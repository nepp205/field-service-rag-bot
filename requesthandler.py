"""FastAPI request handler for the Field-Service RAG Bot.

Exposes a single POST endpoint ``/api/chat`` that accepts a user message
together with a session ID and returns a plain-text answer.

The response is currently a demo stub; replace the body of ``chat()`` with
a call to the RAG pipeline (rag_core.RAG) and the Azure OpenAI LLM once
those components are ready.

Usage:
    uvicorn requesthandler:app --reload
"""

from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

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
    """Incoming chat message from the front-end."""

    message: str
    sessionId: str


class ChatResponse(BaseModel):
    """Outgoing chat answer returned to the front-end."""

    answer: str


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    """Handle a chat request and return an answer.

    Args:
        req: The incoming request containing the user's message and a
             session identifier for future multi-turn support.

    Returns:
        A ``ChatResponse`` with the generated answer string.

    TODO: Replace the demo stub below with a call to the RAG pipeline,
          e.g.::

              from rag_core import RAG
              rag = RAG()
              result = rag.answer(req.message)
              return ChatResponse(answer=result["content"])
    """
    # Demo stub – returns the user's message echoed back
    demo_answer = f"Demo-Antwort für: {req.message}"
    return ChatResponse(answer=demo_answer)
