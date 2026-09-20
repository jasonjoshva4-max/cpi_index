"""APIx configuration settings."""
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"

# User Agent
DEFAULT_USER_AGENT = (
    "APIx-AirfareBot/1.0 (+https://apix.example.com/bot; bot@apix.example.com)"
)

# Base Period Setting
DEFAULT_BASE_DATE = "2026-09-20"


# Rate Limiting & Delays (seconds)
DEFAULT_MIN_JOB_GAP = 2.0
DEFAULT_MAX_JOB_GAP = 5.0

# Retries & Backoff
DEFAULT_MAX_RETRIES = 3
DEFAULT_INITIAL_BACKOFF = 2.0  # seconds

# Timeout settings (ms)
DEFAULT_PAGE_TIMEOUT = 30000

# Supported Sources Configuration
SOURCE_DOMAINS = {
    "indigo": "https://www.goindigo.in",
}
