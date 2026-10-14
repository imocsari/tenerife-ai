# main.py
# The web layer: like routes.rb + a controller.

from fastapi import FastAPI
from pydantic import BaseModel
import rag

app = FastAPI(title="Tenerife AI")


class AskRequest(BaseModel):     
    question: str


@app.get("/health")               # simple check that the server is running
def health():
    return {"status": "ok"}


@app.post("/ask")                 # POST /ask  →  { "question": "..." }
def ask(request: AskRequest):
    return rag.ask(request.question)
