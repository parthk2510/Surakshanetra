"""
constant.py
Global URL constants and path defaults for the Blockchain.com API client.

Keep all hard-coded strings that would otherwise be scattered across modules
in one place so they are easy to update and test.
"""
from pathlib import Path

# ---------------------------------------------------------------------------
# API base URLs
# ---------------------------------------------------------------------------

#: Core Blockchain.info data API (addresses, transactions, blocks, …)
BLOCKCHAIN_BASE: str = "https://blockchain.info"

#: Charts / analytics sub-domain (market-price, hash-rate, etc.)
BLOCKCHAIN_CHARTS_BASE: str = "https://api.blockchain.info"

# ---------------------------------------------------------------------------
# Local file paths
# ---------------------------------------------------------------------------

#: Default directory where graph JSON files are written.
#: Resolved at import time so relative paths work regardless of CWD.
DEFAULT_DATA_DIR: Path = Path("data/graph")
DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)

#: Default directory for saved case / investigation files.
DEFAULT_CASES_DIR: Path = Path("data/cases")
DEFAULT_CASES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# API limits
# ---------------------------------------------------------------------------

#: Hard maximum that blockchain.info returns per /rawaddr page.
RAWADDR_PAGE_HARD_LIMIT: int = 50

#: Maximum UTXOs allowed by the /unspent endpoint.
UNSPENT_HARD_LIMIT: int = 1000

#: Default number of transactions fetched per /rawaddr page.
RAWADDR_DEFAULT_LIMIT: int = 50

#: Default number of UTXOs fetched per /unspent request.
UNSPENT_DEFAULT_LIMIT: int = 250

#: Maximum number of /multiaddr transactions returned in one call.
MULTIADDR_CHUNK_SIZE: int = 100

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

#: User-Agent header sent with every outbound HTTP request.
USER_AGENT: str = "ChainBreak-Forensics/2.0"
