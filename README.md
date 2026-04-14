# Field-Service RAG Bot

Ein Retrieval-Augmented Generation (RAG) Chatbot für Außendienst-Techniker. Der Bot beantwortet Fragen zur Miele-Gerätedokumentation, indem er relevante Inhalte aus einer Qdrant Cloud-Vektordatenbank abruft und über Azure OpenAI präzise Antworten generiert – bereitgestellt über eine konversationelle Weboberfläche.

**Erstellt von:** Marvin Palsbröker, Tobias Stolle und Niklas Epp – Studierende an der FHDW, im Rahmen des Kurses „Advanced Topics in Computer Science".

---

## Inhaltsverzeichnis

- [Architekturübersicht](#architekturübersicht)
- [Repository-Struktur](#repository-struktur)
- [Dienste](#dienste)
  - [Context Handler](#context-handler)
  - [Request Handler](#request-handler)
  - [Webpage](#webpage)
- [Erste Schritte](#erste-schritte)
  - [Voraussetzungen](#voraussetzungen)
  - [Schritt 1 – Umgebungsvariablen konfigurieren](#schritt-1--umgebungsvariablen-konfigurieren)
  - [Schritt 2 – Vektordatenbank befüllen](#schritt-2--vektordatenbank-befüllen)
  - [Schritt 3 – Alle Dienste mit Docker Compose starten](#schritt-3--alle-dienste-mit-docker-compose-starten)
  - [Schritt 4 – Frontend öffnen](#schritt-4--frontend-öffnen)
- [Referenz der Umgebungsvariablen](#referenz-der-umgebungsvariablen)
- [Konfigurationsreferenz](#konfigurationsreferenz)
- [Fehlerbehebung](#fehlerbehebung)

---

## Architekturübersicht

```
PDF-Handbücher
    │
    ▼
Context_Handler/create_vector_db.py  ──►  Qdrant Cloud (Vektordatenbank)
                                                │
                                                │ Ähnlichkeitssuche
                                                ▼
Browser  ◄──►  webpage/  ◄──►  Request_Handler (FastAPI)  ──►  Azure OpenAI API
                                      │
                                      └── ruft Kontext vom Context_Handler (Flask) ab
```

Das System besteht aus drei unabhängigen Microservices, die in einem gemeinsamen Docker-Netzwerk (`rag-network`) betrieben werden:

1. **Context Handler** (Port 5000) – Ein Flask-Dienst, der eingehende Anfragen mit dem Modell `intfloat/multilingual-e5-large` von Hugging Face einbettet und die semantisch ähnlichsten PDF-Abschnitte aus der Qdrant Cloud-Vektordatenbank abruft. Unterstützt optionale Modellnamensfilterung mit Fuzzy-Matching. Erstellt von Marvin Palsbröker.
2. **Request Handler** (Port 8000) – Ein FastAPI-Dienst, der Chat-Sitzungen verwaltet, Kontext vom Context Handler abruft und die Azure OpenAI Chat Completions API aufruft, um eine fundierte Antwort zu generieren. Läuft unter Gunicorn + UvicornWorker.
3. **Webpage** (Port 8080) – Eine eigenständige Single-Page-Chat-Oberfläche mit Spracheingabe (STT), Sprachausgabe (TTS) und einem Hell-/Dunkel-Theme-Umschalter. Wird von Nginx innerhalb von Docker bereitgestellt.

---

## Repository-Struktur

```
field-service-rag-bot/
├── Context_Handler/
│   ├── create_vector_db.py        # Einmaliges Skript: PDFs in Qdrant indexieren
│   ├── context_webserver.py       # Flask-Einstiegspunkt (POST /context)
│   ├── Context_Handler.py         # Dünner Wrapper um rag.py
│   ├── rag.py                     # Kern-Retrieval-Logik (Qdrant + Embeddings)
│   ├── pdf_sources.json           # Verknüpft PDF-Dateinamen mit öffentlichen Quell-URLs
│   ├── pdfs/                      # Gerätebezogene PDF-Handbücher hier ablegen
│   ├── requirements.txt
│   ├── docker-compose.yml         # Eigenständiges Compose für diesen Dienst
│   └── README_DOCKER.md
├── Request_Handler/
│   ├── requesthandler.py          # FastAPI-Anwendung
│   ├── system_prompt.txt          # Beim Start geladener Systemprompt
│   ├── gunicorn.conf.py           # Gunicorn/UvicornWorker-Einstellungen
│   ├── requirements.txt
│   └── docker-compose.yml
├── webpage/
│   ├── index.html                 # Chat-UI (Single-Page-App)
│   ├── script.js                  # Chat-Logik, STT, TTS
│   ├── styles.css                 # Hell-/Dunkel-Theme-Styles
│   ├── Dockerfile
│   └── docker-compose.yml
├── docker-compose.yml             # Root-Compose – startet alle drei Dienste
├── .env.example                   # Vorlage für erforderliche Umgebungsvariablen
└── README.md
```

---

## Dienste

### Context Handler

**Verzeichnis:** `Context_Handler/`  
**Port:** `5000`  
**Autor:** Marvin Palsbröker

#### Aufgaben

- Einbettung von Anfragen mit dem Hugging Face Modell `intfloat/multilingual-e5-large`.
- Suche in einer Qdrant Cloud-Kollektion nach den semantisch ähnlichsten PDF-Abschnitten.
- Rückgabe von formatiertem Kontext inklusive PDF-Name, Quell-URL, Seitenangabe und Abschnittstext.
- Optionale Modellnamensfilterung mit tippfehlertoleranter Fuzzy-Suche (`rag.py → resolve_document_name`).

#### Wichtige Dateien

| Datei | Zweck |
|-------|-------|
| `context_webserver.py` | Flask-Server – stellt `POST /context` und `GET /health` bereit |
| `Context_Handler.py` | Wrapper, der an `rag.get_context()` delegiert |
| `rag.py` | Kern-Retrieval: Einbettung, Qdrant-Abfrage, Fuzzy-Dokumentenabgleich |
| `create_vector_db.py` | Einmaliges Indexierungsskript: liest PDFs, teilt sie in Abschnitte, bettet sie ein und lädt sie in Qdrant hoch |
| `pdf_sources.json` | Verknüpft PDF-Dateinamen (ohne Erweiterung) mit ihren öffentlichen Download-URLs |

#### API

**`POST /context`**

Erfordert den Header `Authorization: Bearer <WEBSERVER_TOKEN>`.

Anfrage-Body:

```json
{
  "query": "Wie tausche ich das Heizelement aus?",
  "model": "W1"
}
```

> `model` ist optional. Wenn angegeben, werden nur PDFs durchsucht, deren Dateiname dem Wert per Fuzzy-Matching entspricht.

Antwort-Body:

```json
{
  "context": "PDF Name: siemens-waschmaschine-W1.pdf\nWebLink zum PDF: https://...\nSeite: 12\n..."
}
```

**`GET /health`**

Gibt `200 OK` zurück, wenn der Dienst läuft.

#### Retrieval-Einstellungen (`rag.py`)

| Variable | Standardwert | Beschreibung |
|----------|-------------|--------------|
| `COLLECTION_NAME` | `Dev_Test` | Zu abfragende Qdrant-Kollektion |
| `SIMILARITY_TOP_RES` | `5` | Maximale Anzahl zurückgegebener Abschnitte |
| `SIMILARITY_CUTOFF` | `0.80` | Minimaler Cosinus-Ähnlichkeitswert |
| `DOCUMENT_MATCH_THRESHOLD` | `0.80` | Minimaler Fuzzy-Score für den Modellnamenfilter |
| `embed_model` | `intfloat/multilingual-e5-large` | Hugging Face Einbettungsmodell (1024-dimensional) |

#### Vektordatenbank (`create_vector_db.py`)

Einmalig ausführen (oder bei Änderungen an den PDF-Handbüchern), um die Qdrant-Kollektion zu befüllen.

| Einstellung | Wert |
|-------------|------|
| Chunk-Größe | 800 Zeichen |
| Chunk-Überlappung | 150 Zeichen |
| Batch-Größe | 50 Nodes pro Upsert |
| Kollektion-Vektorgröße | 1024 (passend zu `multilingual-e5-large`) |
| Distanzmetrik | Kosinus |

PDF-Dateien vor dem Ausführen des Skripts in `Context_Handler/pdfs/` ablegen. Optional können in `pdf_sources.json` Quell-URLs für jedes PDF hinterlegt werden, damit der Bot auf das Originaldokument verlinken kann.

```bash
# Vom Repository-Stammverzeichnis ausführen
python Context_Handler/create_vector_db.py
```

---

### Request Handler

**Verzeichnis:** `Request_Handler/`  
**Port:** `8000`

#### Aufgaben

- Verwaltung einer globalen Konversationshistorie (Systemprompt + Nutzer-/Assistenten-Nachrichten).
- Abruf von relevantem Kontext vom Context Handler vor jedem LLM-Aufruf.
- Aufruf der Azure OpenAI Chat Completions und Rückgabe der Antwort an das Frontend.
- Bereitstellung von Sitzungsverwaltung, damit das Frontend die Konversationshistorie zurücksetzen kann.

#### Wichtige Dateien

| Datei | Zweck |
|-------|-------|
| `requesthandler.py` | FastAPI-Anwendung mit den Endpunkten `/api/chat` und `/api/session/init` |
| `system_prompt.txt` | Beim Start geladene Systemanweisungen für das LLM (ohne Code-Änderungen editierbar) |
| `gunicorn.conf.py` | Gunicorn-Konfiguration: 1 UvicornWorker, Port 8000, 120 s Timeout |

#### System-Prompt

Der Systemprompt (`system_prompt.txt`) definiert das Verhalten des Bots:

- **Identität:** Spezialisierter technischer Support-Assistent für Miele-Außendienst-Techniker.
- **Antwortregeln:** Ausschließlich auf Basis der abgerufenen Dokumentation antworten – keine Halluzinationen. Jede Aussage muss mit einer Quellenangabe (Dokumentname, Seite) belegt werden.
- **JSON-Formular-Tool:** Bei Nennung von Problem, Modellname oder Fehlercode wird automatisch ein strukturiertes Formular (`fill_json_form`) befüllt, das den Kontext-Abruf triggert.
- **Antwortformat:** Strukturierte Antworten mit Abschnitten für Problemübersicht, Quelldokumentation, Diagnose & Lösung, Sicherheitshinweise, Wartungsempfehlungen und nächste Schritte.
- **Sprache:** Passt sich automatisch an die Sprache des Technikers an (Deutsch, Englisch o. a.).

#### API-Endpunkte

**`POST /api/chat`**

Anfrage-Body:

```json
{
  "message": "Mein Geschirrspüler zeigt Fehler F-404. Was soll ich tun?",
  "sessionId": "abc123",
  "model": "PFD 401"
}
```

> `model` ist optional. Wenn angegeben, wird es zur Dokumentenfilterung an den Context Handler weitergeleitet.

Antwort-Body:

```json
{
  "answer": "Fehler F-404 weist auf ein Problem mit dem Wasserzulauf hin. Bitte prüfen Sie..."
}
```

**`POST /api/session/init`**

Setzt die globale Konversationshistorie auf den anfänglichen Systemprompt zurück.

Anfrage-Body:

```json
{
  "sessionId": "abc123"
}
```

Antwort-Body:

```json
{
  "status": "ok",
  "sessionId": "abc123"
}
```

Interaktive API-Dokumentation (Swagger UI) ist unter `http://localhost:8000/docs` verfügbar.

#### Konfiguration

| Variable / Einstellung | Standardwert | Beschreibung |
|------------------------|-------------|--------------|
| `MAX_TOKENS` | `100` | Maximale Token pro Azure OpenAI-Antwort |
| `CONTEXT_HANDLER_URL` | `http://localhost:5000/context` | Context Handler-Endpunkt (in Docker überschrieben) |
| `system_prompt.txt` | Siehe Datei | Systemanweisungen für das LLM |
| `allow_origins` | `["*"]` | CORS – vor dem Produktionseinsatz einschränken |
| Azure `api_version` | `2024-02-01` | Azure OpenAI API-Version |
| Gunicorn `workers` | `1` | Anzahl der Gunicorn-Worker-Prozesse |
| Gunicorn `timeout` | `120` | Request-Timeout in Sekunden |

---

### Webpage

**Verzeichnis:** `webpage/`  
**Port (Docker):** `8080` → von Nginx auf internem Port 80 bereitgestellt  

Eine eigenständige Single-Page-Anwendung, die keinen Build-Schritt erfordert.

| Funktion | Beschreibung |
|----------|-------------|
| **Chat-Oberfläche** | Nutzer- und Bot-Nachrichten werden als gestaltete Sprechblasen in einem scrollbaren Fenster angezeigt |
| **Scroll-Helfer** | Schwebende ⬇-Schaltfläche springt zur neuesten Nachricht, wenn der Nutzer nach oben scrollt |
| **Hell-/Dunkel-Theme** | Umschalter (🌙) wechselt das `data-theme`-Attribut; CSS Custom Properties übernehmen das Theming |
| **Spracheingabe (STT)** | 🎤-Schaltfläche nutzt die Web Speech API (`de-DE`); Transkript wird in das Eingabefeld eingefügt. Unterstützt in Chrome, Edge und Safari |
| **Sprachausgabe (TTS)** | Jede Bot-Antwort wird über die Web Speech API (`de-DE`, bevorzugt Google/Hedda deutsche Stimme) vorgelesen |
| **Backend-URL** | Konfiguriert über `API_URL` in `script.js` (Standard: `http://localhost:8000/api/chat`) |
| **Markdown-Rendering** | Bot-Antworten werden mit `marked.js` gerendert und mit `DOMPurify` bereinigt |

---

## Erste Schritte

### Voraussetzungen

- **Docker** und **Docker Compose** (v2) installiert
- Eine **Azure OpenAI**-Ressource mit einem bereitgestellten Chat-Modell (z. B. `gpt-4o-mini`)
- Ein **Qdrant** Cloud-Cluster mit API-Zugangsdaten
- Ein **Hugging Face**-Account-Token (zum Herunterladen des Einbettungsmodells)
- Ein moderner Browser mit Web Speech API-Unterstützung (Chrome, Edge oder Safari) für Sprachfunktionen

---

### Schritt 1 – Umgebungsvariablen konfigurieren

Beispieldatei kopieren und alle Werte eintragen:

```bash
cp .env.example .env
```

Die `.env`-Datei mit den eigenen Zugangsdaten befüllen (Details siehe [Referenz der Umgebungsvariablen](#referenz-der-umgebungsvariablen)).

> ⚠️ **Die `.env`-Datei niemals in die Versionskontrolle einchecken.** Sie ist bereits in `.gitignore` eingetragen.

---

### Schritt 2 – Vektordatenbank befüllen

Einmalig ausführen (oder bei Änderungen an den PDF-Handbüchern), um Dokumente in Qdrant zu indexieren.

1. Geräte-PDF-Handbücher in `Context_Handler/pdfs/` ablegen.
2. Optional Quell-URLs für jedes PDF in `Context_Handler/pdf_sources.json` eintragen:

```json
{
  "mein-geraete-handbuch": {
    "source": "https://example.com/manuals/mein-geraete-handbuch.pdf"
  }
}
```

3. Das Indexierungsskript ausführen (erfordert Python 3.10+ und die Context Handler-Abhängigkeiten):

```bash
pip install -r Context_Handler/requirements.txt
python Context_Handler/create_vector_db.py
```

Erwartete Ausgabe:

```
Lade PDFs...
5 Dokumente geladen
Neue Qdrant Collection erstellt
Payload-Index für 'file_name' erstellt
Indexiere 312 Nodes in Batches...
Batch-Verarbeitung: 100%|████████| 7/7
Alle Nodes erfolgreich in Qdrant indexiert!
```

---

### Schritt 3 – Alle Dienste mit Docker Compose starten

Vom Repository-Stammverzeichnis aus:

```bash
docker compose up --build
```

Dadurch werden drei Container im gemeinsamen `rag-network` gestartet:

| Container | Image erstellt aus | Exposed Port |
|-----------|-------------------|--------------|
| `context-handler` | `Context_Handler/` | 5000 |
| `request-handler-cont` | `Request_Handler/` | 8000 |
| `webpage_deployment` | `webpage/` | 8080 |

Im Hintergrundmodus starten:

```bash
docker compose up --build -d
```

Alle Dienste stoppen:

```bash
docker compose down
```

---

### Schritt 4 – Frontend öffnen

`http://localhost:8080` im Browser öffnen.

Die Chat-Oberfläche sollte erscheinen. Eine Frage eingeben (oder 🎤 für Spracheingabe drücken) und auf **Send** klicken, um mit dem Bot zu interagieren.

Die Swagger UI des Request Handlers ist unter `http://localhost:8000/docs` erreichbar.

---

## Referenz der Umgebungsvariablen

Alle Variablen werden in `.env` definiert (Vorlage aus `.env.example` kopieren).

| Variable | Benötigt von | Beschreibung |
|----------|-------------|--------------|
| `AZURE_OPENAI_ENDPOINT` | Request Handler | Endpunkt-URL der Azure OpenAI-Ressource |
| `AZURE_OPENAI_API_KEY` | Request Handler | Azure OpenAI API-Schlüssel |
| `AZURE_OPENAI_DEPLOYMENT` | Request Handler | Azure-Deployment / Modellname (z. B. `gpt-4o-mini`) |
| `QDRANT_URL` | Context Handler | URL des Qdrant Cloud-Clusters |
| `QDRANT_API_KEY` | Context Handler | Qdrant API-Schlüssel |
| `HF_TOKEN` | Context Handler | Hugging Face Token zum Herunterladen des Einbettungsmodells |
| `WEBSERVER_TOKEN` | Beide | Gemeinsames Bearer-Token, das der Request Handler zur Authentifizierung gegenüber dem Context Handler verwendet |
| `CONTEXT_HANDLER_URL` | Request Handler | URL des Context Handler-Endpunkts (im Docker-Netzwerk: `http://context-handler:5000/context`) |
| `CONTEXT_HANDLER_TOKEN` | Request Handler | Token zur Authentifizierung am Context Handler (entspricht `WEBSERVER_TOKEN`) |

---

## Konfigurationsreferenz

| Datei | Einstellung | Beschreibung |
|-------|-------------|--------------|
| `Context_Handler/rag.py` | `COLLECTION_NAME` | Zu abfragende Qdrant-Kollektion |
| `Context_Handler/rag.py` | `SIMILARITY_TOP_RES` | Maximale Anzahl abgerufener Abschnitte |
| `Context_Handler/rag.py` | `SIMILARITY_CUTOFF` | Minimaler Ähnlichkeitswert (0–1) |
| `Context_Handler/rag.py` | `DOCUMENT_MATCH_THRESHOLD` | Fuzzy-Score-Schwellenwert für den Modellnamenfilter |
| `Context_Handler/create_vector_db.py` | `COLLECTION_NAME` | Ziel-Qdrant-Kollektion für die Indexierung |
| `Context_Handler/create_vector_db.py` | `BATCH_SIZE` | Nodes pro Upsert-Batch |
| `Context_Handler/pdf_sources.json` | — | Verknüpft PDF-Dateinamen mit öffentlichen Quell-URLs |
| `Request_Handler/requesthandler.py` | `MAX_TOKENS` | Maximale Token pro LLM-Antwort |
| `Request_Handler/requesthandler.py` | `CONTEXT_HANDLER_URL` | Context Handler-Endpunkt |
| `Request_Handler/requesthandler.py` | `allow_origins` | CORS-erlaubte Ursprünge (für Produktion einschränken) |
| `Request_Handler/system_prompt.txt` | — | Systemanweisungen für das LLM (ohne Code-Änderungen editierbar) |
| `Request_Handler/gunicorn.conf.py` | `workers` | Anzahl der Gunicorn-Worker (Standard: 1) |
| `Request_Handler/gunicorn.conf.py` | `timeout` | Request-Timeout in Sekunden (Standard: 120) |
| `webpage/script.js` | `API_URL` | Vom Frontend aufgerufener Request Handler-Endpunkt |

---

## Fehlerbehebung

### Container startet nicht

```bash
# Logs eines bestimmten Dienstes anzeigen
docker compose logs context-handler
docker compose logs request-handler
docker compose logs webpage

# Von Grund auf neu erstellen
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Context Handler kann keine Verbindung zu Qdrant herstellen

- `QDRANT_URL` und `QDRANT_API_KEY` in der `.env`-Datei überprüfen.
- Netzwerkkonnektivität prüfen (Firewall, Proxy).
- Sicherstellen, dass die Qdrant-Kollektion durch Ausführen von `create_vector_db.py` erstellt wurde.

### Request Handler gibt 503 zurück

Der Azure OpenAI-Client konnte nicht initialisiert werden. Überprüfen, ob `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY` und `AZURE_OPENAI_DEPLOYMENT` alle in der `.env`-Datei gesetzt sind.

### Es wird kein Kontext abgerufen (leere Antworten)

- Bestätigen, dass PDFs indexiert wurden (`create_vector_db.py` erfolgreich abgeschlossen).
- Sicherstellen, dass `COLLECTION_NAME` in `rag.py` mit der beim Indexieren verwendeten Kollektion übereinstimmt.
- `SIMILARITY_CUTOFF` in `rag.py` verringern, wenn zu wenige Abschnitte den Schwellenwert überschreiten.
- Den Health-Endpunkt des Context Handlers prüfen: `GET http://localhost:5000/health`.

### Sprachfunktionen funktionieren nicht

Die Web Speech API erfordert einen sicheren Kontext (HTTPS) oder `localhost`. Wenn auf die App von einem anderen Rechner zugegriffen wird, das Frontend über HTTPS bereitstellen oder ein Tunneling-Tool wie `ngrok` verwenden.
