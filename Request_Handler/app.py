"""Field-Service RAG Bot – single-file entry point.

Combines llm.py, api.py and server.py into one runnable module.

Start modes:
  Dev:       python app.py
  Prod-like: gunicorn -k uvicorn.workers.UvicornWorker app:app \\
                 -b 0.0.0.0:8000 --access-logfile - --error-logfile -
"""

import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import AsyncAzureOpenAI, OpenAIError
from pydantic import BaseModel

# Load .env when present (development convenience)
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
for _name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(_name).setLevel(logging.DEBUG)

# ---------------------------------------------------------------------------
# Configuration constants  (formerly llm.py)
# ---------------------------------------------------------------------------

MAX_TOKENS = 100
CONTEXT_HANDLER_URL = os.getenv("CONTEXT_HANDLER_URL", "http://localhost:5000/context")
CONTEXT_HANDLER_TOKEN = os.getenv("CONTEXT_HANDLER_TOKEN")

_azure_client: Optional[AsyncAzureOpenAI] = None


def init_clients() -> None:
    """Initialize the Azure OpenAI client from environment variables."""
    global _azure_client
    missing = [
        v
        for v in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_KEY", "AZURE_OPENAI_DEPLOYMENT")
        if not os.environ.get(v)
    ]
    if missing:
        logging.warning(
            "Missing required environment variable(s): %s. Server will start but /api/chat will return 503 until set.",
            ", ".join(missing),
        )

    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")

    try:
        _azure_client = AsyncAzureOpenAI(
            azure_endpoint=endpoint, api_key=api_key, api_version=api_version
        )
        logging.info(
            "Azure OpenAI client initialized (endpoint=%s, api_version=%s)",
            endpoint,
            api_version,
        )
    except Exception as exc:
        logging.exception("Failed to initialize Azure OpenAI client: %s", exc)
        _azure_client = None


def get_azure_client() -> Optional[AsyncAzureOpenAI]:
    """Return the initialized Azure client, or None if not configured."""
    return _azure_client


async def fetch_context(
    query: str, model: Optional[str] = None, timeout: float = 3.0
) -> Optional[str]:
    """Call the Context_Handler service and return plain-text context.

    Returns None when the service is not configured or the call fails.
    An optional ``model`` filter can be forwarded to the Context_Handler so it
    can restrict results to documents relevant to a specific appliance model.
    """
    if not CONTEXT_HANDLER_URL or not CONTEXT_HANDLER_TOKEN:
        logging.debug("Context handler not configured; skipping fetch")
        return None

    headers = {
        "Authorization": f"Bearer {CONTEXT_HANDLER_TOKEN}",
        "Content-Type": "application/json",
    }
    payload: dict = {"query": query}
    if model:
        payload["model"] = model

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(CONTEXT_HANDLER_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            logging.warning(
                "Context handler returned status %s: %s", resp.status_code, resp.text
            )
            return None
        data = resp.json()
        context = data.get("context")
        if context is None:
            logging.debug("Context handler returned no 'context' field")
            return None
        if isinstance(context, list):
            return "\n\n".join(map(str, context))
        return str(context)
    except Exception as exc:
        logging.warning("Error fetching context: %s", exc)
        return None


# ---------------------------------------------------------------------------
# System prompt  (formerly api.py)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt"
if _SYSTEM_PROMPT_PATH.exists():
    _SYSTEM_PROMPT = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
else:
    _SYSTEM_PROMPT = "You are a helpful field service assistant."

# Simple in-memory session store
_sessions: dict[str, list[dict]] = {}


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str
    sessionId: str
    model: str | None = None


class SessionInitRequest(BaseModel):
    sessionId: str


# ---------------------------------------------------------------------------
# FastAPI application  (formerly server.py)
# ---------------------------------------------------------------------------

app = FastAPI(title="Field-Service RAG Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_clients()


# ---------------------------------------------------------------------------
# Endpoints  (formerly api.py)
# ---------------------------------------------------------------------------


@app.post("/api/session/init")
async def session_init(req: SessionInitRequest):
    if req.sessionId not in _sessions:
        _sessions[req.sessionId] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    return {"status": "ok", "sessionId": req.sessionId}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    client = get_azure_client()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")

    if client is None or not deployment:
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

    # Fetch RAG context if available
    try:
        context_text = await fetch_context(req.message, model=req.model, timeout=3.0)
    except Exception:
        context_text = None

    # Replace previous context message instead of accumulating
    if context_text:
        context_msg = {"role": "system", "content": f"Retrieved context:\n{context_text}"}
        if len(history) > 1 and history[1].get("content", "").startswith("Retrieved context:"):
            history[1] = context_msg
        else:
            history.insert(1, context_msg)

    history.append({"role": "user", "content": req.message})

    logging.debug(
        "LLM request messages (full history):\n%s",
        json.dumps(history, ensure_ascii=False, indent=2),
    )

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


# ---------------------------------------------------------------------------
# Dev entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
