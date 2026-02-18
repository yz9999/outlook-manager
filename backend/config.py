import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = f"sqlite+aiosqlite:///{os.path.join(DATA_DIR, 'outlook.db')}"

# Microsoft OAuth endpoints
MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
MS_GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Staggered sync: interval between each single-account sync (minutes)
STAGGER_INTERVAL_MINUTES = int(os.environ.get("STAGGER_INTERVAL", "4"))

# Cooldown after completing a full round-robin cycle (hours)
ROUND_COOLDOWN_HOURS = int(os.environ.get("ROUND_COOLDOWN_HOURS", "3"))

# Auth credentials (set via environment variables in production)
AUTH_USERNAME = os.environ.get("AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD", "change-me")
AUTH_SECRET = os.environ.get("AUTH_SECRET", "change-me-to-a-random-secret")

# Default Azure App client_id (shared across all accounts)
DEFAULT_CLIENT_ID = os.environ.get("DEFAULT_CLIENT_ID", "")
