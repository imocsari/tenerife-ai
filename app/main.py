# app/main.py
# The web layer only (like routes.rb + a controller).
# Run from the project folder:  uvicorn app.main:app --reload

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app import rag

STATIC_DIR = Path(__file__).resolve().parent / "static"

@asynccontextmanager
async def lifespan(_app):
    """Warm the slow things before the first question rather than during it: the embedding
    model takes seconds to load, and whoever asked first was paying for it."""
    try:
        from app.embeddings import embed
        embed("warm up")
        from app.db import pool
        pool()
        print("[startup] embedding model and database pool ready", flush=True)
    except Exception as e:                       # never block serving on a warm-up failure
        print(f"[startup] warm-up skipped: {type(e).__name__}: {e}", flush=True)
    yield


app = FastAPI(title="Tenerife AI", lifespan=lifespan)

# Who may call this from a browser. Defaults to local development; set ALLOWED_ORIGINS in the
# environment for production, e.g. "https://tenerinfo.app,https://www.tenerinfo.app".
ALLOWED_ORIGINS = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
    allow_methods=["POST", "GET"], allow_headers=["Content-Type", "X-API-Key"],
)

# Optional shared secret. Unset means open, which is right for local development and wrong in
# production — set API_KEY there, and the page passes it through.
API_KEY = os.getenv("API_KEY")

# Crude per-IP throttle. Not a substitute for a real limiter at the edge, but it stops one
# script turning the model bill into someone else's hobby.
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "20"))
_hits: dict[str, list[float]] = {}


def _rate_limit(request: Request):
    who = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
           or (request.client.host if request.client else "unknown"))
    now = time.monotonic()
    recent = [t for t in _hits.get(who, []) if now - t < 60]
    if len(recent) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(429, "Too many questions in a minute — give it a moment.")
    recent.append(now)
    _hits[who] = recent
    if len(_hits) > 10_000:          # keep the dict from growing without bound
        for key in [k for k, v in _hits.items() if not v or now - v[-1] > 300]:
            _hits.pop(key, None)


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def home():
    """The chat page. /docs still has the raw API for testing."""
    return FileResponse(STATIC_DIR / "index.html")


class Turn(BaseModel):
    role: str
    content: str = Field(max_length=4000)


class AskRequest(BaseModel):
    # Bounded on the way in. An unbounded question is a bill someone else can run up, and a
    # 50,000-character prompt is never a real traveller asking about dinner.
    question: str = Field(min_length=2, max_length=500)
    # The conversation so far, sent by the client. Keeping it there rather than in server
    # memory means no sessions, no expiry and no state to lose when the process restarts —
    # the page already has the thread on screen.
    history: list[Turn] = []


@app.get("/health")
def health():
    return {"status": "ok"}


class Feedback(BaseModel):
    question: str = Field(max_length=500)
    score: int = Field(ge=-1, le=1)


@app.post("/feedback")
def feedback(body: Feedback):
    """Thumbs up or down. Logged, not stored — enough to find bad answers in the log without
    building a database of what individuals asked."""
    print(f'[feedback] {"up" if body.score > 0 else "down"}  q={body.question[:80]!r}', flush=True)
    return {"ok": True}


@app.post("/ask")
def ask(body: AskRequest, request: Request, x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "Missing or wrong API key.")
    _rate_limit(request)

    started = time.monotonic()
    result = rag.ask(body.question, [t.model_dump() for t in body.history])
    # Logged without anything personal: no IP, no identifiers. The question itself is needed
    # to see what people ask and what comes back empty.
    print(f'[ask] {time.monotonic() - started:.1f}s  sources={len(result["sources"])}  '
          f'q={body.question[:80]!r}', flush=True)
    return result
