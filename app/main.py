# app/main.py
# The web layer only (like routes.rb + a controller).
# Run from the project folder:  uvicorn app.main:app --reload

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import rag

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Tenerife AI")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def home():
    """The chat page. /docs still has the raw API for testing."""
    return FileResponse(STATIC_DIR / "index.html")


class Turn(BaseModel):
    role: str
    content: str


class AskRequest(BaseModel):
    question: str
    # The conversation so far, sent by the client. Keeping it there rather than in server
    # memory means no sessions, no expiry and no state to lose when the process restarts —
    # the page already has the thread on screen.
    history: list[Turn] = []


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(request: AskRequest):
    return rag.ask(request.question, [t.model_dump() for t in request.history])
