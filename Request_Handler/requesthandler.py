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

JSON_FILLED=False # flag ob json für context handler gefüllt ist

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
    json_form
    JSON_FILLED=False



#json handling -> Form muss ausgefüllt sein aus llm sonst kein kontext handler
with open('form.json', 'r', encoding='utf-8') as form:
    json_form = json.load(form)

def test_json():
    global JSON_FILLED
    if json_form["problem"] != "" and json_form["product_model_name"] !="" and json_form["error_code"]!="":
        JSON_FILLED = True
    else:
        JSON_FILLED = False

""" print(json_form,JSON_FILLED)
test_json()
json_form['problem'] = "problem123"
print(json_form)
test_json()
print(json_form,JSON_FILLED)
json_form['product_model_name'] = "model123"
json_form['error_code'] = "error123"
test_json()
print(json_form,JSON_FILLED) """

_history.append({
    "role": "system",
    "content": "If the user provides problem, product model name or error code, call the tool fill_json_form."
})
print(_history)

def fill_json_form(problem: str, product_model_name: str, error_code: str):
    global json_form
    json_form["problem"] = problem.strip()
    json_form["product_model_name"] = product_model_name.strip()
    json_form["error_code"] = error_code.strip()
    test_json()

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fill_json_form",
            "description": "Fill the JSON form with problem, product model name and error code from the user message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem": {"type": "string","description": "Short description of the problem the user is facing."},
                    "product_model_name": {"type": "string","description":"Exact or best product model name."},
                    "error_code": {"type": "string","description":"Error code associated with the problem."},
                },
                "required": ["problem", "product_model_name", "error_code"],
                "additionalProperties": False,
            },
        },
    }
]

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
    if JSON_FILLED==True:
        try:
            context_text = await fetch_context(req.message, model=req.model)
            print("Context Handler called")
        except Exception as e:
            logging.warning("Error while fetching context: %s", e)
            context_text = None

        if context_text:
            history.insert(1, {"role": "system", "content": f"Retrieved context:\n{context_text}"})#context an histroy hängen für llm

    #user prompt an history anhängen (aus frontend)
    history.append({"role": "user", "content": req.message})
    print(_history)
    #llm anfragen
    try:
        if not JSON_FILLED:
            first = _azure_client.chat.completions.create(
                model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                messages=history,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=MAX_TOKENS,
            )

            message = first.choices[0].message
            answer = message.content or ""

            if message.tool_calls:
                history.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": message.tool_calls
                })

                for tool_call in message.tool_calls:
                    if tool_call.function.name == "fill_json_form":
                        args = json.loads(tool_call.function.arguments)

                        fill_json_form(
                            problem=args.get("problem", ""),
                            product_model_name=args.get("product_model_name", ""),
                            error_code=args.get("error_code", ""),
                        )

                    history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": json.dumps({"status": "ok"})
                    })

                if JSON_FILLED:
                    try:
                        context_text = await fetch_context(req.message, model=req.model)
                        print("Context Handler called")
                    except Exception as e:
                        logging.warning("Error while fetching context: %s", e)
                        context_text = None

                    if context_text:
                        history.insert(1, {
                            "role": "system",
                            "content": f"Retrieved context:\n{context_text}"
                        })

                second = _azure_client.chat.completions.create(
                    model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                    messages=history,
                    max_tokens=MAX_TOKENS,
                )

                answer = second.choices[0].message.content or "Okay"
            else:
                answer = message.content or "Okay"

        else:
            normal = _azure_client.chat.completions.create(
                model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                messages=history,
                max_tokens=MAX_TOKENS,
            )
            answer = normal.choices[0].message.content or "Okay"

        history.append({"role": "assistant", "content": answer})
        return ChatResponse(answer=answer)
            
    except Exception as e:
        logging.error("AZURE FEHLER: %s", str(e), exc_info=True)
        return ChatResponse(answer=f"Interner Fehler: {type(e).__name__}")

