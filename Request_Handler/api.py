import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from openai import OpenAIError
from pydantic import BaseModel
import httpx
import logging

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
    # Use explicit REST call to Azure OpenAI deployments endpoint.
    # This is more robust across different SDK versions and ensures the
    # deployment name is included explicitly. We do NOT modify the
    # AZURE_OPENAI_ENDPOINT value here (no URL filtering) – we use it verbatim
    # when constructing the request URL.
    if req.sessionId not in _sessions:
        raise HTTPException(status_code=400, detail="Session not initialized")

    history = _sessions[req.sessionId]

    # RAG-Kontext holen, falls verfuegbar
    try:
        # fetch_context signature may ignore model; we pass req.model for future use
        context_text = await fetch_context(req.message, timeout=3.0)
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

    # Read required Azure env vars
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")

    if not endpoint or not api_key or not deployment:
        # revert history additions
        if history:
            history.pop()
        if len(history) > 1 and history[1].get("content", "").startswith("Retrieved context:"):
            history.pop(1)
        raise HTTPException(status_code=503, detail="Azure OpenAI configuration missing (endpoint/key/deployment)")

    # Construct URL using the env-provided endpoint verbatim (no filtering)
    url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={api_version}"

    payload = {
        # also include model explicitly in the body to satisfy clients that
        # expect it there; Azure accepts deployment in the path but this
        # makes the request explicit.
        "model": deployment,
        "messages": history,
        "max_tokens": MAX_TOKENS,
    }

    headers = {"Content-Type": "application/json", "api-key": api_key}

    try:
        async with httpx.AsyncClient(timeout=3000.0) as client:
            resp = await client.post(url, headers=headers, json=payload)

        if resp.status_code >= 400:
            logging.error("Azure OpenAI returned %s: %s", resp.status_code, resp.text)
            # undo history changes
            if history:
                history.pop()
            if len(history) > 1 and history[1].get("content", "").startswith("Retrieved context:"):
                history.pop(1)
            raise HTTPException(status_code=502, detail=f"Azure OpenAI request failed: {resp.status_code}")

        data = resp.json()
        # Extract answer: Azure chat completions usually return choices[0].message.content
        answer = ""
        try:
            answer = data.get("choices", [])[0].get("message", {}).get("content", "")
        except Exception:
            answer = data.get("choices", [])[0].get("text", "") if data.get("choices") else ""

        history.append({"role": "assistant", "content": answer})
        return {"answer": answer}

    except httpx.RequestError as exc:
        logging.exception("Request to Azure OpenAI failed: %s", exc)
        if history:
            history.pop()
        if len(history) > 1 and history[1].get("content", "").startswith("Retrieved context:"):
            history.pop(1)
        raise HTTPException(status_code=502, detail="Azure OpenAI request failed (network error)")