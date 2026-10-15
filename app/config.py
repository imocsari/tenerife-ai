# app/config.py
# All settings in one place. Values come from the .env file.

import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent   # the tenerife-ai folder
load_dotenv(BASE_DIR / ".env")

# --- Data files -------------------------------------------------------------
DATA_DIR = BASE_DIR / "data"
PAGES_DIR = DATA_DIR / "pages"                       # raw Wikivoyage pages
CHUNKS_FILE = DATA_DIR / "chunks.json"
EMBEDDED_CHUNKS_FILE = DATA_DIR / "chunks_with_embeddings.json"

# --- Embeddings -------------------------------------------------------------
# The stored vectors in data/chunks_with_embeddings.json were built with bge-small, so this must stay
# bge-small unless they are regenerated: both models output 384 dimensions, so a mismatch raises no
# error at all — it just silently returns meaningless rankings. (The old flat search.py had exactly
# that bug: it embedded queries with MiniLM against bge-small chunks.)
# Multilingual (2026-10-15). bge-small is English-only, which was fine for an English
# travel guide and wrong for a tourist assistant: measured across the app's 8 languages,
# the same question scored 0.77 in English but 0.65 in Russian, and Polish, Italian and
# Hungarian returned the wrong venues outright — Polish asking for live music got a
# sports bar. Same 384 dimensions, so the pgvector column is unchanged, but every stored
# vector must be regenerated: a query embedded by one model against passages embedded by
# another returns confident nonsense rather than an error.
EMBED_MODEL = "intfloat/multilingual-e5-small"
EMBED_DIM = 384          # must match EMBED_MODEL; used for the pgvector column

# --- LLM --------------------------------------------------------------------
# Defaults to claude, not ollama (2026-10-15). The old default meant any deployment that
# forgot the variable tried to reach a local Ollama that is not in the container, failed, and
# answered every single question with the "could not reach the service" fallback — a silent
# misconfiguration dressed up as a transient outage. Claude needs a key, so getting it wrong
# now fails loudly at the first request instead.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "claude")  # "claude" or "ollama"
# qwen2.5:7b, not llama3.2 (2026-10-14): tool calling is the job now, and llama3.2 at 3B
# cannot do it — it answered "I don't know" to questions whose data was in front of it, and
# described tool calls in prose instead of making them. 7B is the realistic floor here, and
# fits a 16GB machine alongside everything else.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
# The bare id, not the dated snapshot: both resolve to the same model today, but the dated
# form pins to one snapshot forever, so the app would never pick up a newer Haiku 4.5 build.
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
MAX_TOKENS = 600

# A tool-using turn makes several round trips; this bounds the whole thing.
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "90"))

# How long a weather or sea answer stays good enough to reuse. Forecasts update hourly at
# best, so re-fetching per question buys nothing and just adds latency and load on a free API.
API_CACHE_SECONDS = int(os.getenv("API_CACHE_SECONDS", "1800"))

# --- Database ---------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Retrieval --------------------------------------------------------------
TOP_K = 6                # how many sources the LLM receives
