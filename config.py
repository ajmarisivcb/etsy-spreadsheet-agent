"""Environment + path configuration. Reads .env from the agent dir."""

import os
import time
from pathlib import Path
from dotenv import load_dotenv, set_key

AGENT_DIR = Path(__file__).resolve().parent
ENV_PATH = AGENT_DIR / ".env"
load_dotenv(ENV_PATH)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ETSY_CLIENT_ID = os.environ.get("ETSY_CLIENT_ID", "")
ETSY_REDIRECT_URI = os.environ.get("ETSY_REDIRECT_URI", "http://localhost:8765/callback")
ETSY_ACCESS_TOKEN = os.environ.get("ETSY_ACCESS_TOKEN", "")
ETSY_REFRESH_TOKEN = os.environ.get("ETSY_REFRESH_TOKEN", "")
ETSY_TOKEN_EXPIRES_AT = float(os.environ.get("ETSY_TOKEN_EXPIRES_AT") or 0)
ETSY_SHOP_ID = os.environ.get("ETSY_SHOP_ID", "")
ETSY_USER_ID = os.environ.get("ETSY_USER_ID", "")

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR") or (AGENT_DIR / "output")).resolve()
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = AGENT_DIR / "state.db"

MODEL = "claude-opus-4-7"


def persist(key: str, value: str) -> None:
    """Write a value back to .env so the next run picks it up."""
    if not ENV_PATH.exists():
        ENV_PATH.touch()
    set_key(str(ENV_PATH), key, value)
    os.environ[key] = value


def token_is_expired(skew_seconds: int = 60) -> bool:
    if not ETSY_TOKEN_EXPIRES_AT:
        return True
    return time.time() + skew_seconds >= ETSY_TOKEN_EXPIRES_AT
