# Zusammenarbeit von Niklas und Tobias, verfeinert mit GitHub Copilot
import os
import logging
import json
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import AzureOpenAI
from pydantic import BaseModel

load_dotenv(override=True)  # .env laden

# --- Konstanten ---
MAX_TOKENS = 10000  # antwortlänge begrenzen
CONTEXT_HANDLER_URL = os.getenv("CONTEXT_HANDLER_URL")  # url zum context handler
CONTEXT_HANDLER_TOKEN = os.getenv("CONTEXT_HANDLER_TOKEN")  # auth token
CONTEXT_PREFIX = "Retrieved context:\n"  # präfix für kontext-nachrichten in history
CONTEXT_MARKERS = ("Retrieved context:\n", "Retrieved context:", "Context:\n")  # erkennungsmarker

# --- System-Prompt laden ---
_prompt_path = Path(__file__).parent / "system_prompt.txt"
_SYSTEM_PROMPT = _prompt_path.read_text(encoding="utf-8").strip() if _prompt_path.is_file() \
    else "You are a helpful field service assistant."  # fallback

# --- Globaler Zustand ---
_azure_client: AzureOpenAI | None = None  # wird beim startup gesetzt
_history: list[dict] = [{"role": "system", "content": _SYSTEM_PROMPT}]  # gesprächsverlauf
json_filled = False  # flag: formular vollständig ausgefüllt?

# --- Formular aus Datei laden ---
with open("form.json", "r", encoding="utf-8") as _f:
    json_form = json.load(_f)  # problem, modell, fehlercode


# --- Startup / Shutdown ---
@asynccontextmanager
async def lifespan(app):  # fastapi lifecycle hook
    global _azure_client
    _azure_client = AzureOpenAI(
        azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version="2024-02-01",
    )
    logging.info("Azure OpenAI client gestartet.")
    yield  # ab hier anfragen annehmen


# --- Hilfsfunktionen Formular ---
def _update_json_filled() -> None:
    global json_filled
    # alle drei felder müssen befüllt sein
    json_filled = all(json_form.get(k, "") for k in ("problem", "product_model_name", "error_code"))


def fill_json_form(problem: str, product_model_name: str, error_code: str) -> bool:
    """Formular befüllen, gibt True zurück wenn sich etwas geändert hat."""
    prev = (json_form.get("problem", ""), json_form.get("product_model_name", ""), json_form.get("error_code", ""))
    json_form["problem"] = problem.strip()
    json_form["product_model_name"] = product_model_name.strip()
    json_form["error_code"] = error_code.strip()
    _update_json_filled()
    return (json_form["problem"], json_form["product_model_name"], json_form["error_code"]) != prev


def _persist_form() -> None:
    with open("form.json", "w", encoding="utf-8") as f:
        json.dump(json_form, f, ensure_ascii=False, indent=2)  # formular speichern


# --- Hilfsfunktionen History/Kontext ---
def _has_context(history: list[dict]) -> bool:
    return any(
        m.get("role") == "system" and isinstance(m.get("content"), str)
        and m["content"].startswith(CONTEXT_MARKERS)
        for m in history
    )  # prüft ob kontext bereits in history ist


def _upsert_context(history: list[dict], context_text: str) -> None:
    # alten kontext entfernen und neuen einfügen (nach system-prompt)
    history[:] = [
        m for m in history
        if not (m.get("role") == "system" and isinstance(m.get("content"), str)
                and m["content"].startswith(CONTEXT_MARKERS))
    ]
    insert_at = 1 if history and history[0].get("role") == "system" else 0
    history.insert(insert_at, {"role": "system", "content": f"{CONTEXT_PREFIX}{context_text}"})


def _build_context_query(user_message: str) -> str:
    if json_filled:  # formular-daten als suchanfrage nutzen wenn vorhanden
        return (
            f"Problem: {json_form['problem']}\n"
            f"Product model name: {json_form['product_model_name']}\n"
            f"Error code: {json_form['error_code']}"
        )
    return user_message  # sonst direkt die nutzerfrage


# --- Context Handler anfragen ---
async def fetch_context(query: str, model: str | None = None, timeout: float = 200.0, retries: int = 2) -> str | None:
    if not CONTEXT_HANDLER_URL or not CONTEXT_HANDLER_TOKEN:
        return None  # nicht konfiguriert, überspringen

    headers = {"Authorization": f"Bearer {CONTEXT_HANDLER_TOKEN}", "Content-Type": "application/json"}
    payload = {"query": query}
    if model:
        payload["model"] = model

    for attempt in range(retries + 1):
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                logging.debug("Context Handler anfragen: %s", CONTEXT_HANDLER_URL)
                resp = await client.post(CONTEXT_HANDLER_URL, headers=headers, json=payload)

            if resp.status_code != 200:
                logging.warning("Context Handler status %s: %s", resp.status_code, resp.text)
                return None

            data = resp.json()
            context = data.get("context")
            if context is None:
                logging.warning("Kein 'context' Feld in Antwort: %s", data)
                return None

            # liste zu text zusammenfügen falls nötig
            context = "\n\n".join(map(str, context)) if isinstance(context, list) else str(context)
            logging.debug("Kontext erhalten, länge=%d", len(context))
            return context

        except (httpx.ReadTimeout, httpx.ConnectError) as exc:
            logging.warning("Context Handler Fehler (versuch %d/%d): %s", attempt + 1, retries + 1, exc)
            if attempt < retries:
                await asyncio.sleep(1 + attempt * 1.5)  # kurz warten, dann nochmal
        except Exception as exc:
            logging.warning("Unerwarteter Fehler beim Kontext holen: %r", exc)
            return None
    return None


# --- Tool-Definition für LLM ---
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "fill_json_form",
            "description": "Fill the JSON form with problem, product model name and error code from the user message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "problem": {"type": "string", "description": "Short description of the problem the user is facing."},
                    "product_model_name": {"type": "string", "description": "Exact or best product model name."},
                    "error_code": {"type": "string", "description": "Error code associated with the problem."},
                },
                "required": ["problem", "product_model_name", "error_code"],
                "additionalProperties": False,
            },
        },
    }
]

# --- FastAPI App ---
app = FastAPI(title="Field-Service RAG Bot API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # alle origins erlauben (entwicklung)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Datenmodelle ---
class ChatRequest(BaseModel):  # eingehende chat-anfrage
    message: str
    sessionId: str
    model: str | None = None  # optionales modell für context handler


class ChatResponse(BaseModel):  # antwort des bots
    answer: str


class SessionInitRequest(BaseModel):  # anfrage zum sitzungsstart
    sessionId: str


class SessionInitResponse(BaseModel):  # antwort auf sitzungsstart
    status: str
    sessionId: str


# --- Endpunkte ---
@app.post("/api/session/init", response_model=SessionInitResponse)
async def session_init(req: SessionInitRequest) -> SessionInitResponse:
    global _history, json_filled, json_form
    _history = [{"role": "system", "content": _SYSTEM_PROMPT}]  # history zurücksetzen

    # formular leeren
    json_form["problem"] = json_form["product_model_name"] = json_form["error_code"] = ""
    json_filled = False

    try:
        _persist_form()  # datei synchron halten
    except Exception:
        logging.exception("form.json konnte nicht gespeichert werden")

    logging.info("Sitzung zurückgesetzt: %s", req.sessionId)
    return SessionInitResponse(status="ok", sessionId=req.sessionId)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if _azure_client is None:  # sollte nicht passieren, aber sicherheitshalber
        raise HTTPException(status_code=503, detail="Azure OpenAI client nicht verfügbar.")

    history = _history
    history.append({"role": "user", "content": req.message})  # nutzernachricht anhängen

    try:
        # erste LLM-anfrage (mit tool-aufruf möglich)
        first = _azure_client.chat.completions.create(
            model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
            messages=history,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=MAX_TOKENS,
            temperature=0,
        )

        message = first.choices[0].message
        form_changed = False

        if message.tool_calls:
            history.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": message.tool_calls,
            })

            for tool_call in message.tool_calls:
                if tool_call.function.name == "fill_json_form":
                    args = json.loads(tool_call.function.arguments)
                    changed = fill_json_form(
                        problem=args.get("problem", ""),
                        product_model_name=args.get("product_model_name", ""),
                        error_code=args.get("error_code", ""),
                    )
                    form_changed = form_changed or changed

                history.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps({"status": "ok"}),
                })

            if form_changed:
                try:
                    _persist_form()  # geänderte werte speichern
                except Exception:
                    logging.exception("form.json konnte nach update nicht gespeichert werden")

        # kontext neu laden wenn formular geändert oder noch keiner in history
        if json_filled and (form_changed or not _has_context(history)):
            try:
                context_text = await fetch_context(_build_context_query(req.message), model=req.model)
            except Exception as e:
                logging.warning("Fehler beim Kontext holen: %s", e)
                context_text = None
            if context_text:
                _upsert_context(history, context_text)  # kontext in history einfügen

        if message.tool_calls:
            # zweite LLM-anfrage mit kontext und tool-ergebnis
            second = _azure_client.chat.completions.create(
                model=os.environ["AZURE_OPENAI_DEPLOYMENT"],
                messages=history,
                max_tokens=MAX_TOKENS,
                temperature=0,
            )
            answer = second.choices[0].message.content or "Okay"
        else:
            answer = message.content or "Okay"  # direkte antwort ohne tool-aufruf

        history.append({"role": "assistant", "content": answer})
        return ChatResponse(answer=answer)

    except Exception as e:
        logging.error("Azure Fehler: %s", str(e), exc_info=True)
        return ChatResponse(answer=f"Interner Fehler: {type(e).__name__}")
