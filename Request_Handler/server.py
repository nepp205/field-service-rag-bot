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

# setup logging to stdout
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s", stream=sys.stdout)

# startup: initialise Azure OpenAI client once
app = FastAPI(title="Field-Service RAG Bot API")


# call init_clients() when the server starts
@app.on_event("startup")
def on_startup():
    init_clients()

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


# dev: run with `python server.py` (reload for development)
if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
