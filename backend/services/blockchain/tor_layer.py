"""
tor_layer.py
Tor anonymity layer helper used optionally by the Blockchain.com API client.

``TorNetworkLayer`` wraps the Tor SOCKS proxy settings *and* provides Tor
control-port functionality (circuit renewal via ``SIGNAL NEWNYM``).
"""
from __future__ import annotations

import logging
import socket
import time
from pathlib import Path
from typing import Dict, Optional, Union

import requests

__all__ = ["TorNetworkLayer"]

log = logging.getLogger(__name__)


class TorNetworkLayer:
    """Encapsulates Tor proxy configuration and control-port operations.

    Parameters
    ----------
    socks_proxy:
        Full SOCKS5-over-Tor URL, e.g. ``"socks5h://127.0.0.1:9050"``.
    control_host:
        Hostname of the Tor control port (usually ``"127.0.0.1"``).
    control_port:
        TCP port number for the Tor control interface (usually ``9051``).
    auth_password:
        Plain-text password for ``AUTHENTICATE`` (``HashedControlPassword``
        must be set in ``torrc``).  If *None* the layer tries cookie auth
        then null auth.
    cookie_auth:
        When ``True``, attempt cookie-file authentication *first*.
    data_directory:
        Path to Tor's data directory that contains ``control_auth_cookie``.
        Required for cookie auth.
    min_renew_interval_s:
        Minimum seconds between consecutive ``SIGNAL NEWNYM`` commands.
        Tor itself enforces a 10-second cool-down on identity rotation.
    """

    def __init__(
        self,
        socks_proxy: str = "socks5h://127.0.0.1:9050",
        control_host: str = "127.0.0.1",
        control_port: int = 9051,
        auth_password: Optional[str] = None,
        cookie_auth: bool = True,
        data_directory: Optional[Union[str, Path]] = None,
        min_renew_interval_s: float = 10.0,
    ) -> None:
        self.proxies: Dict[str, str] = {
            "http": socks_proxy,
            "https": socks_proxy,
        }
        self.control_host = control_host
        self.control_port = control_port
        self.auth_password = auth_password
        self.cookie_auth = cookie_auth
        self.data_directory = (
            Path(data_directory) if data_directory is not None else None
        )
        self.min_renew_interval_s = min_renew_interval_s
        self._last_renew_ts: float = 0.0

    # ------------------------------------------------------------------ #
    # Control-port helpers (private)
    # ------------------------------------------------------------------ #

    def _authenticate(self, sock: socket.socket) -> bool:
        """Try to authenticate on an already-opened control socket.

        Attempts cookie auth (if configured), then password auth, then
        null (unauthenticated) auth, in that order.  Returns ``True`` on
        the first successful method.
        """
        # 1. Cookie authentication
        if self.cookie_auth and self.data_directory is not None:
            cookie_path = self.data_directory / "control_auth_cookie"
            if cookie_path.exists():
                try:
                    cookie_hex = cookie_path.read_bytes().hex()
                    sock.sendall(f"AUTHENTICATE {cookie_hex}\r\n".encode())
                    resp = sock.recv(1024).decode("utf-8", errors="ignore")
                    if resp.startswith("250"):
                        log.debug("Tor cookie authentication succeeded")
                        return True
                    log.debug("Tor cookie auth failed: %s", resp.strip())
                except Exception as exc:
                    log.debug("Tor cookie auth error: %s", exc)

        # 2. Password authentication
        if self.auth_password is not None:
            sock.sendall(f'AUTHENTICATE "{self.auth_password}"\r\n'.encode())
            resp = sock.recv(1024).decode("utf-8", errors="ignore")
            if resp.startswith("250"):
                log.debug("Tor password authentication succeeded")
                return True
            log.debug("Tor password auth failed: %s", resp.strip())
            return False

        # 3. Null authentication (works when CookieAuthentication 0 / HashedControlPassword not set)
        sock.sendall(b"AUTHENTICATE\r\n")
        resp = sock.recv(1024).decode("utf-8", errors="ignore")
        if resp.startswith("250"):
            log.debug("Tor null authentication succeeded")
            return True
        log.debug("Tor null auth failed: %s", resp.strip())
        return False

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def renew_identity(self) -> bool:
        """Send ``SIGNAL NEWNYM`` to rotate the Tor exit circuit.

        Guards against spamming the control port by enforcing
        ``min_renew_interval_s`` between calls.

        Returns
        -------
        bool
            ``True`` if the command was sent successfully, ``False``
            otherwise (rate-limited or control-port unreachable).
        """
        now = time.time()
        if (now - self._last_renew_ts) < self.min_renew_interval_s:
            log.debug(
                "Tor NEWNYM skipped – cooldown %.1fs remaining",
                self.min_renew_interval_s - (now - self._last_renew_ts),
            )
            return False

        try:
            with socket.create_connection(
                (self.control_host, self.control_port), timeout=3
            ) as sock:
                sock.settimeout(3)
                if not self._authenticate(sock):
                    log.warning("Tor authentication failed; cannot renew identity")
                    return False
                sock.sendall(b"SIGNAL NEWNYM\r\n")
                resp = sock.recv(1024).decode("utf-8", errors="ignore")
                if not resp.startswith("250"):
                    log.debug("Tor NEWNYM failed: %s", resp.strip())
                    return False
                self._last_renew_ts = now
                log.info("Tor identity renewed successfully")
                return True
        except Exception as exc:
            log.debug("Tor identity renewal error: %s", exc)
            return False

    def get_current_ip(self) -> str:
        """Probe the current Tor exit IP via ``httpbin.org/ip``.

        Returns
        -------
        str
            The exit IP address string, or a human-readable error message.
        """
        try:
            resp = requests.get(
                "http://httpbin.org/ip",
                proxies=self.proxies,
                timeout=15,
            )
            resp.raise_for_status()
            # httpbin returns {"origin": "1.2.3.4"}
            return resp.json().get("origin", resp.text.strip())
        except Exception as exc:
            log.debug("Could not determine Tor IP: %s", exc)
            return f"(error: {exc})"
