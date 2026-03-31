"""FastAPI request handler for the Field-Service RAG Bot.

Exposes a POST endpoint ``/api/chat`` and serves the static front-end.

The RAG pipeline (rag_core.RAG) is initialised on startup once the
ChromaDB vector store is available.  On a fresh deployment the vector
store must be built first – see todo.txt for the required steps.

Usage:
    uvicorn requesthandler:app --reload
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rag_core import RAG

logger = logging.getLogger("requesthandler")
logging.basicConfig(level=logging.INFO)

_rag: RAG | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):  # noqa: ARG001
    """Initialise the RAG pipeline on startup."""
    global _rag  # noqa: PLW0603

    # TODO (Marvin): ensure the ChromaDB vector store is built before starting.
    # See todo.txt for the required setup steps.
    _rag = RAG()
    logger.info("RAG pipeline ready.")
    yield


app = FastAPI(title="Field-Service RAG Bot API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static assets (CSS, JS) from the webpage directory
_WEBPAGE_DIR = Path(__file__).parent / "webpage"
app.mount("/static", StaticFiles(directory=str(_WEBPAGE_DIR)), name="static")


class ChatRequest(BaseModel):
    """Incoming chat message from the front-end."""

    message: str
    sessionId: str


class ChatResponse(BaseModel):
    """Outgoing chat answer returned to the front-end."""

    answer: str


@app.get("/")
async def index() -> FileResponse:
    """Serve the chat UI."""
    return FileResponse(str(_WEBPAGE_DIR / "index.html"))


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Handle a chat request and return a RAG-generated answer.

    Args:
        req: The incoming request containing the user's message and a
             session identifier for future multi-turn support.

    Returns:
        A ``ChatResponse`` with the generated answer string.
    """
    if _rag is None:
        return ChatResponse(answer="RAG-Pipeline noch nicht bereit, bitte kurz warten.")

    result = _rag.answer(req.message)
    return ChatResponse(answer=result["content"])
