# app/main.py
# The web layer only (like routes.rb + a controller).
# Run from the project folder:  uvicorn app.main:app --reload

from fastapi import FastAPI
from pydantic import BaseModel

from app import rag

app = FastAPI(title="Tenerife AI")


class AskRequest(BaseModel):
    question: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(request: AskRequest):
    return rag.ask(request.question)
