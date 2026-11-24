import os
from dotenv import load_dotenv
load_dotenv()

# ── Helius ──────────────────────────────────────────────────────────────────
API_KEY  = os.getenv("HELIUS_API_KEY")
BASE_URL = "https://api.helius.xyz"

# ── Jupiter (prices for tokens Helius doesn't price) ─────────────────────────
# Optional free key from https://portal.jup.ag. Without it the server uses the
# free lite-api host, which Jupiter is retiring.
JUPITER_API_KEY = os.getenv("JUPITER_API_KEY")

# ── Target wallet ────────────────────────────────────────────────────────────
WALLET     = "FuUKYBncpU3BSJ43hgKigKhzYrigWUEja3n69gzNTxeP"

# ── Supabase (PostgreSQL) ─────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")   # set in .env and on Render

# ── Fetch limits ─────────────────────────────────────────────────────────────
PAGE_LIMIT = 100   # max results per Helius page (their max is 100)
MAX_PAGES  = 5     # safety cap so you don't hammer the API while testing
