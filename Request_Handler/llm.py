#This module provides three small utilities used by the request handler:

#- init_clients(): create an AzureOpenAI client from environment variables.
#- fetch_context(): optional call to an external Context_Handler service.
#- get_azure_client(): return the initialized Azure client.
 
import os
import logging
import httpx
from typing import Optional
from openai import AzureOpenAI, OpenAIError

# Load .env when present (development convenience)
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

# Simple configuration constants
MAX_TOKENS = 100
CONTEXT_HANDLER_URL = os.getenv("CONTEXT_HANDLER_URL", "http://localhost:5000/context")
CONTEXT_HANDLER_TOKEN = os.getenv("CONTEXT_HANDLER_TOKEN")

# Internal client holder
_azure_client: Optional[AzureOpenAI] = None


# Initialize the Azure OpenAI clients

def init_clients() -> None:
   # Initialize the Azure OpenAI client
    global _azure_client
    #env variables
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    api_key = os.getenv("AZURE_OPENAI_API_KEY")
    api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")

    try:
        _azure_client = AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)
        logging.info("Azure OpenAI client initialized (endpoint=%s, api_version=%s)", endpoint, api_version)
    except Exception as exc:
        logging.exception("Failed to initialize Azure OpenAI client: %s", exc)
        _azure_client = None





async def fetch_context(query: str, timeout: float = 3.0) -> Optional[str]:
    """Call the Context_Handler service and return a plain text context.

    If the service is not configured (no token or URL) this returns None.
    """
    if not CONTEXT_HANDLER_URL or not CONTEXT_HANDLER_TOKEN:
        logging.debug("Context handler not configured; skipping fetch")
        return None

    headers = {"Authorization": f"Bearer {CONTEXT_HANDLER_TOKEN}", "Content-Type": "application/json"}
    payload = {"query": query}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(CONTEXT_HANDLER_URL, headers=headers, json=payload)
        if resp.status_code != 200:
            logging.warning("Context handler returned status %s: %s", resp.status_code, resp.text)
            return None
        data = resp.json()
        context = data.get("context")
        if context is None:
            logging.debug("Context handler returned no 'context' field")
            return None
        # Normalise to single string
        if isinstance(context, list):
            return "\n\n".join(map(str, context))
        return str(context)
    except Exception as exc:
        logging.warning("Error fetching context: %s", exc)
        return None


def get_azure_client() -> Optional[AzureOpenAI]:
    """Callers should check for None and surface a 503/appropriate error if
    the client is not configured.
    """
    return _azure_client

