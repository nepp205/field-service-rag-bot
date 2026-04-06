# Mit GitHub Copilot erstellt
# Build Stage
FROM python:3.11-slim as builder

WORKDIR /app

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

# Runtime Stage
FROM python:3.11-slim

WORKDIR /app

# Python Einstellungen
ENV FLASK_APP=context_webserver.py \
    FLASK_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Dependencies aus Builder kopieren
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# App-Code kopieren
COPY . .

# Gunicorn für Production
RUN pip install --no-cache-dir gunicorn==21.2.0

EXPOSE 5000

# Health Check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health').read()" || exit 1

# Gunicorn mit gthread Worker (Thread-basiert, teilt Memory besser) und erhöhtem Timeout
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "1", \
     "--threads", "4", \
     "--worker-class", "gthread", \
     "--timeout", "300", \
     "--max-requests", "1000", \
     "context_webserver:webserver"]
