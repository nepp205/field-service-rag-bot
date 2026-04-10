# gehört zu Context_Handler
# Das Context_Handler directory wurde vollständig von Marvin Palsbröker erstellt
# Diese Datei wurde vollständig mit KI erstellt und ist für das chache-magaement für die schnelle Bereitstellung des Embedding Modells zur Laufzeit zuständig
# verwednete KI Github Copilot
import os
from pathlib import Path

from huggingface_hub import login, snapshot_download

MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "intfloat/multilingual-e5-large")
HF_CACHE_DIR = Path(os.getenv("HF_HOME", "/opt/hf-cache"))
MODEL_CACHE_DIR = HF_CACHE_DIR / f"models--{MODEL_NAME.replace('/', '--')}"
READY_MARKER = HF_CACHE_DIR / ".model-cache-ready"


def cache_matches_requested_model() -> bool:
    """Return True when the persistent cache is already prepared for the active model."""
    if not READY_MARKER.exists():
        return False

    try:
        return READY_MARKER.read_text(encoding="utf-8").strip() == MODEL_NAME
    except OSError:
        return False


def existing_model_files_present() -> bool:
    """Detect whether the requested model is already present in the shared volume."""
    return MODEL_CACHE_DIR.exists() and any(MODEL_CACHE_DIR.iterdir())


def maybe_login() -> None:
    """Perform a non-interactive Hugging Face login when a token is available."""
    hf_token = os.getenv("HF_TOKEN")
    if not hf_token:
        print("[CACHE] HF_TOKEN not set; trying public model download without login.")
        return

    try:
        login(token=hf_token, add_to_git_credential=False)
        print("[CACHE] Hugging Face login succeeded for cache warmup.")
    except Exception as exc:
        print(f"[CACHE][WARN] Hugging Face login failed during warmup; continuing without it: {exc}")


def warm_cache() -> None:
    """Populate the shared Docker volume with the embedding model if it is missing."""
    sentence_transformers_home = Path(
        os.getenv("SENTENCE_TRANSFORMERS_HOME", str(HF_CACHE_DIR / "sentence-transformers"))
    )

    HF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (HF_CACHE_DIR / "hub").mkdir(parents=True, exist_ok=True)
    sentence_transformers_home.mkdir(parents=True, exist_ok=True)

    if cache_matches_requested_model():
        print(f"[CACHE] Cache for {MODEL_NAME} already present in {HF_CACHE_DIR}; skipping download.")
        return

    if existing_model_files_present():
        READY_MARKER.write_text(MODEL_NAME, encoding="utf-8")
        print(f"[CACHE] Reusing existing model files from {MODEL_CACHE_DIR}.")
        return

    maybe_login()
    print(f"[CACHE] Downloading model files for '{MODEL_NAME}' into {HF_CACHE_DIR} ...")
    snapshot_download(repo_id=MODEL_NAME, cache_dir=str(HF_CACHE_DIR))
    READY_MARKER.write_text(MODEL_NAME, encoding="utf-8")
    print(f"[CACHE] Model cache ready for {MODEL_NAME}.")


if __name__ == "__main__":
    warm_cache()
