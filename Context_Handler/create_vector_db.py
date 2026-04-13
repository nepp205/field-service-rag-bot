# gehört zu Context_Handler
# Das Context_Handler directory wurde vollständig von Marvin Palsbröker erstellt

from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, VectorParams
import json
from pathlib import Path
import re
from dotenv import load_dotenv
import os
from tqdm import tqdm

load_dotenv()

qdrant_url = os.getenv("QDRANT_URL")
qdrant_key = os.getenv("QDRANT_API_KEY")

COLLECTION_NAME = "Manuals_pdfs"
# COLLECTION_NAME = "Dev_Test"

PDF_SOURCES_PATH = Path(__file__).resolve().parent / "pdf_sources.json"

BATCH_SIZE = 50
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150

def load_pdf_sources() -> dict[str, str]:
    """Lädt die PDF-Links aus der JSON-Datei anhand des Dateinamens ohne Endung."""
    if not PDF_SOURCES_PATH.exists():
        return {}

    with open(PDF_SOURCES_PATH, "r", encoding="utf-8") as file:
        raw_sources = json.load(file)

    return {
        name.strip(): entry.get("source", "")
        for name, entry in raw_sources.items()
        if entry.get("source")
    }

PDF_SOURCE_MAP = load_pdf_sources()

# 1. PDFs laden mit LlamaIndex
print("Lade PDFs...")
loader = SimpleDirectoryReader("field-service-rag-bot/Context_Handler/pdfs/")
docs = loader.load_data()
print(docs[0].text[:1000])
print(f"{len(docs)} Dokumente geladen")

# Text-Preprocessing
def clean_text(text: str) -> str:
    """Cleans text from Noise and format-errors"""
    text = re.sub(r'\s+', ' ', text)    # entfernt mehrere Leerzeichen und erstzt diese mit nur einem Leerzeichen
    text = re.sub(r'\n+', ' ', text)    # ersetzt einene oder mehrere Zeilenumbrüche mit einem Leerzeichen
    return text.strip()

# Metadaten zu den Dokumenten hinzufügen
for doc in docs:
    doc.set_content(clean_text(doc.text))

    file_name = doc.metadata.get("file_name", "")
    source_link = PDF_SOURCE_MAP.get(Path(file_name).stem.strip())
    if source_link:
        doc.metadata["source"] = source_link

# 2. Text in Nodes zerlegen
node_parser = SimpleNodeParser.from_defaults(
    chunk_size=CHUNK_SIZE,
    chunk_overlap=CHUNK_OVERLAP
)

nodes = node_parser.get_nodes_from_documents(docs)
print(f"{len(nodes)} Nodes erstellt")
# print(nodes[0].get_content()[:1000])

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
    vectors_config=VectorParams(size=1024, distance=Distance.COSINE)  # dimensionen des e5 large sind 1024 Kosinusdistanz ist standard
)
print("Neue Qdrant Collection erstellt")

# Payload-Index für Metadata-Filter auf Dateinamen erstellen
client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="file_name",
    field_schema=PayloadSchemaType.KEYWORD,     # aufgrund eines Fehlers bei der metadata verarbeitung wurde das Feldschema auf Keyword gesetzt damit es im späteren Metadatamanagement verwendet werden kann
)
print("Payload-Index für 'file_name' erstellt")

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