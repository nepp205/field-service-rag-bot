# gehört zu Context_Handler
# Das Context_Handler directory wurde vollständig von Marvin Palsbröker erstellt

# Mit GitHub Copilot erstellt und angepasst
# Build Stage
FROM python:3.11-slim as builder

WORKDIR /app

# HuggingFace-/SentenceTransformer-Cache zentral festlegen,
# damit das Embedding-Modell bereits beim Build heruntergeladen werden kann.
ENV HF_HOME=/opt/hf-cache \
    TRANSFORMERS_CACHE=/opt/hf-cache \
    SENTENCE_TRANSFORMERS_HOME=/opt/hf-cache

# System-Dependencies für PDF-Processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Pip & setuptools upgraden
RUN pip install --upgrade pip setuptools wheel

# Requirements installieren
COPY requirements.txt .
RUN pip install --no-cache-dir --retries 5 -r requirements.txt

# Embedding-Modell bereits beim Image-Build herunterladen,
# damit es beim späteren Container-Start nicht erneut geladen werden muss.
RUN mkdir -p "${HF_HOME}" && \
    python -c "from llama_index.embeddings.huggingface import HuggingFaceEmbedding; HuggingFaceEmbedding(model_name='intfloat/multilingual-e5-large')"

# Runtime Stage
FROM python:3.11-slim

WORKDIR /app

# Python Einstellungen
ENV FLASK_APP=context_webserver.py \
    FLASK_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/opt/hf-cache \
    TRANSFORMERS_CACHE=/opt/hf-cache \
    SENTENCE_TRANSFORMERS_HOME=/opt/hf-cache

# Dependencies und Modell-Cache aus Builder kopieren
COPY --from=builder /opt/hf-cache /opt/hf-cache
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Code kopieren
COPY context_webserver.py ./
COPY Context_Handler.py ./
COPY rag.py ./
COPY pdfs ./pdfs

# Gunicorn für Production
RUN pip install --no-cache-dir gunicorn==21.2.0

EXPOSE 5000

# Gunicorn mit gthread Worker (Thread-basiert, teilt Memory besser) und erhöhtem Timeout
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "1", \
     "--threads", "4", \
     "--worker-class", "gthread", \
     "--timeout", "300", \
     "--max-requests", "1000", \
     "context_webserver:webserver"]
