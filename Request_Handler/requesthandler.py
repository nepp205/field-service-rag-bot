#Zusammenarbeit von Niklas und Tobias, verfeinert mit GitHub Copilot
#import alle bibliotheken
import os
import logging
from pathlib import Path
import json
import httpx
from typing import Optional
from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI, HTTPException
from openai import AzureOpenAI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware



from dotenv import load_dotenv
load_dotenv(override=True) #umgebungsvariablen laden


##umgebungsvariablen definieren
#
MAX_TOKENS = 100 #maximale länge der antwort (token sparen)

#verbindung zu marvins context handler
CONTEXT_HANDLER_URL = os.getenv("CONTEXT_HANDLER_URL")
CONTEXT_HANDLER_TOKEN = os.getenv("CONTEXT_HANDLER_TOKEN")



_SYSTEM_PROMPT_PATH = Path(__file__).parent / "system_prompt.txt" #systemprompt laden
_SYSTEM_PROMPT = "You are a helpful field service assistant." #fallback, wenns system prompt nicht gibt

if _SYSTEM_PROMPT_PATH.is_file():
    _SYSTEM_PROMPT = _SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip() #systemprompt aus datei lesen

_history: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}] #globale variable für die konversation, startet mit system prompt

json_filled=False # flag ob json für context handler gefüllt ist

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
  



#json handling -> Form muss ausgefüllt sein aus llm sonst kein kontext handler
with open('form.json', 'r', encoding='utf-8') as form:
    json_form = json.load(form)

def test_json():
    global json_filled
    if json_form["problem"] != "" and json_form["product_model_name"] !="" and json_form["error_code"]!="":
        json_filled = True
    else:
        json_filled = False

""" print(json_form,json_filled)
test_json()
json_form['problem'] = "problem123"
print(json_form)
test_json()
print(json_form,json_filled)
json_form['product_model_name'] = "model123"
json_form['error_code'] = "error123"
test_json()
print(json_form,json_filled) """

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
                    "problem": {"type": "string","description": "Short description of the problem the user is facing.No errorcodes or product model names, just a short problem description."},
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




async def fetch_context(query: str, model: Optional[str] = None, timeout: float = 20.0, retries: int = 2) -> Optional[str]:
    # context von marvins context handler holen (mit Retries + grösserem Timeout)
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

    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                print("Calling Context_Handler", CONTEXT_HANDLER_URL, "with payload:", payload)
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

            if isinstance(context, list):
                context = "\n\n".join(map(str, context))
            else:
                context = str(context)

            logging.debug("Retrieved context length=%d", len(context))
            return context

        except (httpx.ReadTimeout, httpx.ConnectError) as exc:
            logging.warning("Context handler request failed (attempt %d/%d): %s", attempt + 1, retries + 1, exc, exc_info=True)
            if attempt < retries:
                await asyncio.sleep(1 + attempt * 1.5)
                continue
            return None
        except Exception as exc:
            logging.warning("Unexpected error fetching context (%s): %r", type(exc).__name__, exc, exc_info=True)
            return None


async def test_context_handler_connection(timeout: float = 3.0) -> dict:
    """Quick connectivity test for the Context Handler.

    Returns a dict with keys:
      - ok: bool
      - status_code: int|None
      - detail: short message
      - response: decoded JSON or raw text when available

    This is safe to call during startup or at runtime to verify the
    CONTEXT_HANDLER_URL and CONTEXT_HANDLER_TOKEN are reachable and
    returning a valid response.
    """
    if not CONTEXT_HANDLER_URL:
        return {"ok": False, "status_code": None, "detail": "CONTEXT_HANDLER_URL not set"}
    print("Context handler URL:", CONTEXT_HANDLER_URL)
    print("Context handler token:", CONTEXT_HANDLER_TOKEN)
    if not CONTEXT_HANDLER_TOKEN:
        return {"ok": False, "status_code": None, "detail": "CONTEXT_HANDLER_TOKEN not set"}

    headers = {
        "Authorization": f"Bearer {CONTEXT_HANDLER_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"query": "__health_check__"}

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(CONTEXT_HANDLER_URL, headers=headers, json=payload)

        # try to decode JSON response, fall back to text
        try:
            content = resp.json()
        except Exception:
            content = resp.text

        if resp.status_code == 200:
            return {"ok": True, "status_code": resp.status_code, "detail": "OK", "response": content}
        else:
            print("hierist der fehler")
            return {"ok": False, "status_code": resp.status_code, "detail": "Non-200 from context handler", "response": content}

    except Exception as exc:
        print("Context handler connectivity test failed: %s", exc)
        return {"ok": False, "status_code": None, "detail": str(exc)}


def test_context_handler_connection_sync(timeout: float = 3.0) -> dict:
    """Synchronous wrapper to run the async connectivity test locally.

    Use this when running the module directly (no FastAPI server). It
    executes the async test with asyncio.run and returns the result dict.
    """
    import asyncio
    return asyncio.run(test_context_handler_connection(timeout=timeout))


if __name__ == "__main__":
    # When executed directly we want a simple local test (no API).
    result = test_context_handler_connection_sync()
    try:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception:
        # fallback to plain print if JSON serialization fails
        print(result)


@app.post("/api/session/init", response_model=SessionInitResponse) #post endpunkt für neue session
async def session_init(req: SessionInitRequest) -> SessionInitResponse:
    global _history
    _history = [{"role": "system", "content": _SYSTEM_PROMPT}] #systemprompt zur history hinzufügen, damit llm immer lesen kann
    json_form["problem"] = "" #json form zurücksetzen
    json_form["product_model_name"] = ""
    json_form["error_code"] = ""
    json_filled = False
    print("Session initialised/reset: %s", req.sessionId)
    return SessionInitResponse(status="ok", sessionId=req.sessionId)


@app.post("/api/chat", response_model=ChatResponse) #post endpunkt für chat anfragen
async def chat(req: ChatRequest) -> ChatResponse:
   
    if _azure_client is None: #fallback wenn azure client nicht konfiguriert ist
        raise HTTPException(
            status_code=503,
            detail="Azure OpenAI client not configured. Set AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY and AZURE_OPENAI_DEPLOYMENT.",
        )

    history = _history #vaible für die konversation, startet mit system prompt, wird bei jeder anfrage erweitert


    #user prompt an history anhängen (aus frontend)
    history.append({"role": "user", "content": req.message})
    print(history)


    print(_history)
    #llm anfragen
    try:
        if not json_filled: #wenn json form nicht gefüllt ist, llm mit tools anfragen, damit es die form ausfüllen kann (wenn nötig)
            first = _azure_client.chat.completions.create(
                model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                messages=history,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=MAX_TOKENS,
                temperature=0,
            )
            print(first)
            message = first.choices[0].message
            answer = message.content or ""

            if message.tool_calls:
                history.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": message.tool_calls
                })
                print("history nach first call:", history)
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
                print("history nach tool call:", history)
                if json_filled:
                    try:
                        print("JSON form filled, fetching context with query:", req.message)
                        print("Current JSON form state:", req.model)
                        context_text = await fetch_context(req.message, model=req.model)

                        print("Context Handler called\n ", context_text)
                    except Exception as e:
                        logging.warning("Error while fetching context: %s", e)
                        context_text = None

                    if context_text:
                        history.insert(1, {
                            "role": "system",
                            "content": f"Retrieved context:\n{context_text}"
                        })

                print("history vor second call:", history)
                second = _azure_client.chat.completions.create(
                    model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                    messages=history,
                    max_tokens=MAX_TOKENS,
                    temperature=0,
                )

                answer = second.choices[0].message.content or "Okay"
            else:
                answer = message.content or "Okay"

        else:
            normal = _azure_client.chat.completions.create(
                model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                messages=history,
                max_tokens=MAX_TOKENS,
                temperature=0,
            )
            answer = normal.choices[0].message.content or "Okay"

        history.append({"role": "assistant", "content": answer})
        return ChatResponse(answer=answer)
            
    except Exception as e:
        logging.error("AZURE FEHLER: %s", str(e), exc_info=True)
        return ChatResponse(answer=f"Interner Fehler: {type(e).__name__}")

