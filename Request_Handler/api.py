"""API routes for the Field-Service RAG Bot.

Defines Pydantic models, the in-memory session store, and both endpoints:
- POST /api/session/init
- POST /api/chat

Mount via ``app.include_router(router)`` in server.py.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from openai import OpenAIError
from pydantic import BaseModel

from llm import MAX_TOKENS, fetch_context, get_azure_client, optimize_prompt

# ---------------------------------------------------------------------------
# System prompt – loaded once at import time from system_prompt.txt.
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

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/session/init", response_model=SessionInitResponse)
async def session_init(req: SessionInitRequest) -> SessionInitResponse:
    """Initialise a chat session with the system prompt.

    Creates a new session entry containing only the system prompt message.
    If the session already exists it is left unchanged (idempotent).
    The LLM is **not** called; nothing is shown in the UI.
    """
    if req.sessionId not in _sessions:
        _sessions[req.sessionId] = [{"role": "system", "content": _SYSTEM_PROMPT}]
        logging.info("Session initialised: %s", req.sessionId)
    else:
        logging.info("Session already exists, skipping init: %s", req.sessionId)
    return SessionInitResponse(status="ok", sessionId=req.sessionId)


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Handle a chat request and return an answer from the Azure OpenAI API.

    Maintains full conversation history per session so the LLM has context
    from previous turns. If no session exists yet (e.g. the init endpoint was
    not called) one is created on-the-fly with the system prompt.
    """
    azure_client = get_azure_client()
    if azure_client is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Azure OpenAI client not configured. "
                "Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT."
            ),
        )

    # Ensure the session exists (fallback if /api/session/init was not called)
    if req.sessionId not in _sessions:
        logging.warning("Session %s not found – creating on-the-fly.", req.sessionId)
        _sessions[req.sessionId] = [{"role": "system", "content": _SYSTEM_PROMPT}]

    history = _sessions[req.sessionId]

    # 1) Try fetching context from the Context_Handler service (optional).
    # Replace the previous context entry (position 1) to avoid accumulation.
    context_inserted = False
    try:
        context_text = await fetch_context(req.message, model=req.model)
    except Exception as exc:
        logging.warning("Error while fetching context: %s", exc)
        context_text = None

    if context_text:
        logging.debug(
            "Inserting retrieved context into history (len=%d)", len(context_text)
        )
        context_msg = {"role": "system", "content": f"Retrieved context:\n{context_text}"}
        if len(history) > 1 and history[1].get("content", "").startswith("Retrieved context:"):
            history[1] = context_msg
        else:
            history.insert(1, context_msg)
        context_inserted = True

    # 2) Run the lightweight prompt optimiser (if configured) and append user message
    optimized_message = optimize_prompt(req.message)
    history.append({"role": "user", "content": optimized_message})

    logging.debug(
        "LLM request messages (full history):\n%s",
        json.dumps(history, ensure_ascii=False, indent=2),
    )

    try:
        completion = azure_client.chat.completions.create(
            model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            messages=history,
            max_tokens=MAX_TOKENS,
        )
        answer = completion.choices[0].message.content or ""
        history.append({"role": "assistant", "content": answer})
        return ChatResponse(answer=answer)
    except OpenAIError as exc:
        # Remove the user message (and freshly inserted context) to keep history consistent
        history.pop()
        if context_inserted and len(history) > 1 and history[1].get("content", "").startswith("Retrieved context:"):
            history.pop(1)
        raise HTTPException(status_code=502, detail="Azure OpenAI request failed.") from exc
