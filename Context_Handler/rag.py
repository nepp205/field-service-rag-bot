# gehört zu Context_Handler
# Das Context_Handler directory wurde vollständig von Marvin Palsbröker erstellt

from difflib import SequenceMatcher
from pathlib import Path
import os
import re

from dotenv import load_dotenv
from huggingface_hub import login
from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

load_dotenv()
login(token=os.getenv("HF_TOKEN"))

# Zentrale Konfiguration für Collection, Retrieval und Dokumentabgleich
COLLECTION_NAME = "Manuals_pdfs"
SIMILARITY_TOP_K = 15
SIMILARITY_CUTOFF = 0.6
DOCUMENT_MATCH_THRESHOLD = 0.80
PDF_DIRECTORY = Path(__file__).resolve().parent / "pdfs"
GENERIC_DOCUMENT_WORDS = {
    "bedienungsanleitung",
    "gebrauchsanweisung",
    "manual",
    "handbuch",
    "instructions",
    "guide",
    "service",
    "repair",
}

# Embedding-Modell für Query und Indexzugriff
embed_model = HuggingFaceEmbedding(
    model_name="intfloat/multilingual-e5-large"
)

# Qdtrant Client Connection definition für Zugriff auf Cloud Service
qdrant_client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY")
)

# Definition der von LlammaIndex gegebenen Schnittstelle für die Interaktion mit dem Qdrant Vector Store
vector_store = QdrantVectorStore(
    client=qdrant_client,
    collection_name=COLLECTION_NAME
)

# definition des Index auf basis des definierten Vector Stores und dem verwendeten embedding Modell
index = VectorStoreIndex.from_vector_store(
    vector_store=vector_store,
    embed_model=embed_model
)

def normalize_document_name(value: str) -> str:
    """Normalize document and model names for typo-tolerant matching."""
    normalized = Path(value).stem.lower().strip()
    normalized = re.sub(r"[_\-.]+", " ", normalized) # ersetzt _ - .  durch Leerzeichen
    normalized = re.sub(r"[^\w\s]", " ", normalized) # ersetzt alle Sonderzeichen durch Leerzeichen
    normalized = re.sub(r"\s+", " ", normalized).strip() # ersetzt mehrere Leerzeichen durch nur eines

    tokens = [   # String wird in Einzelteile zerlegt und die Teile werden mit den 
        token    # generischen Begriffen abgeglichen
        for token in normalized.split()
        if token and token not in GENERIC_DOCUMENT_WORDS
    ]
    return " ".join(tokens)         # array wird wieder zu einem string zusammengesetzt und zurückgegeben


def build_document_catalog() -> list[dict]:
    """Create a simple catalog of the indexed source PDF names."""
    # Der Katalog wird aus den lokalen PDF-Dateinamen aufgebaut und später
    # für den Modellabgleich vor dem eigentlichen Retrieval genutzt
    catalog = []

    if not PDF_DIRECTORY.exists():
        return catalog

    for pdf_path in sorted(PDF_DIRECTORY.glob("*.pdf")):
        file_name = pdf_path.name
        normalized_name = normalize_document_name(file_name)

        catalog.append(
            {
                "file_name": file_name,
                "normalized_name": normalized_name,
            }
        )

    return catalog


DOCUMENT_CATALOG = build_document_catalog()


def best_partial_ratio(model: str, file: str) -> float:
    """Best similarity of `model` against any substring of `file`."""
    # diese Funktion prüft ob das Modell in einem Teilstrings des Dateinamens der gerade zur Prüfung herangezogen wird in ähnlicher Form vorliegt
    # bester Ähnlichkeitswert wird an die aufrufende Funktion zurückgegeben
    if not model or not file:
        return 0.0

    if model in file:
        return 1.0

    if len(model) > len(file):
        return SequenceMatcher(None, model, file).ratio()

    best_score = 0.0
    window_len = len(model)

    for start in range(len(file) - window_len + 1):
        window = file[start:start + window_len]
        score = SequenceMatcher(None, model, window).ratio()
        best_score = max(best_score, score)

    return best_score


def resolve_document_name(model: str, threshold: float = DOCUMENT_MATCH_THRESHOLD) -> str | None:
    """Resolve a possibly misspelled model name to one canonical PDF name."""
    # Wenn ein ausreichend guter Match gefunden wird, wird genau ein PDF-Name für die spätere Metadata-Filterung zurückgegeben
    normalized_model = normalize_document_name(model)
    
    if not normalized_model:
        return None

    matches = []
    for entry in DOCUMENT_CATALOG:  # iterieren durch den Dokumentenkatalog 
        score = best_partial_ratio(normalized_model, entry["normalized_name"]) # Ähnlichkeitsscore berechnen
        if score >= threshold: # Abgleich mit Mindestwert
            matches.append((entry["file_name"], score)) # Tupel aus Dateinamen und Ähnlichkeitswert zur Liste mit Matches hinzufügen

    if not matches: # wenn kein match dann nichts zurückgeben
        return None

    matches.sort(key=lambda item: item[1], reverse=True)  # Sortieren der Matches nach Score von hoch zu niedrig
    best_file_name, best_score = matches[0]   # nach der sortierung der oberster eintrag zu den Variablen zugewiesen 

    if len(matches) > 1:        # wenn es mehrere Matches gibt dann soll die Differenz aus den beiden besten scors betrachtet werden
        second_best_score = matches[1][1]
        if best_score - second_best_score < 0.02:       # ist diese unter dem festgelegten Schwellenwert wird nichts zurückgegeben weil kein eindeutiges Ergebnis gefunden werden konnte
            return None

    return best_file_name


def build_retriever(file_name: str | None = None) -> VectorIndexRetriever:
    """Create a retriever with an optional exact metadata filter on file_name."""
    filters = None
    if file_name:
        filters = MetadataFilters(     # Metadatafilters von Llamaindex für das vorgelagerte Filtern vor der tatsächlichen Suche in der Vektordatenbank
            filters=[ExactMatchFilter(key="file_name", value=file_name)]
        )

    return VectorIndexRetriever(        # Rückgabe des konfigurierten retrievers
        index=index,
        similarity_top_k=SIMILARITY_TOP_K,
        similarity_cutoff=SIMILARITY_CUTOFF,
        filters=filters,
    )


def get_context(query: str, model: str = None) -> str:
    """Retrieve raw context nodes from Qdrant, with typo-tolerant pre-filtering."""
    # Erst wird optional ein passender Dokumentname aufgelöst
    # danach wird der Retriever mit genau diesem Dateifilter aufgesetzt
    resolved_file_name = resolve_document_name(model) if model else None  # wenn model dann model | Dokumente Abgleich
    retriever = build_retriever(resolved_file_name)
    nodes = retriever.retrieve(query)

    context = "\n\n---\n\n".join(
        f"Quelle: {node.node.metadata.get('file_name', 'unbekannt')} "      # node.node wegen Klassenstruktur von LlamaIndex
        f"(Seite {node.node.metadata.get('page_label', 'unbekannt')})\n"
        f"{node.node.get_content()}"
        for node in nodes       # nodes ist eine Liste an Node Wrappern "NodeWithScore" deswegen muss man auf den eigentlichen node mit .node zugreifen
    )

    return context


# Test
if __name__ == "__main__":
    # frage = "Wie sollte ich meine Waschmaschine am besten hinstellen?"
    frage = "Mein Geschirrspüler zeigt den Fehler F-404 an was soll ich tun?"
    modell = "pfd 401"  # Optional: Filtern nach Modellname
    
    context = get_context(frage, model=modell)
    print(context)