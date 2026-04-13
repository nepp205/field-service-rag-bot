# RAG Vector DB - Docker Setup

Gehört zu Context_Handler
Das Context_Handler directory wurde vollständig von Marvin Palsbröker erstellt

## Übersicht
Diese Anwendung ist ein Flask-basiertes RAG (Retrieval Augmented Generation) System mit:
- **Flask Webserver** auf Port 5000
- **HuggingFace Embeddings** für Vektorisierung  
- **Qdrant Vector Store** (cloud-gehostet) zur Dokumentsuche
- **PDF Processing** für Handbücher und Manuals

## Voraussetzungen

### Lokal
- Docker und Docker Compose installiert
- `.env` Datei mit den korrekten Qdrant Credentials

### Environment Variablen

Die folgenden Variablen werden benötigt:
 - `QDRANT_URL` - URL zur Qdrant Vector Database   <!--https://512bf099-ef76-4b8d-bbb0-81c64346546e.eu-central-1-0.aws.cloud.qdrant.io-->
 - `QDRANT_API_KEY` - API Key für Qdrant

 - `HF_TOKEN=Placeholder`

 - `FLASK_ENV=production`
 - `FLASK_APP=context_webserver.py`

 - `WEBSERVER_TOKEN=Placeholder`

---

## Starten und Zugriff

### 1. **Mit Docker Compose (Empfohlen)**

```bash
# Image bauen
docker-compose build --no-cache

# Container starten
docker-compose up -d

# Logs anschauen (optional)
docker-compose logs -f rag-bot

# Stoppen
docker-compose down
```

### 2. **Webserver Zugriff**

Der Webserver läuft erreichbar unter:
- **URL**: `http://localhost:5000`
- **API Endpoint**: `POST http://localhost:5000/context`

#### API Parameter:
```json
{
  "query": "string (erforderlich) - Die Suchfrage",
  "model": "string (optional) - Modellname zum Filtern der PDFs. Nur PDFs mit diesem Namen in der Dateibezeichnung werden durchsucht"
}
```

### 3. **Context via API abrufen**

#### Request (ohne Model-Filter):
```bash
curl -X POST http://localhost:5000/context \
  -H "Authorization: Bearer Placeholder" \
  -H "Content-Type: application/json" \
  -d '{"query": "Wie wechsle ich die Heizung in meiner Miele Waschmaschine?"}'
```

#### Request (mit Model-Filter):
```bash
curl -X POST http://localhost:5000/context \
  -H "Authorization: Bearer Placeholder" \
  -H "Content-Type: application/json" \
  -d '{"query": "Wie wechsle ich die Heizung?", "model": "W1"}'
```

#### Response:
```json
{
  "context": "Quelle: Miele-waschmaschine-W1.pdf\n...\n\n---\n\n..."
}
```

### 4. **Python/JavaScript Client Beispiel**

**Python:**
```python
import requests
import json

url = "http://localhost:5000/context"
token = "Placeholder"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

data = {
    "query": "Welche Fehler können auftreten?",
    "model": "W1"  # Optional: Filtern nach Modellname
}

response = requests.post(url, headers=headers, json=data)
print(json.dumps(response.json(), indent=2))
```

---

## Docker Compose Datei Struktur

```yaml
services:
  rag-bot:
    - Container Name: rag-bot-app
    - Port: 5000
    - Volumes: hf_cache
    - Health Check: Aktiviert (30s Interval)
    - Auto-Restart: enabled
```

---

## Troubleshooting

### Container startet nicht
```bash
# Logs anschauen
docker-compose logs rag-bot

# Container entfernen und neu bauen
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### Container ist nicht erreichbar
```bash
# Prüfen ob Container läuft
docker-compose ps

# Port-Mapping prüfen
docker port rag-bot-app

# Netzwerk prüfen
docker network ls
docker network inspect rag-network
```

## Performance & Skalierung

Der Container nutzt:
- **Gunicorn** mit 4 Worker Prozessen
- **Timeout**: 120 Sekunden pro Request
- **Multi-stage Docker Build** für kleineres Image

Für höhere Last die Worker-Anzahl im Dockerfile anpassen:
```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "8", ...]
```