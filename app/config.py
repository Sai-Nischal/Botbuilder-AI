import os
from pathlib import Path
from dotenv import load_dotenv
from cryptography.fernet import Fernet

# Load environment variables from .env file if available
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

raw_tokens_str = os.getenv("TELEGRAM_BOT_TOKENS", "").strip() or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BOT_TOKENS = [t.strip() for t in raw_tokens_str.split(",") if t.strip()]
TELEGRAM_BOT_TOKEN = TELEGRAM_BOT_TOKENS[0] if TELEGRAM_BOT_TOKENS else ""

MAX_BOTS_PER_USER = 4
_CURRENT_TOKEN_INDEX = 0

def get_current_bot_token() -> str:
    global _CURRENT_TOKEN_INDEX
    if not TELEGRAM_BOT_TOKENS:
        return ""
    if _CURRENT_TOKEN_INDEX >= len(TELEGRAM_BOT_TOKENS):
        _CURRENT_TOKEN_INDEX = 0
    return TELEGRAM_BOT_TOKENS[_CURRENT_TOKEN_INDEX]

def rotate_to_next_bot_token() -> str:
    global _CURRENT_TOKEN_INDEX
    if not TELEGRAM_BOT_TOKENS or len(TELEGRAM_BOT_TOKENS) <= 1:
        return get_current_bot_token()
    _CURRENT_TOKEN_INDEX = (_CURRENT_TOKEN_INDEX + 1) % len(TELEGRAM_BOT_TOKENS)
    print(f"[TOKEN POOL ROTATION] Rotated to bot token index {_CURRENT_TOKEN_INDEX}")
    return TELEGRAM_BOT_TOKENS[_CURRENT_TOKEN_INDEX]

SECRET_KEY = os.getenv("SECRET_KEY", "default-dev-secret-key-change-in-production-1234567890").strip()

# Encryption key for Fernet stored tokens
raw_enc_key = os.getenv("ENCRYPTION_KEY", "").strip()
if not raw_enc_key:
    # Generate a deterministic or persistent fallback key for dev environment if not set
    # Fernet key must be 32 url-safe base64-encoded bytes
    raw_enc_key = Fernet.generate_key().decode()

ENCRYPTION_KEY = raw_enc_key

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GOOGLE_PLACES_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY", "").strip() or os.getenv("GOOGLE_MAPS_API_KEY", "").strip()
IS_VERCEL = "VERCEL" in os.environ or os.getenv("VERCEL_ENV") is not None

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    if IS_VERCEL:
        DATABASE_URL = "sqlite:////tmp/botbuilder.db"
    else:
        DATABASE_URL = "sqlite:///./botbuilder.db"
elif IS_VERCEL and DATABASE_URL == "sqlite:///./botbuilder.db":
    DATABASE_URL = "sqlite:////tmp/botbuilder.db"

DEBUG = os.getenv("DEBUG", "true").lower() in ("true", "1", "yes")
ENABLE_MANAGED_BOTS = os.getenv("ENABLE_MANAGED_BOTS", "false").lower() in ("true", "1", "yes")

# Matcher thresholds
HIGH_THRESHOLD = float(os.getenv("HIGH_THRESHOLD", "0.60"))
LOW_THRESHOLD = float(os.getenv("LOW_THRESHOLD", "0.40"))
PASSAGE_THRESHOLD = float(os.getenv("PASSAGE_THRESHOLD", "0.50"))

# Directories
if IS_VERCEL:
    DATA_DIR = Path("/tmp/data")
else:
    DATA_DIR = BASE_DIR / "data"

BUSINESSES_DIR = DATA_DIR / "businesses"
INDEX_DIR = DATA_DIR / "index"
DOCS_DIR = DATA_DIR / "docs"

# Ensure data directories exist
for folder in [DATA_DIR, BUSINESSES_DIR, INDEX_DIR, DOCS_DIR]:
    folder.mkdir(parents=True, exist_ok=True)

# Embedding model settings
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
