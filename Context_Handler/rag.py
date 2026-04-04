from llama_index.core import VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.retrievers import VectorIndexRetriever
from qdrant_client import QdrantClient
from dotenv import load_dotenv
import os
from huggingface_hub import login

login(token="hf_...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")

load_dotenv()

COLLECTION_NAME = "Manuals_pdfs"

# =============================================
# Setup: Embeddings + Qdrant
# =============================================
embed_model = HuggingFaceEmbedding(
    model_name="intfloat/multilingual-e5-large"
)

qdrant_client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY")
)

vector_store = QdrantVectorStore(
    client=qdrant_client,
    collection_name=COLLECTION_NAME
)

index = VectorStoreIndex.from_vector_store(
    vector_store=vector_store,
    embed_model=embed_model
)

# =============================================
# Retriever (einfach und direkt)
# =============================================
retriever = VectorIndexRetriever(
    index=index,
    similarity_top_k=15,
    similarity_cutoff=0.6   # wird als score_threshold intern verwendet
)

# =============================================
# Hilfsfunktion: Nur Kontext abrufen (ohne LLM)
# =============================================
def get_context(query: str) -> str:
    """Retrieves raw context nodes from Qdrant"""
    nodes = retriever.retrieve(query)   # oder retriever.retrieve(QueryBundle(query))
    
    context = "\n\n---\n\n".join(
        f"Quelle: {node.node.metadata.get('file_name', 'unbekannt')}\n"
        f"{node.node.get_content()}"
        for node in nodes
    )
    
    return context


# =============================================
# Test
# =============================================
if __name__ == "__main__":
    frage = "Sieb Reinigen?"
    
    context = get_context(frage)
    
    prompt = f"""Du bist ein hilfreicher Assistent. 
Verwende nur die folgenden Kontext-Informationen, um die Frage zu beantworten.
Antworte auf Deutsch und sei präzise.

=== KONEXT ===
{context}
=== ENDE KONEXT ===

Frage: {frage}
Antwort:"""

    print(prompt)