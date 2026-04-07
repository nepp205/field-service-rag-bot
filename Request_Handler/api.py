import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from openai import OpenAIError
from pydantic import BaseModel
import logging
import json

from llm import MAX_TOKENS, fetch_context, get_azure_client


# System-Prompt aus Datei laden, sonst Standardtext nutzen
_SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"
if _SYSTEM_PROMPT_PATH.exists():
    _SYSTEM_PROMPT = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
else:
    _SYSTEM_PROMPT = "You are a helpful field service assistant."


# Einfache Session-Speicherung im Arbeitsspeicher
_sessions: dict[str, list[dict]] = {}

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    sessionId: str
    model: str | None = None


class SessionInitRequest(BaseModel):
    sessionId: str


#endpoints

@router.post("/api/session/init")
async def session_init(req: SessionInitRequest):
    if req.sessionId not in _sessions:
        _sessions[req.sessionId] = [
            {"role": "system", "content": _SYSTEM_PROMPT}
        ]
    return {"status": "ok", "sessionId": req.sessionId}


@router.post("/api/chat")
async def chat(req: ChatRequest):
    client = get_azure_client()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")

    if client is None or not deployment:
        raise HTTPException(
            status_code=503,
            detail="Azure OpenAI client not configured. Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT.",
        )

    # Ensure the session exists (fallback if /api/session/init was not called)
    if req.sessionId not in _sessions:
        logging.warning("Session %s not found – creating on-the-fly.", req.sessionId)
        _sessions[req.sessionId] = [{"role": "system", "content": _SYSTEM_PROMPT}]

    history = _sessions[req.sessionId]

    # RAG-Kontext holen, falls verfuegbar
    try:
        context_text = await fetch_context(req.message, model=req.model, timeout=3.0)
    except Exception:
        context_text = None

    # Alten Kontext ersetzen statt immer neuen anzusammeln
    if context_text:
        context_msg = {
            "role": "system",
            "content": f"Retrieved context:\n{context_text}"
        }
        if len(history) > 1 and history[1].get("content", "").startswith("Retrieved context:"):
            history[1] = context_msg
        else:
            history.insert(1, context_msg)

    history.append({"role": "user", "content": req.message})

    # Log full history that will be sent to main model
    logging.debug("LLM request messages (full history):\n%s", json.dumps(history, ensure_ascii=False, indent=2))

    try:
        response = await client.chat.completions.create(
            model=deployment,
            messages=history,
            max_tokens=MAX_TOKENS,
        )
        choices = response.choices
        answer = choices[0].message.content or "" if choices else ""
        history.append({"role": "assistant", "content": answer})
        return {"answer": answer}

    except OpenAIError as exc:
        logging.exception("Azure OpenAI SDK error: %s", exc)
        if history:
            history.pop()
        if len(history) > 1 and history[1].get("content", "").startswith("Retrieved context:"):
            history.pop(1)
        raise HTTPException(status_code=502, detail=f"Azure OpenAI request failed: {exc}")