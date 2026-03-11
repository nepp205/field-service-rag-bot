"""RAG-Integration (Phase-1 stub).

Dieses Modul stellt `get_rag_response(query, thread_id)` bereit. Tobias:
- Ersetze die In-Memory/Stub-Implementierung durch eure LangChain-Chain.
- Erwartetes Rückgabeformat: dict {content: str (Markdown), source_quote: str, pdf_url: str}

Das Stub nutzt `rag_core.RAG` falls vorhanden (SimpleLLM + InMemoryRetriever),
ansonsten fällt es auf eine einfache Regel-Map zurück.
"""

from typing import Dict, Any, Optional

try:
    # Wenn rag_core vorhanden ist, nutze RAG
    from rag_core import RAG, InMemoryRetriever, SimpleLLM  # type: ignore
    _HAS_RAG_CORE = True
except Exception:
    RAG = None  # type: ignore
    InMemoryRetriever = None  # type: ignore
    SimpleLLM = None  # type: ignore
    _HAS_RAG_CORE = False


def _fallback_response(query: str) -> Dict[str, Any]:
    """Fallback: einfache Mapping wie in der UI-Demo."""
    mapping = {
        "e-404": "Überhitzung - Kühler reinigen",
        "e-500": "Sensor defekt - austauschen",
        "druck": "Druckventil kalibrieren",
    }
    t = query.lower()
    diagnosis = "Allgemeine Wartung"
    for k, v in mapping.items():
        if k in t:
            diagnosis = v
            break

    content = (
        f"**DIAGNOSE: {diagnosis.upper()}**\n\n"
        "**📋 HANDLUNGSPLAN:**\n"
        "1. **Sicherheit**: Strom trennen\n"
        f"2. **Prüfung**: {diagnosis}\n"
        "3. **Test**: Neustart + Funktionstest\n"
        "4. **Doku**: Siehe Quelle unten\n\n"
        "**⏱️ Dauer**: 15-30 Minuten\n"
        "**✅ Status**: Wartung abgeschlossen\n"
    )
    source_quote = f"{diagnosis} - Standardverfahren"
    pdf_url = "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf"
    return {"content": content, "source_quote": source_quote, "pdf_url": pdf_url}


def get_rag_response(query: str, thread_id: Optional[str] = None, top_k: int = 3) -> Dict[str, Any]:
    """Hauptfunktion, die vom Frontend aufgerufen wird.

    Versucht, `rag_core.RAG` zu verwenden; wenn nicht vorhanden, liefert sie fallback.
    Tobias: ersetzt diese Implementierung durch einen Aufruf eurer LangChain-Chains,
    die `query` und `thread_id` verwenden können (Kontext, Conversation-ID etc.).
    """
    if _HAS_RAG_CORE:
        try:
            llm = None
            try:
                llm = SimpleLLM()
            except Exception:
                llm = None
            rag = RAG(retriever=InMemoryRetriever(), llm=llm)
            return rag.answer(query)
        except Exception:
            # Falls rag_core existiert, aber etwas schief geht, fallen wir zurück
            return _fallback_response(query)

    # Kein rag_core verfügbar -> Fallback
    return _fallback_response(query)


    if _HAS_RAG_CORE:
        try:
            llm = None
            try:
                llm = SimpleLLM()
            except Exception:
                llm = None
            rag = RAG(retriever=InMemoryRetriever(), llm=llm)
            return rag.answer(query)
        except Exception:
            logging.exception("rag_core present but failed, falling back")

    # 2) Versuch: Azure OpenAI / Foundry Integration via LangChain wenn konfiguriert
    # Erwartete ENV-Vars: AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_KEY, AZURE_OPENAI_DEPLOYMENT
    azure_base = os.getenv("AZURE_OPENAI_ENDPOINT") or os.getenv("AZURE_OPENAI_API_BASE")
    azure_key = os.getenv("AZURE_OPENAI_KEY") or os.getenv("AZURE_OPENAI_API_KEY")
    azure_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT") or os.getenv("AZURE_OPENAI_MODEL")

    def _try_azure_chain() -> Optional[Dict[str, Any]]:
        try:
            # Lazy imports to avoid hard dependency unless needed
            from langchain.chat_models import AzureChatOpenAI
            from langchain import LLMChain, PromptTemplate
            from langchain.vectorstores import Chroma
            from langchain.embeddings import HuggingFaceEmbeddings
        except Exception:
            logging.exception("LangChain Azure imports failed")
            return None

        try:
            CHROMA_DIR = os.getenv("CHROMA_DIR", "./chroma_db")
            embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
            vectordb = Chroma(persist_directory=CHROMA_DIR, embedding_function=embeddings)
            # similarity_search is a common API on vectorstores
            docs = vectordb.similarity_search(query, k=top_k)

            # compose context from docs
            context = "\n\n".join([getattr(d, "page_content", str(d)) for d in docs])

            # Configure Azure OpenAI credentials for underlying client (LangChain/OpenAI lib reads env)
            os.environ.setdefault("OPENAI_API_KEY", azure_key)
            os.environ.setdefault("OPENAI_API_BASE", azure_base)

            llm = AzureChatOpenAI(deployment_name=azure_deployment, temperature=0.0)

            prompt_template = """
You are a concise assistant for field technicians. Use the context to answer the question.

Context:
{context}

Question:
{question}

Provide a short diagnosis headline and a numbered step-by-step action plan. Keep answer factual and reference the source documents.
"""
            prompt = PromptTemplate(input_variables=["context", "question"], template=prompt_template)
            chain = LLMChain(llm=llm, prompt=prompt)
            answer_text = chain.predict(context=context, question=query)

            # extract top doc metadata if present
            source_quote = ""
            pdf_url = ""
            if docs:
                top = docs[0]
                top_text = getattr(top, "page_content", None) or top.get("text") if isinstance(top, dict) else str(top)
                source_quote = (top_text[:400] + "...") if top_text and len(top_text) > 400 else (top_text or "")
                # metadata access may differ
                meta = getattr(top, "metadata", None) or (top if isinstance(top, dict) else {})
                pdf_url = meta.get("pdf_url") if isinstance(meta, dict) else getattr(meta, "pdf_url", "")

            return {"content": answer_text, "source_quote": source_quote, "pdf_url": pdf_url}
        except Exception:
            logging.exception("Azure chain failed")
            return None

    if azure_base and azure_key and azure_deployment:
        azure_resp = _try_azure_chain()
        if azure_resp:
            return azure_resp

    # 3) Kein RAG/Core/Azure-Pfad verfügbar oder alles fehlgeschlagen -> Fallback
    return _fallback_response(query)
