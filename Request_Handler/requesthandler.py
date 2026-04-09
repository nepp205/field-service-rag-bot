#Zusammenarbeit von Niklas und Tobias, verfeinert mit GitHub Copilot
#import alle bibliotheken
import os
import logging
from pathlib import Path
import json
import httpx
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from openai import AzureOpenAI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware


try:
    from dotenv import load_dotenv
    load_dotenv() #umgebungsvariablen laden
except Exception:
    pass

##umgebungsvariablen definieren
#
MAX_TOKENS = 100 #maximale länge der antwort (token sparen)

#verbindung zu marvins context handler
CONTEXT_HANDLER_URL = os.environ.get("CONTEXT_HANDLER_URL", "http://localhost:5000/context")
CONTEXT_HANDLER_TOKEN = os.environ.get("CONTEXT_HANDLER_TOKEN")

_SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt" #systemprompt laden
_SYSTEM_PROMPT = "You are a helpful field service assistant." #fallback, wenns system prompt nicht gibt

if _SYSTEM_PROMPT_PATH.is_file():
    _SYSTEM_PROMPT = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip() #systemprompt aus datei lesen

_history: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}] #globale variable für die konversation, startet mit system prompt

### fast api 

@asynccontextmanager
async def lifespan(app): #startup event definieren
    global _azure_client
    _azure_client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version="2024-02-01",
    )
    logging.info("Azure OpenAI client initialized.")
    
    yield #erst jetzt anfragen zulassen (startup abgeschlossen)
    

# fast api app für rest endpunkte (nutzt lifespan)
app = FastAPI(title="Field-Service RAG Bot API", lifespan=lifespan)
app.add_middleware( #anfragen von überall zulassen
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#schemen für die eingehenden und ausgehenden daten definieren
class ChatRequest(BaseModel): #standard anfrage
    message: str
    sessionId: str
    model: Optional[str] = None #später für context handler vielleicht ergänzen, jz noch nicht vorhanden

class ChatResponse(BaseModel): #antwort des bots
    answer: str


class SessionInitRequest(BaseModel): #anfrage für neue session
    sessionId: str


class SessionInitResponse(BaseModel): #antwort auf session anfrage
    status: str
    sessionId: str




async def fetch_context(query: str, model: Optional[str] = None, timeout: float = 3.0) -> Optional[str]: #context von marvins context handler holen
   #methode von github coplilot erstellt
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


@app.post("/api/session/init", response_model=SessionInitResponse) #post endpunkt für neue session
async def session_init(req: SessionInitRequest) -> SessionInitResponse:
    global _history
    _history = [{"role": "system", "content": _SYSTEM_PROMPT}] #systemprompt zur history hinzufügen, damit llm immer lesen kann
    logging.info("Session initialised/reset: %s", req.sessionId)
    return SessionInitResponse(status="ok", sessionId=req.sessionId)


@app.post("/api/chat", response_model=ChatResponse) #post endpunkt für chat anfragen
async def chat(req: ChatRequest) -> ChatResponse:
   
    if _azure_client is None: #fallback wenn azure client nicht konfiguriert ist
        raise HTTPException(
            status_code=503,
            detail="Azure OpenAI client not configured. Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT.",
        )

    history = _history #vaible für die konversation, startet mit system prompt, wird bei jeder anfrage erweitert

    #kontext handler anfragen
    try:
        context_text = await fetch_context(req.message, model=req.model)
    except Exception as e:
        logging.warning("Error while fetching context: %s", e)
        context_text = None

    if context_text:
        history.insert(1, {"role": "system", "content": f"Retrieved context:\n{context_text}"})#context an histroy hängen für llm

    #user prompt an history anhängen (aus frontend)
    history.append({"role": "user", "content": req.message})

    #llm anfragen
    try:
        completion = _azure_client.chat.completions.create(
            model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            messages=history,#ganze histroy als input geben-> immer im kontext anworten
            max_tokens=MAX_TOKENS,
        )
        answer = completion.choices[0].message.content or "" #antwort aus llm oder leer
        history.append({"role": "assistant", "content": answer})# antwort an history anhängen, damit sie bei der nächsten anfrage im kontext ist
        return ChatResponse(answer=answer)#antwort für frontend zurückgeben
    except Exception as e:
        logging.error("AZURE FEHLER: %s", str(e), exc_info=True)
        return ChatResponse(answer=f"Interner Fehler: {type(e).__name__}")

