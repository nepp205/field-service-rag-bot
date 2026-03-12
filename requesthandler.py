from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# CORS erlauben, damit dein HTML/JS mit dem Backend sprechen darf
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # für Demo ok, später einschränken
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    sessionId: str

class ChatResponse(BaseModel):
    answer: str

@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    # HIER später: Vektor-DB + Azure LLM aufrufen
    demo_answer = f"Demo-Antwort für: {req.message}"
    return ChatResponse(answer=demo_answer)
