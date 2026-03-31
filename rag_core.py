"""RAG pipeline – ChromaDB retrieval + Azure AI Foundry (Azure OpenAI) generation.

Environment variables required (set as HuggingFace Space Secrets):
    AZURE_OPENAI_ENDPOINT   – e.g. https://my-resource.openai.azure.com/
    AZURE_OPENAI_API_KEY    – your Azure OpenAI key
    AZURE_OPENAI_DEPLOYMENT – deployment name, e.g. gpt-4o
    AZURE_OPENAI_API_VERSION – API version, default 2024-02-01

Optional:
    CHROMA_PATH – path to the persistent ChromaDB directory (default /data/chroma_db)
"""

from __future__ import annotations

import os

import chromadb
from chromadb.utils import embedding_functions
from openai import AzureOpenAI

CHROMA_PATH = os.getenv("CHROMA_PATH", "/data/chroma_db")
COLLECTION_NAME = "mini_rag_test"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
TOP_K = 5

SYSTEM_PROMPT = (
    "Du bist ein Servicetechniker-Assistent für Miele-Geräte. "
    "Beantworte Fragen ausschließlich auf Basis des bereitgestellten Kontexts aus dem Handbuch. "
    "Antworte immer auf Deutsch. "
    "Wenn der Kontext keine ausreichende Antwort liefert, sage das klar."
)


class RAG:
    """Retrieval-Augmented Generation pipeline."""

    def __init__(self) -> None:
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=EMBEDDING_MODEL
        )
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.collection = client.get_collection(name=COLLECTION_NAME, embedding_function=ef)

        self._llm = AzureOpenAI(
            azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
            api_key=os.environ["AZURE_OPENAI_API_KEY"],
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
        )
        self._deployment = os.environ["AZURE_OPENAI_DEPLOYMENT"]

    def answer(self, question: str) -> dict:
        """Retrieve relevant chunks and generate an answer.

        Args:
            question: The user's question in natural language.

        Returns:
            A dict with key ``content`` containing the generated answer string.
        """
        results = self.collection.query(query_texts=[question], n_results=TOP_K)
        docs = results.get("documents", [[]])[0]

        if not docs:
            return {"content": "Im Handbuch wurde kein passender Abschnitt zu dieser Frage gefunden."}

        context = "\n\n---\n\n".join(docs)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Kontext aus dem Handbuch:\n{context}\n\nFrage: {question}",
            },
        ]

        response = self._llm.chat.completions.create(
            model=self._deployment,
            messages=messages,
            temperature=0.2,
            max_tokens=1024,
        )

        choices = response.choices
        if not choices or choices[0].message.content is None:
            return {"content": "Keine Antwort vom LLM erhalten – bitte erneut versuchen."}

        return {"content": choices[0].message.content}
