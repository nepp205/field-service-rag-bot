"""LLM client initialisation, prompt optimisation, and context fetching.

Provides:
- ``init_clients()``  – called once at startup to create AzureOpenAI clients.
- ``optimize_prompt(raw)``  – optional pre-flight rewrite via a lightweight model.
- ``fetch_context(query, model, timeout)``  – retrieves context from the Context_Handler service.
- Module-level constants: ``MAX_TOKENS``, ``REWRITE_MAX_TOKENS``.
"""

import json
import logging
import os
from typing import Optional

import httpx
from openai import AzureOpenAI, OpenAIError

# Optional: load a local .env when developing locally (install python-dotenv)
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

MAX_TOKENS = 100
REWRITE_MAX_TOKENS = 150

# Context Handler config (optional). If not set, context lookup is skipped.
CONTEXT_HANDLER_URL = "http://localhost:5000/context"
CONTEXT_HANDLER_TOKEN = os.environ.get("CONTEXT_HANDLER_TOKEN")

_REWRITE_SYSTEM_INSTRUCTION = (
    "You are a prompt-optimisation assistant for a Miele field-service chatbot. "
    "Your only job is to rewrite the technician's message so it is grammatically "
    "correct, clearly phrased, and well-suited for a technical documentation search. "
    "Rules:\n"
    "1. Fix all spelling and grammar mistakes.\n"
    "2. Rephrase fragments or vague notes as a precise, answerable question.\n"
    "3. Preserve all technical terms, model numbers, error codes, and part names "
    "exactly as written (e.g. F67, W1, PCB, NTC, G7310).\n"
    "4. Do NOT answer the question – return only the improved prompt.\n"
    "5. Return only the rewritten message, no explanations or meta-commentary."
)

_azure_client: Optional[AzureOpenAI] = None
_rewrite_client: Optional[AzureOpenAI] = None


def init_clients() -> None:
    """Initialise AzureOpenAI clients from environment variables.

    Should be called once during application startup.
    """
    global _azure_client, _rewrite_client

    missing = [
        v
        for v in (
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
            "AZURE_OPENAI_DEPLOYMENT",
        )
        if not os.environ.get(v)
    ]
    if missing:
        logging.warning(
            "Missing required environment variable(s): %s. "
            "Server will start but /api/chat will return 503 until set.",
            ", ".join(missing),
        )
    else:
        _azure_client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version="2024-02-01",
        )
        logging.info("Azure OpenAI client initialized.")

    rewrite_vars = (
        "AZURE_REWRITE_ENDPOINT",
        "AZURE_REWRITE_API_KEY",
        "AZURE_REWRITE_DEPLOYMENT",
    )
    missing_rewrite = [v for v in rewrite_vars if not os.environ.get(v)]
    if missing_rewrite:
        logging.warning(
            "Prompt optimisation disabled – missing rewrite env var(s): %s.",
            ", ".join(missing_rewrite),
        )
    else:
        _rewrite_client = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_REWRITE_ENDPOINT"],
            api_key=os.environ["AZURE_REWRITE_API_KEY"],
            api_version="2024-02-01",
        )
        logging.info(
            "Azure OpenAI rewrite client initialized (deployment: %s).",
            os.environ["AZURE_REWRITE_DEPLOYMENT"],
        )


def optimize_prompt(raw: str) -> str:
    """Rewrite *raw* with the lightweight rewrite model, or return it unchanged."""
    if _rewrite_client is None:
        return raw

    try:
        messages = [
            {"role": "system", "content": _REWRITE_SYSTEM_INSTRUCTION},
            {"role": "user", "content": raw},
        ]
        logging.debug(
            "Rewrite model request | endpoint=%s deployment=%s\n%s",
            os.environ.get("AZURE_REWRITE_ENDPOINT"),
            os.environ.get("AZURE_REWRITE_DEPLOYMENT"),
            json.dumps(messages, ensure_ascii=False, indent=2),
        )

        result = _rewrite_client.chat.completions.create(
            model=os.environ["AZURE_REWRITE_DEPLOYMENT"],
            messages=messages,
            max_tokens=REWRITE_MAX_TOKENS,
            temperature=0.0,
        )
        optimized = (result.choices[0].message.content or "").strip()
        logging.debug("Rewrite model response: %r", optimized)
        if not optimized:
            logging.warning(
                "Rewrite model returned empty response – using original message."
            )
            return raw
        logging.info(
            "Prompt optimised | original=%r | optimised=%r", raw, optimized
        )
        return optimized
    except OpenAIError as exc:
        logging.warning(
            "Prompt optimisation failed (%s) – using original message.", exc
        )
        return raw


async def fetch_context(
    query: str, model: Optional[str] = None, timeout: float = 3.0
) -> Optional[str]:
    """Call the external Context_Handler HTTP service to retrieve relevant context.

    Returns the context string on success or ``None`` on error / if service not configured.
    """
    if not CONTEXT_HANDLER_URL or not CONTEXT_HANDLER_TOKEN:
        logging.debug(
            "Context handler not configured (URL/token missing) – skipping context fetch."
        )
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
            logging.debug(
                "Calling Context_Handler %s with payload: %s",
                CONTEXT_HANDLER_URL,
                payload,
            )
            resp = await client.post(CONTEXT_HANDLER_URL, headers=headers, json=payload)
        logging.debug("Context_Handler response status: %s", resp.status_code)
        if resp.status_code != 200:
            logging.warning(
                "Context handler returned non-200 status %s: %s",
                resp.status_code,
                resp.text,
            )
            return None
        data = resp.json()
        context = data.get("context")
        if context is None:
            logging.warning(
                "Context handler response missing 'context' field: %s", data
            )
            return None
        if isinstance(context, list):
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


def get_azure_client() -> Optional[AzureOpenAI]:
    """Return the main AzureOpenAI client (may be None if not configured)."""
    return _azure_client
