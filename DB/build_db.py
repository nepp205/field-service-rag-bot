"""Build (or rebuild) the ChromaDB vector store from a PDF.

Can be run as a standalone script for local development or called
programmatically from the FastAPI lifespan hook on first boot.

Standalone usage:
    python DB/build_db.py
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

import chromadb
from chromadb.utils import embedding_functions
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

# =============================================================
# Defaults – override via function arguments or environment vars
# =============================================================
_DEFAULT_PDF = Path(__file__).parent / "Miele-PFD-401-MasterLine-Bedienungsanleitung.pdf"
_DEFAULT_CHROMA_PATH = os.getenv("CHROMA_PATH", "/data/chroma_db")
_DEFAULT_COLLECTION = "mini_rag_test"

CHUNK_SIZE = 350
CHUNK_OVERLAP = 80
EMBEDDING_MODEL = "all-MiniLM-L6-v2"


# =============================================================
def _extract_text(pdf_path: Path) -> str:
    """Extract all text from a PDF file."""
    reader = PdfReader(pdf_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def _split_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split *text* into overlapping fixed-size character chunks."""
    chunks: List[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start : start + chunk_size])
        start += chunk_size - overlap
    return chunks


def build(
    pdf_path: Path = _DEFAULT_PDF,
    chroma_path: str = _DEFAULT_CHROMA_PATH,
    collection_name: str = _DEFAULT_COLLECTION,
) -> None:
    """Ingest *pdf_path* into a ChromaDB collection at *chroma_path*.

    An existing collection with the same name is deleted first so the
    function is safe to call multiple times (idempotent).

    Args:
        pdf_path:        Path to the source PDF.
        chroma_path:     Directory used by ChromaDB for persistence.
        collection_name: Name of the ChromaDB collection to (re-)create.
    """
    print(f"Loading PDF .......... {pdf_path}")
    raw_text = _extract_text(pdf_path)
    print(f"Extracted text:      {len(raw_text):,} characters")

    print("Splitting into chunks …")
    chunks = _split_chunks(raw_text, CHUNK_SIZE, CHUNK_OVERLAP)
    print(f"Created {len(chunks)} chunks")

    print(f"Loading embedding model: {EMBEDDING_MODEL}")
    # Pre-load to warm the cache before connecting to Chroma
    SentenceTransformer(EMBEDDING_MODEL)

    print(f"Connecting to ChromaDB at {chroma_path!r} …")
    client = chromadb.PersistentClient(path=chroma_path)

    try:
        client.delete_collection(collection_name)
    except Exception as exc:  # collection may not exist yet on first run
        print(f"Note: could not delete existing collection ({exc})")

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    collection = client.create_collection(name=collection_name, embedding_function=ef)

    print("Storing chunks in vector database …")
    collection.add(
        documents=chunks,
        ids=[f"chunk_{i}" for i in range(len(chunks))],
    )
    print(f"Done – {len(chunks)} chunks stored in collection '{collection_name}'.")


def _smoke_test(chroma_path: str, collection_name: str) -> None:
    """Quick sanity-check query after a local build."""
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL
    )
    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_collection(name=collection_name, embedding_function=ef)

    query = "Filter wechseln"
    results = collection.query(query_texts=[query], n_results=5)
    print(f"\nSmoke-test query: {query!r}")
    for i, (doc, dist) in enumerate(
        zip(results["documents"][0], results["distances"][0]), 1
    ):
        print(f"  {i}. Score: {dist:.4f}   |   {doc[:120]} …")


if __name__ == "__main__":
    build()
    _smoke_test(chroma_path=_DEFAULT_CHROMA_PATH, collection_name=_DEFAULT_COLLECTION)
