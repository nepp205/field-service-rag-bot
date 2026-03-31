"""FastAPI request handler for the Field-Service RAG Bot.

Exposes a POST endpoint ``/api/chat`` and serves the static front-end.

On startup the handler checks whether the ChromaDB vector store already
exists under ``CHROMA_PATH`` (default ``/data/chroma_db``).  If it does
not exist the PDF is ingested automatically so the first cold boot on a
fresh HuggingFace Space with Persistent Storage works without any manual
intervention.

Usage:
    uvicorn requesthandler:app --reload
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from DB.build_db import build
from rag_core import CHROMA_PATH, COLLECTION_NAME, RAG

logger = logging.getLogger("requesthandler")
logging.basicConfig(level=logging.INFO)

_rag: RAG | None = None

PDF_PATH = Path(__file__).parent / "DB" / "Miele-PFD-401-MasterLine-Bedienungsanleitung.pdf"


def _db_exists() -> bool:
    """Return True when the ChromaDB collection directory is already populated."""
    chroma_dir = Path(CHROMA_PATH)
    return chroma_dir.exists() and any(chroma_dir.iterdir())


@asynccontextmanager
async def lifespan(application: FastAPI):  # noqa: ARG001
    """Build the vector DB on first boot, then initialise the RAG pipeline."""
    global _rag  # noqa: PLW0603

    if not _db_exists():
        logger.info("ChromaDB not found at %s – building from PDF …", CHROMA_PATH)
        build(pdf_path=PDF_PATH, chroma_path=CHROMA_PATH, collection_name=COLLECTION_NAME)
        logger.info("ChromaDB build complete.")
    else:
        logger.info("ChromaDB found at %s – skipping build.", CHROMA_PATH)

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
