"""
session.py
Factory function that creates a :class:`requests.Session` pre-configured with
retry logic, connection pooling, and standard headers.

Separating session creation into its own module makes it trivial to inject
a custom session in tests without sub-classing the fetcher.
"""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .constant import USER_AGENT

__all__ = ["create_session"]


def create_session(
    max_retries: int = 3,
    backoff_factor: float = 0.3,
    timeout: int = 20,          # kept for API symmetry; not stored on session
    status_forcelist: tuple = (500, 502, 503, 504),
) -> requests.Session:
    """Build and return a :class:`requests.Session` with retry handling.

    Parameters
    ----------
    max_retries:
        Total number of retries on transient server errors.
    backoff_factor:
        Passed directly to :class:`urllib3.util.Retry`.  Sleep between
        retries grows as ``backoff_factor * (2 ** (retry_number - 1))``.
    timeout:
        Accepted for API symmetry but *not* stored on the session object
        (timeout is passed per-request so callers can override it).
    status_forcelist:
        HTTP status codes that trigger an automatic retry.

    Returns
    -------
    requests.Session
        A fully configured session ready for use.
    """
    session = requests.Session()

    retry_kwargs: dict = {
        "total": max_retries,
        "status_forcelist": list(status_forcelist),
        "backoff_factor": backoff_factor,
        "raise_on_status": False,   # we handle errors ourselves
    }

    # ``allowed_methods`` replaced the deprecated ``method_whitelist`` in
    # urllib3 1.26; fall back gracefully for older installs.
    try:
        retry_strategy = Retry(
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
            **retry_kwargs,
        )
    except TypeError:
        retry_strategy = Retry(
            method_whitelist=["HEAD", "GET", "OPTIONS", "POST"],
            **retry_kwargs,
        )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }
    )

    return session
