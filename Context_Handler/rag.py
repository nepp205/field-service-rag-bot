# gehört zu Context_Handler
# Das Context_Handler directory wurde vollständig von Marvin Palsbröker erstellt

from difflib import SequenceMatcher
from pathlib import Path
import json
import os
import re
from dotenv import load_dotenv
from huggingface_hub import login
from llama_index.core import Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

load_dotenv()
login(token=os.getenv("HF_TOKEN"))


# Zentrale Konfiguration für Collection, Retrieval und Dokumentabgleich
COLLECTION_NAME = "Manuals_pdfs"
# COLLECTION_NAME = "Dev_Test"
SIMILARITY_TOP_RES = 20                # bei Tests sind bisher nur die ersten 3 bis 5 oder 6 zurückgegebenen Text chunks relevant gewesen
SIMILARITY_CUTOFF = 0.67             # Score relativ hoch da die Inhalte sehr ähnlich sind
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
    model_name="intfloat/multilingual-e5-large"         # größeres Modell weil es performance technisch keinen Unterschied macht
)

# Qdrant Client Connection definition für Zugriff auf Cloud Service
qdrant_client = QdrantClient(
    url=os.getenv("QDRANT_URL"),
    api_key=os.getenv("QDRANT_API_KEY"),
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


def build_filter(file_name: str | None = None) -> Filter | None:
    """Create an optional exact metadata filter on `file_name` for native Qdrant search."""
    if not file_name:   # wenn kein file name übergeben dann gebe auch nichts zurück
        return None

    return Filter(      # filter definieren 
        must=[FieldCondition(key="file_name", match=MatchValue(value=file_name))]   # fieldCondition für qdrant client interne Filterung und Verarbeitung
    )

# Mit Ki erstellt (Github Copilot) für error Handling und potentielle Fehler bei der Rückgabe
def extract_payload_text(payload: dict) -> str:
    """Extract the actual chunk text from the stored Qdrant payload."""
    if not payload:
        return ""

    if isinstance(payload.get("text"), str) and payload["text"].strip():        # wenn die payload text mitliefert dann wird dieser zurückgegeben
        return payload["text"].strip()

    node_content = payload.get("_node_content")                                 # wenn in text nichts gefunden wurde wird das feld _node_content geprüft
    if isinstance(node_content, str):                                           # wenn der inhalt da liegt dann gebe den inhalt zurück von json zu string
        try:
            return json.loads(node_content).get("text", "").strip()
        except json.JSONDecodeError:                                            # wenn das schief geht gebe nichts zurück
            return ""

    return ""                                                                   # wenn in beiden nichts (kein String) drin ist gebe leeren string zurück

def get_context(query: str, model: str = None) -> str:
    """Retrieve raw context nodes from Qdrant, with typo-tolerant pre-filtering."""
    resolved_file_name = resolve_document_name(model) if model else None

    response = qdrant_client.query_points(                  # query_points verlagert die verarbeitung und indexierung zu qdrant aus serverseitig effizienter
        collection_name=COLLECTION_NAME,
        query=embed_model.get_query_embedding(query),
        query_filter=build_filter(resolved_file_name),
        limit=SIMILARITY_TOP_RES,
        score_threshold=SIMILARITY_CUTOFF,
        with_payload=True     # parameter dafür das metadaten mit zurückgeliefert werden sollen 
    )

    context = "\n\n---\n\n".join(
        f"PDF Name: {point.payload.get('file_name', 'unbekannt')}\n"
        f"WebLink zum PDF: {point.payload.get('source') or 'unbekannt'}\n"
        f"Seite: {point.payload.get('page_label', 'unbekannt')}\n"
        f"{extract_payload_text(point.payload or {})}"
        
        for point in response.points
        if extract_payload_text(point.payload or {})
    )
    print(context)
    return context

# Test
if __name__ == "__main__":
    # frage = "Wie sollte ich meine Waschmaschine am besten hinstellen?"
    frage = "Mein Geschirrspüler zeigt den Fehler F-404 an was soll ich tun?"
    modell = "pfd 401"  # Optional: Filtern nach Modellname
    
    context = get_context(frage, model=modell)
    print("\n ------ \n")
    print(context)