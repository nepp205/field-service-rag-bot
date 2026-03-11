from pathlib import Path
from typing import List

from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.utils import embedding_functions

# =============================================================
# Konfiguration – alles was du anpassen musst ist hier
# =============================================================
PDF_PATH = Path("./field-service-rag-bot/DB/Miele-PFD-401-MasterLine-Bedienungsanleitung.pdf")              # ← dein PDF hier
CHUNK_SIZE = 350                         # Zeichen pro Chunk
CHUNK_OVERLAP = 80                       # Überlappung damit nichts abgeschnitten wird
COLLECTION_NAME = "mini_rag_test"

# Embedding-Modell (schnell & gut genug für den Anfang)
EMBEDDING_MODEL = "all-MiniLM-L6-v2"     # 384 Dimensionen, sehr schnell auf CPU

# =============================================================
def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extrahiert allen Text aus dem PDF (sehr einfach gehalten)"""
    reader = PdfReader(pdf_path)
    full_text = ""
    for page in reader.pages:
        text = page.extract_text() or ""
        full_text += text + "\n\n"
    return full_text.strip()


def split_text_into_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Teilt Text in überlappende Chunks"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
    return chunks


def main():
    print(f"Lade PDF ............. {PDF_PATH}")
    raw_text = extract_text_from_pdf(PDF_PATH)
    print(f"Extrahierter Text:    {len(raw_text):,} Zeichen")

    print("Teile in Chunks ......")
    chunks = split_text_into_chunks(raw_text, CHUNK_SIZE, CHUNK_OVERLAP)
    print(f"Erzeugt {len(chunks)} Chunks")

    print(f"Lade Embedding-Modell: {EMBEDDING_MODEL}")
    embedder = SentenceTransformer(EMBEDDING_MODEL)

    print("Verbinde mit Chroma (lokal, speichert in ./chroma_db/)")
    client = chromadb.PersistentClient(path="./chroma_db")
    
    # Lösche alte Collection falls vorhanden (für saubere Tests)
    try:
        client.delete_collection(COLLECTION_NAME)
    except:
        pass
    
    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_functions.SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    )

    # Wir fügen die Chunks + automatisch generierte Embeddings hinzu
    print("Speichere Chunks in Vektordatenbank ...")
    ids = [f"chunk_{i}" for i in range(len(chunks))]
    
    collection.add(
        documents=chunks,
        ids=ids,
        # metadatas=[{"source": "test.pdf", "chunk_index": i} for i in range(len(chunks))],
    )
    print("Fertig gespeichert!")

    # ───────────────────────────────────────────────
    # Test-Suche
    # ───────────────────────────────────────────────
    query = "Filter wechseln"

    results = collection.query(
            query_texts=[query],
            n_results=5
    )
    print(f"\nQuery: {query}")
    for i, (doc, dist) in enumerate(zip(results["documents"][0], results["distances"][0]), 1):
        print(f"  {i}. Score: {dist:.4f}   |   {doc[:120]}...")


if __name__ == "__main__":
    main()