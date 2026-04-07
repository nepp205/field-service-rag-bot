"""FastAPI application entry-point for the Field-Service RAG Bot.

Start modes:
  Dev:       python server.py          (or press F5 in VS Code)
  Prod-like: cd Request_Handler && gunicorn -k uvicorn.workers.UvicornWorker server:app \\
                 -b 0.0.0.0:8000 --access-logfile - --error-logfile -
"""

import logging
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import router
from llm import init_clients

# ---------------------------------------------------------------------------
# Logging – stdout-friendly, visible in terminal and container logs.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    stream=sys.stdout,
)
for _name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(_name).setLevel(logging.DEBUG)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------
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

app.include_router(router)


@app.on_event("startup")
async def startup_event() -> None:
    """Initialise Azure OpenAI clients on application startup."""
    init_clients()


# ---------------------------------------------------------------------------
# Dev server entry-point (F5 / python server.py)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
