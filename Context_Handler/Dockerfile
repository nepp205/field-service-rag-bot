# gehört zu Context_Handler
# Das Context_Handler directory wurde vollständig von Marvin Palsbröker erstellt

# Mit GitHub Copilot erstellt und angepasst
# Build Stage
FROM python:3.11-slim as builder

WORKDIR /app

# Pip & setuptools upgraden
RUN pip install --upgrade pip setuptools wheel

# Requirements installieren
COPY requirements.txt .
RUN pip install --no-cache-dir --retries 5 -r requirements.txt

# Runtime Stage
FROM python:3.11-slim

WORKDIR /app

# Python Einstellungen und Umgebungsvariablen Pfade
ENV FLASK_APP=context_webserver.py \
    FLASK_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # HuggingFace-/SentenceTransformer-Cache zentral festlegen.
    # Der Cache wird zur Laufzeit über das Docker-Volume `hf_cache` befüllt,
    # damit das Image selbst klein bleibt.
    HF_HOME=/opt/hf-cache \
    HF_HUB_CACHE=/opt/hf-cache/hub \
    SENTENCE_TRANSFORMERS_HOME=/opt/hf-cache/sentence-transformers

# Dependencies aus Builder kopieren
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Code kopieren
COPY Context_Webserver.py ./
COPY Context_Handler.py ./
COPY rag.py ./
COPY warm_model_cache.py ./

# Gunicorn für Production
RUN pip install --no-cache-dir gunicorn==21.2.0

# Läuft auf Port 5000
EXPOSE 5000  
# Erst Cache-Volume prüfen/befüllen, dann Webserver starten.
CMD ["sh", "-c", "python /app/warm_model_cache.py && exec gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 --worker-class gthread --timeout 300 --max-requests 1000 Context_Webserver:webserver"]
# Gunicorn sorgt mit Worker Prozessen die eine Fork von Master prozessen sind für ständige verügbarkeit und die Verarbeitung von mehreren Anfragen gelichzeitig