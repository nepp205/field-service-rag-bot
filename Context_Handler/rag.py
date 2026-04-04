from llama_index.core import VectorStoreIndex
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.retrievers import VectorIndexRetriever
from qdrant_client import QdrantClient
from dotenv import load_dotenv
import os
from huggingface_hub import login

login(token=os.getenv("HF_TOKEN"))

load_dotenv()

COLLECTION_NAME = "Manuals_pdfs"

# Setup: Embeddings + Qdrant
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

# Retriever (einfach und direkt)
retriever = VectorIndexRetriever(
    index=index,
    similarity_top_k=15,
    similarity_cutoff=0.6
)

def get_context(query: str, model: str = None) -> str:
    """Retrieves raw context nodes from Qdrant
    
    Args:
        query (str): The search query
        model (str, optional): The model name to filter PDFs. Only PDFs containing this model name will be searched.
    
    Returns:
        str: The retrieved context from matching documents
    """
    nodes = retriever.retrieve(query)   # oder retriever.retrieve(QueryBundle(query))
    
    # Filter by model name if provided
    if model:
        model_lower = model.lower()
        filtered_nodes = [
            node for node in nodes 
            if model_lower in node.node.metadata.get('file_name', '').lower()
        ]
        # If no nodes match the model filter, return empty result
        if filtered_nodes:
            nodes = filtered_nodes
    
    context = "\n\n---\n\n".join(
        f"Quelle: {node.node.metadata.get('file_name', 'unbekannt')} "
        f"(Seite {node.node.metadata.get('page_label', 'unbekannt')})\n"
        f"{node.node.get_content()}"
        for node in nodes
    )
    
    return context


# Test
if __name__ == "__main__":
    frage = "Wie sollte ich meine Waschmaschine am besten hinstellen?"
    modell = "W1"  # Optional: Filtern nach Modellname
    
    context = get_context(frage, model=modell)

    print(context)