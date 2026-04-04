from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
import re
from dotenv import load_dotenv
import os
from tqdm import tqdm

load_dotenv()

qdrant_url = os.getenv("QDRANT_URL")
qdrant_key = os.getenv("QDRANT_API_KEY")

COLLECTION_NAME = "Manuals_pdfs"
BATCH_SIZE = 50

# 1. PDFs laden mit LlamaIndex
print("Lade PDFs...")
loader = SimpleDirectoryReader("field-service-rag-bot/Context_Handler/pdfs/")
docs = loader.load_data()

print(f"{len(docs)} Dokumente geladen")

# Text-Preprocessing
def clean_text(text: str) -> str:
    """Bereinigt Text von Noise und Formatierungsfehlern"""
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'\n+', ' ', text)
    return text.strip()

for doc in docs:
    doc.text = clean_text(doc.text)

# 2. Text in Nodes zerlegen
node_parser = SimpleNodeParser.from_defaults(
    chunk_size=500,
    chunk_overlap=100
)

nodes = node_parser.get_nodes_from_documents(docs)
print(f"{len(nodes)} Nodes erstellt")

# 3. Embeddings-Modell
embed_model = HuggingFaceEmbedding(
    model_name="intfloat/multilingual-e5-large"
)

# Qdrant Connection
client = QdrantClient(
    url=qdrant_url,
    api_key=qdrant_key
)

# Collection löschen/erstellen
try:
    client.delete_collection(collection_name=COLLECTION_NAME)
    print("Alte Collection gelöscht")
except Exception:
    pass

client.create_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
)
print("Neue Qdrant Collection erstellt")

# 5. Vector Store mit Qdrant
vector_store = QdrantVectorStore(
    client=client,
    collection_name=COLLECTION_NAME
)

storage_context = StorageContext.from_defaults(vector_store=vector_store)

# 6. Batch-Processing mit Progress Bar
print(f"\nIndexiere {len(nodes)} Nodes in Batches...")

index = None
for i in tqdm(range(0, len(nodes), BATCH_SIZE), desc="Batch-Verarbeitung"):
    batch_nodes = nodes[i:i + BATCH_SIZE]
    
    if index is None:
        # Erster Batch: Erstelle Index
        index = VectorStoreIndex(
            nodes=batch_nodes,
            storage_context=storage_context,
            embed_model=embed_model,
            show_progress=True
        )
    else:
        # Weitere Batches: Füge hinzu
        index.insert_nodes(batch_nodes)

print("\nAlle Nodes erfolgreich in Qdrant indexiert!")