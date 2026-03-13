"""Build the ChromaDB vector database from PDF source documents.

This script ingests PDF files from the `data/` directory, splits them into
chunks, computes embeddings, and stores them in a persistent ChromaDB
collection so that rag_core.py can perform vector-based retrieval.

Dependencies (see requirements.txt):
    - chromadb  – local persistent vector store
    - pypdf     – PDF text extraction
    - langchain-openai – embedding model (OpenAI Ada or similar)

Usage:
    python build_db.py

Environment variables:
    OPENAI_API_KEY – required by the embedding model

TODO (Marvin): Implement the ingestion pipeline below.
"""

# ---------------------------------------------------------------------------
# Placeholder – implement the ingestion pipeline here
# ---------------------------------------------------------------------------
#
# Suggested steps:
#   1. Glob all *.pdf files under the data/ directory.
#   2. Use pypdf (PdfReader) to extract text page by page.
#   3. Split the extracted text into overlapping chunks
#      (e.g. 500 tokens, 50-token overlap) to stay within embedding limits.
#   4. Create or open a persistent ChromaDB client and collection.
#   5. Generate embeddings with the OpenAI embedding model via langchain-openai.
#   6. Upsert the chunks together with their source metadata (filename, page)
#      into the ChromaDB collection.
#   7. Print a summary (number of documents / chunks ingested).
#
# Example skeleton:
#
#   import os, glob
#   from pypdf import PdfReader
#   import chromadb
#   from langchain_openai import OpenAIEmbeddings
#
#   DATA_DIR  = os.path.join(os.path.dirname(__file__), "data")
#   DB_DIR    = os.path.join(os.path.dirname(__file__), "chroma_db")
#   COLLECTION = "field_service_docs"
#
#   client     = chromadb.PersistentClient(path=DB_DIR)
#   collection = client.get_or_create_collection(COLLECTION)
#   embeddings = OpenAIEmbeddings()
#
#   for pdf_path in glob.glob(os.path.join(DATA_DIR, "*.pdf")):
#       reader = PdfReader(pdf_path)
#       for page_num, page in enumerate(reader.pages):
#           text = page.extract_text() or ""
#           # TODO: chunk text, embed, upsert into collection
