# Von GitHub Copilot generiert, angepasst von Niklas

# --- Build-Stage: abhängigkeiten installieren ---
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
    && rm -rf /var/lib/apt/lists/*  # cache leeren

RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .
RUN pip install --no-cache-dir --retries 5 -r requirements.txt

# --- Runtime-Stage: nur was wirklich gebraucht wird ---
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1  # keine .pyc dateien

# pakete aus builder übernehmen
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# anwendungsdateien kopieren
COPY requesthandler.py ./
COPY gunicorn.conf.py ./
COPY system_prompt.txt ./
COPY form.json ./

EXPOSE 8000  # port freigeben

CMD ["gunicorn", "-c", "gunicorn.conf.py", "requesthandler:app"]
