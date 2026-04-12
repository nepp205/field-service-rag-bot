# gehört zu Context_Handler
# Das Context_Handler directory wurde vollständig von Marvin Palsbröker erstellt
# Diese Datei wurde vollständig mit KI erstellt und ist für das chache-magaement für die schnelle Bereitstellung des Embedding Modells zur Laufzeit zuständig
# verwednete KI Github Copilot
import os
from pathlib import Path

from huggingface_hub import login, snapshot_download

# Modellname
MODEL_NAME = "intfloat/multilingual-e5-large"

# Alle Cache-Pfade zeigen in dasselbe persistente Docker-Volume. Dadurch muss
# das Modell nicht bei jedem Container-Start neu aus dem Hugging-Face-Hub geladen werden.
HF_CACHE_DIR = Path(os.getenv("HF_HOME", "/opt/hf-cache"))

# Hugging Face legt Modelle in einem Ordner-Schema wie `models--owner--repo` ab.
# Genau diesen Zielordner prüfen wir später, um vorhandene Modelldateien wiederzuverwenden.
MODEL_CACHE_DIR = HF_CACHE_DIR / f"models--{MODEL_NAME.replace('/', '--')}"

# Diese kleine Marker-Datei speichert für welches Modell der Cache zuletzt als
# vollständig vorbereitet markiert wurde. Das ist robuster als nur auf Ordner zu prüfen
# weil ein Ordner auch nach einem abgebrochenen Download schon existieren könnte.
READY_MARKER = HF_CACHE_DIR / ".model-cache-ready"


def cache_matches_requested_model() -> bool:
    """Return True when the persistent cache is already prepared for the active model."""
    # wenn die Marker-Datei fehlt wurde der Cache noch nie sauber als bereit markiert oder das Volume ist leer
    if not READY_MARKER.exists():
        return False

    try:
        # Die Datei enthält genau den Modellnamen, für den der Cache vorbereitet wurde.
        return READY_MARKER.read_text(encoding="utf-8").strip() == MODEL_NAME
    except OSError:     # wenn fehler beim lesen entsteht dann wird der cache nicht verwendet
        return False


def existing_model_files_present() -> bool:
    """Detect whether the requested model is already present in the shared volume."""
    # `any(iterdir())` stellt sicher, dass nicht nur der Ordner existiert, sondern
    # darin auch tatsächlich Dateien abgelegt wurden.
    return MODEL_CACHE_DIR.exists() and any(MODEL_CACHE_DIR.iterdir())


def maybe_login() -> None:
    """Perform a non-interactive Hugging Face login when a token is available."""
    # optional nur bei Modell download wichtig
    hf_token = os.getenv("HF_TOKEN")   
    if not hf_token:
        print("[CACHE] HF_TOKEN not set; trying public model download without login.")
        return

    try:
        # add_to_git_credential=False verhindert dass im container dauerhaft
        # Git-Credentials geschrieben werden. Wir brauchen das Token hier nur
        # für den einmaligen Download zugriff
        login(token=hf_token, add_to_git_credential=False)
        print("[CACHE] Hugging Face login succeeded for cache warmup.")
    except Exception as exc:
        print(f"[CACHE][WARN] Hugging Face login failed during warmup; continuing without it: {exc}")
        # kein Abbruch weil ist ja optional


def warm_cache() -> None:
    """Populate the shared Docker volume with the embedding model if it is missing."""
    # Sentence-Transformers nutzt zusätzlich einen eigenen Cache-Pfad. Auch dieser
    # wird in dasselbe persistente Volume gelegt
    sentence_transformers_home = Path(
        os.getenv("SENTENCE_TRANSFORMERS_HOME", str(HF_CACHE_DIR / "sentence-transformers"))
    )

    # Die Zielordner werden angelegt
    HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (HF_CACHE_DIR / "hub").mkdir(parents=True, exist_ok=True)
    sentence_transformers_home.mkdir(parents=True, exist_ok=True)

    # Cache Marker Modell passt mit dem cache Namen, also wird das Modell einfach in den Cache geladen
    if cache_matches_requested_model():
        print(f"[CACHE] Cache for {MODEL_NAME} already present in {HF_CACHE_DIR}; skipping download.")
        return

    # Modelldateien sind schon im Volume vorhanden, aber der Marker fehlt noch. 
    # Dann wird kein erneuter Download erzwungen, sondern der Marker nachgezogen.
    if existing_model_files_present():
        READY_MARKER.write_text(MODEL_NAME, encoding="utf-8")
        print(f"[CACHE] Reusing existing model files from {MODEL_CACHE_DIR}.")
        return

    # Nur wenn wirklich noch kein nutzbarer Cache gefunden wurde, wird ein Login
    # versucht und anschließend das Modell vollständig heruntergeladen
    maybe_login()
    print(f"[CACHE] Downloading model files for '{MODEL_NAME}' into {HF_CACHE_DIR} ...")

    # `snapshot_download` lädt die vollständige Repository-Snapshot-Struktur des
    # Modells in den Hugging-Face-Cache. Genau diese Struktur erwarten spätere
    # Hugging-Face- und Sentence-Transformer-Aufrufe beim Laden des Modells
    snapshot_download(repo_id=MODEL_NAME, cache_dir=str(HF_CACHE_DIR))

    # Nach erfolgreichem Download wird Marker geschrieben
    # Damit wird signalisiert dass das Volume für dieses Modell vollständig vorbereitet ist
    READY_MARKER.write_text(MODEL_NAME, encoding="utf-8")
    print(f"[CACHE] Model cache ready for {MODEL_NAME}.")


if __name__ == "__main__":
    warm_cache()
