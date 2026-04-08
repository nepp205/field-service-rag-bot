"""FastAPI request handler for the Field-Service RAG Bot.

Usage:
    # development (auto-reload on file changes)
    gunicorn -k uvicorn.workers.UvicornWorker --reload requesthandler:app

    # production (via gunicorn.conf.py)
    gunicorn -c gunicorn.conf.py requesthandler:app
"""

import os
import logging
from pathlib import Path
import json
import httpx
from typing import Optional

from fastapi import FastAPI, HTTPException
from openai import AzureOpenAI, OpenAIError
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

# Optional: load a local .env when developing locally (install python-dotenv)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

MAX_TOKENS = 100


# Context Handler config (optional). If not set, context lookup is skipped.
# CONTEXT_HANDLER_URL can be overridden via environment variable so the correct
# Docker service name (e.g. http://context-handler:5000/context) is used when
# both services run inside the same Docker network.
CONTEXT_HANDLER_URL = os.environ.get("CONTEXT_HANDLER_URL", "http://localhost:5000/context")
CONTEXT_HANDLER_TOKEN = os.environ.get("CONTEXT_HANDLER_TOKEN")

# ---------------------------------------------------------------------------
# System prompt – loaded once at module import time from system_prompt.txt.
# Falls back to a minimal default if the file is not found.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"
try:
    _SYSTEM_PROMPT = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
    logging.info("System prompt loaded from %s", _SYSTEM_PROMPT_PATH)
except FileNotFoundError:
    _SYSTEM_PROMPT = "You are a helpful field service assistant."
    logging.warning(
        "system_prompt.txt not found at %s – using minimal default.",
        _SYSTEM_PROMPT_PATH,
    )

# ---------------------------------------------------------------------------
# In-memory session store: maps sessionId → list of OpenAI-style messages.
# ---------------------------------------------------------------------------
_sessions: dict[str, list[dict]] = {}

app = FastAPI(title="Field-Service RAG Bot API")

# Allow all origins for the demo phase.
# Restrict `allow_origins` to the actual front-end URL in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    """Incoming chat message from the front-end.

    Optional `model` can be provided by the frontend and is forwarded to the
    Context_Handler as a filter. It does NOT change the Azure deployment used
    for the final LLM call (that is controlled via AZURE_OPENAI_DEPLOYMENT).
    """

    message: str
    sessionId: str
    model: Optional[str] = None


class ChatResponse(BaseModel):
    """Outgoing chat answer returned to the front-end."""

    answer: str


class SessionInitRequest(BaseModel):
    """Request body for initialising a new session."""

    sessionId: str


class SessionInitResponse(BaseModel):
    """Response returned after a session is initialised."""

    status: str
    sessionId: str


_azure_client = None


@app.on_event("startup")
async def startup_event():
    """Initialize AzureOpenAI clients if env vars are present; otherwise warn."""
    global _azure_client

    missing = [
        v for v in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT")
        if not os.environ.get(v)
    ]
    if missing:
        logging.warning(
            "Missing required environment variable(s): %s. Server will start but /api/chat will return 503 until set.",
            ", ".join(missing),
        )
    else:
        _azure_client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version="2024-02-01",
        )
        logging.info("Azure OpenAI client initialized.")


async def fetch_context(query: str, model: Optional[str] = None, timeout: float = 3.0) -> Optional[str]:
    """Call the external Context_Handler HTTP service to retrieve relevant context.

    Returns the context string on success or None on error / if service not configured.
    """
    if not CONTEXT_HANDLER_URL or not CONTEXT_HANDLER_TOKEN:
        logging.debug("Context handler not configured (URL/token missing) – skipping context fetch.")
        return None

    headers = {
        "Authorization": f"Bearer {CONTEXT_HANDLER_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {"query": query}
    if model:
        payload["model"] = model

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            logging.debug("Calling Context_Handler %s with payload: %s", CONTEXT_HANDLER_URL, payload)
            resp = await client.post(CONTEXT_HANDLER_URL, headers=headers, json=payload)
        logging.debug("Context_Handler response status: %s", resp.status_code)
        if resp.status_code != 200:
            logging.warning("Context handler returned non-200 status %s: %s", resp.status_code, resp.text)
            return None
        data = resp.json()
        context = data.get("context")
        if context is None:
            logging.warning("Context handler response missing 'context' field: %s", data)
            return None
        # ensure string
        if isinstance(context, list):
            # join list items into a single string
            context = "\n\n".join(map(str, context))
        else:
            context = str(context)
        logging.debug("Retrieved context length=%d", len(context))
        return context
    except httpx.RequestError as exc:
        logging.warning("Context handler request failed: %s", exc)
        return None
    except Exception as exc:
        logging.warning("Unexpected error fetching context: %s", exc)
        return None


@app.post("/api/session/init", response_model=SessionInitResponse)
async def session_init(req: SessionInitRequest) -> SessionInitResponse:
    """Initialise a chat session with the system prompt.

    Creates a new session entry containing only the system prompt message.
    If the session already exists it is left unchanged (idempotent).
    The LLM is **not** called; nothing is shown in the UI.

    Args:
        req: Request body containing the client-generated session ID.

    Returns:
        A ``SessionInitResponse`` with status ``"ok"`` and the session ID.
    """
    if req.sessionId not in _sessions:
        _sessions[req.sessionId] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        logging.info("Session initialised: %s", req.sessionId)
    else:
        logging.info("Session already exists, skipping init: %s", req.sessionId)
    return SessionInitResponse(status="ok", sessionId=req.sessionId)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Handle a chat request and return an answer from the Azure OpenAI API.

    Maintains full conversation history per session so the LLM has context
    from previous turns. If no session exists yet (e.g. the init endpoint was
    not called) one is created on-the-fly with the system prompt.

    Args:
        req: The incoming request containing the user's message and session ID.

    Returns:
        A ``ChatResponse`` with the generated answer string.
    """
    if _azure_client is None:
        raise HTTPException(
            status_code=503,
            detail="Azure OpenAI client not configured. Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT.",
        )

    # Ensure the session exists (fallback if /api/session/init was not called)
    if req.sessionId not in _sessions:
        logging.warning("Session %s not found – creating on-the-fly.", req.sessionId)
        _sessions[req.sessionId] = [{"role": "system", "content": _SYSTEM_PROMPT}]

    history = _sessions[req.sessionId]

    # 1) Try fetching context from the Context_Handler service (optional)
    try:
        context_text = await fetch_context(req.message, model=req.model)
    except Exception as e:
        logging.warning("Error while fetching context: %s", e)
        context_text = None

    if context_text:
        # Insert the returned context right after the system prompt so the model sees it
        # without overwriting the main system instruction.
        logging.debug("Inserting retrieved context into history (len=%d)", len(context_text))
        history.insert(1, {"role": "system", "content": f"Retrieved context:\n{context_text}"})

    # 2) Append the user's raw message to the history
    history.append({"role": "user", "content": req.message})

    # Log full history that will be sent to main model
    logging.debug("LLM request messages (full history):\n%s", json.dumps(history, ensure_ascii=False, indent=2))

    try:
        completion = _azure_client.chat.completions.create(
            model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            messages=history,
            max_tokens=MAX_TOKENS,
        )
        answer = completion.choices[0].message.content or ""
        history.append({"role": "assistant", "content": answer})
        return ChatResponse(answer=answer)
    except Exception as e:
        logging.error("AZURE FEHLER: %s", str(e), exc_info=True)
        return ChatResponse(answer=f"Interner Fehler: {type(e).__name__}")

