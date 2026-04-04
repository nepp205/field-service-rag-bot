# RAG Vector DB - Docker Setup

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
Erstelle eine `.env` Datei basierend auf `.env.example`:
```
cp .env.example .env
```

Die folgenden Variablen werden benötigt:
 - `QDRANT_URL` - URL zur Qdrant Vector Database   <!--https://512bf099-ef76-4b8d-bbb0-81c64346546e.eu-central-1-0.aws.cloud.qdrant.io-->
- `QDRANT_API_KEY` - API Key für Qdrant

---

## Starten und Zugriff

### 1. **Mit Docker Compose (Empfohlen)**

```bash
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
- **Health Check**: `GET http://localhost:5000/health`
- **API Endpoint**: `POST http://localhost:5000/context`

### 3. **Context via API abrufen**

#### Request:
```bash
curl -X POST http://localhost:5000/context \
  -H "Authorization: Bearer Placeholder" \
  -H "Content-Type: application/json" \
  -d '{"query": "Wie wechsle ich die Heizung in meiner Siemens Waschmaschine?"}'
```

#### Response:
```json
{
  "context": "Quelle: siemens-waschmaschine.pdf\n...\n\n---\n\n..."
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
    "query": "Welche Fehler können auftreten?"
}

response = requests.post(url, headers=headers, json=data)
print(json.dumps(response.json(), indent=2))
```

**JavaScript/Node.js:**
```javascript
const token = "Placeholder";

const response = await fetch("http://localhost:5000/context", {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${token}`,
    "Content-Type": "application/json"
  },
  body: JSON.stringify({ query: "Welche Fehler können auftreten?" })
});

const data = await response.json();
console.log(data);
```

---

## Docker Compose Datei Struktur

```yaml
services:
  rag-bot:
    - Container Name: rag-bot-app
    - Port: 5000
    - Volumes: ./pdfs -> /app/pdfs
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

### Qdrant Verbindung fehlgeschlagen
- `.env` Datei prüfen
- `QDRANT_URL` und `QDRANT_API_KEY` validieren
- Netzwerkverbindung prüfen (firewall, proxy)

---

## Performance & Skalierung

Der Container nutzt:
- **Gunicorn** mit 4 Worker Prozessen
- **Timeout**: 120 Sekunden pro Request
- **Multi-stage Docker Build** für kleineres Image

Für höhere Last die Worker-Anzahl im Dockerfile anpassen:
```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "8", ...]
```

---

## Sicherheit

⚠️ **Wichtig**: 
- Das SECRET_TOKEN ist hart-codiert. Für Production sollte es:
  - In Environment Variablen ausgelagert sein
  - Regelmäßig rotiert werden
  - Über einen Secret Manager verwaltet werden
