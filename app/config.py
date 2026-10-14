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
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_DIM = 384          # must match EMBED_MODEL; used for the pgvector column

# --- LLM --------------------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")  # "ollama" or "claude"
# qwen2.5:7b, not llama3.2 (2026-10-14): tool calling is the job now, and llama3.2 at 3B
# cannot do it — it answered "I don't know" to questions whose data was in front of it, and
# described tool calls in prose instead of making them. 7B is the realistic floor here, and
# fits a 16GB machine alongside everything else.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
MAX_TOKENS = 600

# --- Database ---------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Retrieval --------------------------------------------------------------
TOP_K = 6                # how many sources the LLM receives
