# src/rag_app.py
import os
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import FakeEmbeddings
from langchain.prompts import PromptTemplate

# ---------- Azure: Deployment-Namen aus deinem Azure AI Foundry Projekt ----------
CHAT_DEPLOYMENT = "gpt4omini"        # <== anpassen an deine Deployments
EMBED_DEPLOYMENT = "textembedding"   # <== anpassen an deine Deployments

# ---------- Azure LLM Clients ----------
llm = AzureChatOpenAI(
    api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
    deployment_name=CHAT_DEPLOYMENT,
    temperature=0,
)

embedder = AzureOpenAIEmbeddings(
    api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
    azure_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
    model=EMBED_DEPLOYMENT,
)

# ---------- Retriever (Dummy, bis Marvin DB liefert) ----------
USE_DUMMY_DB = True

if USE_DUMMY_DB:
    fake = FakeEmbeddings(size=768)
    vectorstore = Chroma.from_texts(
        texts=[
            "Fehler E-404: Wassereinlaufproblem.",
            "Pumpe defekt: Flusensieb reinigen und Laugenpumpe prüfen.",
            "Trockner Fehler E13: Luftkanal blockiert oder Filter verschmutzt.",
            "Waschmaschine vibriert: Gerät ausrichten, Transportsicherungen prüfen.",
            "Wasser zieht nicht ein: Aquastop prüfen, Zulaufsieb reinigen."
        ],
        embedding=fake,
        collection_name="field_service",
        persist_directory="./data/chroma_dummy_db"
    )
else:
    vectorstore = Chroma(
        collection_name="field_service",
        persist_directory="./data/chroma_db",
        embedding_function=embedder
    )

retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

# ---------- Prompt ----------
TECH_PROMPT = """
Du bist ein professioneller Field-Service-Techniker.
Antworte IMMER als nummerierte Schritt-für-Schritt-Anleitung.
Nutze ausschließlich den bereitgestellten Kontext. Keine Halluzinationen!

Frage:
{question}

Kontext:
{context}

Antwort:
1)
2)
3)
"""

prompt = PromptTemplate(
    input_variables=["question", "context"],
    template=TECH_PROMPT
)

# ---------- Kernfunktion (API für UI) ----------
def rag_answer(question: str) -> dict:
    docs = retriever.get_relevant_documents(question)
    context = "\n---\n".join(d.page_content for d in docs)

    filled = prompt.format(question=question, context=context)
    answer = llm.invoke(filled)

    sources = [{"snippet": d.page_content[:200]} for d in docs]
    return {"answer": answer, "sources": sources}

# ---------- Optional: Conversation Memory ----------
_chat_memory: dict[str, list[tuple[str, str]]] = {}

def rag_answer_with_memory(question: str, chat_id: str = "default") -> dict:
    history = ""
    turns = _chat_memory.get(chat_id, [])
    if turns:
        history = "\n".join([f"U:{u}\nA:{a}" for u, a in turns])

    docs = retriever.get_relevant_documents(question)
    context = "\n---\n".join(d.page_content for d in docs)

    prompt_with_memory = f"""
Du bist ein professioneller Field-Service-Techniker.
Berücksichtige den bisherigen Chatverlauf.

Chatverlauf:
{history}

Frage:
{question}

Kontext:
{context}

Antwort:
1)
2)
3)
"""
    answer = llm.invoke(prompt_with_memory)
    _chat_memory.setdefault(chat_id, []).append((question, answer))
    return {"answer": answer, "memory_len": len(_chat_memory[chat_id])}

# ---------- Mini-Tests ----------
if __name__ == "__main__":
    tests = [
        "Fehler E-404 Waschmaschine?",
        "Pumpe defekt – wie gehe ich vor?",
        "Trockner zeigt Fehler E13?",
        "Was tun bei starken Vibrationen?",
        "Wasser zieht nicht ein – mögliche Ursachen?"
    ]
    for q in tests:
        print("TEST:", q)
        res = rag_answer(q)
        print(res["answer"])
        print("-" * 60)