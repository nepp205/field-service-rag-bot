# gehört zu Context_Handler
# Das Context_Handler directory wurde vollständig von Marvin Palsbröker erstellt

from difflib import SequenceMatcher
from pathlib import Path
import json
import os
import re
import time
from dotenv import load_dotenv
from huggingface_hub import login
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

load_dotenv()

hf_token = os.getenv("HF_TOKEN")
if hf_token:
    try:
        login(token=hf_token, add_to_git_credential=False)
        print("[INFO] Hugging Face login succeeded.")
    except Exception as exc:
        print(f"[WARN] Hugging Face login failed; continuing without it: {exc}")
else:
    print("[INFO] HF_TOKEN not set; continuing without Hugging Face login.")


# Zentrale Konfiguration für Collection, Retrieval und Dokumentabgleich
COLLECTION_NAME = "Manuals_pdfs"
# COLLECTION_NAME = "Dev_Test"
SIMILARITY_TOP_RES = 15             # hohe Anzahl um auch scheinbar unbedeutenden Kontext abzudecken
SIMILARITY_CUTOFF = 0.5             # Score relativ hoch da die Inhalte sehr ähnlich sind
DOCUMENT_MATCH_THRESHOLD = 0.80
DOCUMENT_CATALOG_TTL_SECONDS = 300
HF_CACHE_DIR = os.getenv("HF_HOME", "/opt/hf-cache")        # Pfad im Docker
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
_model_load_start = time.perf_counter()
embed_model = HuggingFaceEmbedding(
    model_name="intfloat/multilingual-e5-large",        # größeres Modell weil es performance technisch keinen Unterschied macht
    cache_folder=HF_CACHE_DIR,                          # cache für docker performance
)
print(f"[METRIC] embed_model_load_seconds={time.perf_counter() - _model_load_start:.3f} cache_dir={HF_CACHE_DIR}")

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


DOCUMENT_CATALOG: list[dict] = []
DOCUMENT_CATALOG_LAST_REFRESH = 0.0


def build_document_catalog() -> list[dict]:
    """Create a cached catalog of indexed PDF names from Qdrant payload metadata."""
    # Der Katalog wird direkt aus Qdrant geladen, damit kein lokales
    # Verzeichnis für den Modellabgleich benötigt wird.
    global DOCUMENT_CATALOG, DOCUMENT_CATALOG_LAST_REFRESH

    now = time.time()
    cache_is_fresh = (now - DOCUMENT_CATALOG_LAST_REFRESH) < DOCUMENT_CATALOG_TTL_SECONDS   # für doceker damit der catalog nicht immer neu aufgebaut werden muss  ttl auf 300 sec dann refresh
    if DOCUMENT_CATALOG and cache_is_fresh:
        return DOCUMENT_CATALOG

    catalog_by_name: dict[str, dict] = {}
    offset = None

    try:
        while True:
            points, offset = qdrant_client.scroll(
                collection_name=COLLECTION_NAME,
                limit=256,                          # batch verarbeitungslimit 
                offset=offset,                      # was übrig bleibt
                with_payload=["file_name"],         # nur dateinamen für performance
                with_vectors=False,                 # hier nur metadaten vektoren nicht nötig
            )

            for point in points:
                payload = point.payload or {}
                file_name = payload.get("file_name") # dateinamen auslesen

                if isinstance(file_name, str) and file_name.strip() and file_name not in catalog_by_name:           # katalog an pdfs anlegen 
                    catalog_by_name[file_name] = {
                        "file_name": file_name,
                        "normalized_name": normalize_document_name(file_name),
                    }

            if offset is None:  # wenn nichts mehr übrig ist
                break

    except Exception as exc:
        print(f"[WARN] Could not load document catalog from Qdrant: {exc}")
        return DOCUMENT_CATALOG

    DOCUMENT_CATALOG = sorted(catalog_by_name.values(), key=lambda entry: entry["file_name"].lower())
    DOCUMENT_CATALOG_LAST_REFRESH = now
    print(f"[INFO] Loaded {len(DOCUMENT_CATALOG)} document names from Qdrant metadata.")
    return DOCUMENT_CATALOG


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

    catalog = build_document_catalog()

    matches = []
    for entry in catalog:  # iterieren durch den Dokumentenkatalog aus Qdrant-Metadaten
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
    total_start = time.perf_counter()

    model_resolve_start = time.perf_counter()
    resolved_file_name = resolve_document_name(model) if model else None
    model_resolve_seconds = time.perf_counter() - model_resolve_start

    embedding_start = time.perf_counter()
    query_embedding = embed_model.get_query_embedding(query)
    embedding_seconds = time.perf_counter() - embedding_start

    qdrant_start = time.perf_counter()
    response = qdrant_client.query_points(                  # query_points verlagert die verarbeitung zu qdrant aus serverseitig effizienter
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        query_filter=build_filter(resolved_file_name),
        limit=SIMILARITY_TOP_RES,
        score_threshold=SIMILARITY_CUTOFF,
        with_payload=True     # parameter dafür das metadaten mit zurückgeliefert werden sollen 
    )
    qdrant_seconds = time.perf_counter() - qdrant_start

    context = "\n\n---\n\n".join(
        f"PDF Name: {point.payload.get('file_name', 'unbekannt')}\n"
        f"WebLink zum PDF: {point.payload.get('source') or 'unbekannt'}\n"
        f"Seite: {point.payload.get('page_label', 'unbekannt')}\n"
        f"{extract_payload_text(point.payload or {})}"
        
        for point in response.points
        if extract_payload_text(point.payload or {})
    )

    total_seconds = time.perf_counter() - total_start               # Ausgabe der Zeiten
    print(
        "[METRIC] "
        f"resolve_model_seconds={model_resolve_seconds:.3f} "
        f"embedding_seconds={embedding_seconds:.3f} "
        f"qdrant_seconds={qdrant_seconds:.3f} "
        f"total_seconds={total_seconds:.3f} "
        f"hits={len(response.points)}"
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