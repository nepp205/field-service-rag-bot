# Field-Service RAG Bot

A Retrieval-Augmented Generation (RAG) chatbot designed for field-service technicians. The bot answers questions about appliance documentation by searching a local vector database built from PDF manuals and returning relevant answers through a conversational web interface.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Repository Structure](#repository-structure)
- [Modules & Components](#modules--components)
  - [DB – Vector Database Builder](#db--vector-database-builder)
  - [requesthandler.py – FastAPI Backend](#requesthandlerpy--fastapi-backend)
  - [webpage – Frontend UI](#webpage--frontend-ui)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Step 1 – Build the Vector Database](#step-1--build-the-vector-database)
  - [Step 2 – Start the Backend API](#step-2--start-the-backend-api)
  - [Step 3 – Open the Frontend](#step-3--open-the-frontend)
- [Configuration](#configuration)

---

## Architecture Overview

```
PDF Manuals  ──►  DB/build_db.py  ──►  ChromaDB (./chroma_db/)
                                              │
                                              ▼
Browser  ◄──►  webpage/  ◄──►  requesthandler.py (FastAPI)  ──►  RAG Pipeline (planned)
```

1. **DB layer** – Extracts text from PDF manuals, splits it into overlapping chunks, embeds each chunk with a sentence-transformer model, and stores everything in a local ChromaDB instance.
2. **API layer** – A FastAPI application that receives chat messages from the browser and (once the RAG pipeline is wired in) queries ChromaDB to retrieve the most relevant chunks before sending them to an LLM.
3. **Frontend layer** – A plain HTML/CSS/JS chat interface with speech-to-text input and text-to-speech output.

---

## Repository Structure

```
field-service-rag-bot/
├── DB/
│   ├── build_db.py                              # Builds the ChromaDB vector database from PDFs
│   └── Miele-PFD-401-MasterLine-Bedienungsanleitung.pdf  # Example appliance manual
├── webpage/
│   ├── index.html                               # Chat UI (single-page app)
│   ├── script.js                                # Chat logic, STT, TTS
│   └── styles.css                               # Light/dark theme styles
├── requesthandler.py                            # FastAPI backend (POST /api/chat)
└── README.md
```

---

## Modules & Components

### DB – Vector Database Builder

**File:** `DB/build_db.py`

This script turns one or more PDF manuals into a searchable vector database.

| Step | What it does |
|------|-------------|
| **Text extraction** | Uses `pypdf` to read every page of the PDF and concatenate the plain text. |
| **Chunking** | Splits the raw text into fixed-size character windows (default 350 characters) with a configurable overlap (default 80 characters) so that no sentence is cut off at a chunk boundary. |
| **Embedding** | Loads the `all-MiniLM-L6-v2` sentence-transformer model (384-dimensional embeddings, fast on CPU) and converts every chunk into a dense vector. |
| **Storage** | Persists all chunks and their embeddings in a local ChromaDB collection (`mini_rag_test`) under `./chroma_db/`. |
| **Test query** | After building, the script runs a sample similarity search ("Filter wechseln") and prints the top-5 matching chunks so you can verify the database works. |

Key settings at the top of the file:

| Variable | Default | Description |
|----------|---------|-------------|
| `PDF_PATH` | `./field-service-rag-bot/DB/Miele-PFD-401-MasterLine-Bedienungsanleitung.pdf` | Path to the source PDF |
| `CHUNK_SIZE` | `350` | Characters per chunk |
| `CHUNK_OVERLAP` | `80` | Character overlap between consecutive chunks |
| `COLLECTION_NAME` | `mini_rag_test` | ChromaDB collection name |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer model used for embeddings |

---

### requesthandler.py – FastAPI Backend

**File:** `requesthandler.py`

Provides the HTTP API consumed by the frontend.

| Item | Detail |
|------|--------|
| **Framework** | [FastAPI](https://fastapi.tiangolo.com/) with Uvicorn as the ASGI server |
| **CORS** | All origins are allowed during the demo phase (restrict `allow_origins` before deploying to production) |
| **Endpoint** | `POST /api/chat` |
| **Request body** | `{ "message": "<user question>", "sessionId": "<session id>" }` |
| **Response body** | `{ "answer": "<bot answer>" }` |
| **Current behaviour** | Demo stub – echoes the user's message back as `"Demo-Antwort für: <message>"` |
| **Planned behaviour** | Replace the stub with a call to the RAG pipeline (`rag_core.RAG`) and an Azure OpenAI LLM to return a real document-grounded answer |

Interactive API docs are available at `http://localhost:8000/docs` once the server is running.

---

### webpage – Frontend UI

**Files:** `webpage/index.html`, `webpage/script.js`, `webpage/styles.css`

A self-contained single-page chat application that requires no build step.

| Feature | Description |
|---------|-------------|
| **Chat interface** | Displays user and bot messages as styled bubbles in a scrollable conversation window |
| **Scroll helper** | A floating ⬇ button appears when the user scrolls up and jumps back to the latest message with one click |
| **Light / dark theme** | Toggle button (🌙) switches the `data-theme` attribute on `<html>`; styles in `styles.css` respond via CSS custom properties |
| **Speech-to-Text (STT)** | The 🎤 microphone button triggers the Web Speech API (language: `de-DE`); the recognised transcript is placed in the text input automatically. Supported in Chrome, Edge, and Safari |
| **Text-to-Speech (TTS)** | Every bot reply is read aloud via the Web Speech API (`de-DE`, prefers a Google or Hedda German voice when available) |
| **Source documents** | Bot responses may include a collapsible panel showing the source documentation title and an embedded iframe preview |
| **Backend URL** | Hard-coded to `http://localhost:8000/api/chat` (change `API_URL` in `script.js` if the backend runs on a different host/port) |

---

## Getting Started

### Prerequisites

- **Python 3.10+**
- **pip** (or a virtual-environment manager such as `venv` or `conda`)
- A modern browser with Web Speech API support (Chrome, Edge, or Safari) for voice features

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/nepp205/field-service-rag-bot.git
cd field-service-rag-bot

# 2. Create and activate a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install Python dependencies
pip install fastapi uvicorn pypdf sentence-transformers chromadb
```

---

### Step 1 – Build the Vector Database

Run this once (or whenever you add new PDFs) to populate the ChromaDB database.

```bash
# From the repository root
python DB/build_db.py
```

Expected output:

```
Lade PDF ............. DB/Miele-PFD-401-MasterLine-Bedienungsanleitung.pdf
Extrahierter Text:    12,345 Zeichen
Teile in Chunks ...... Erzeugt 47 Chunks
Lade Embedding-Modell: all-MiniLM-L6-v2
Verbinde mit Chroma (lokal, speichert in ./chroma_db/)
Speichere Chunks in Vektordatenbank ...
Fertig gespeichert!

Query: Filter wechseln
  1. Score: 0.3412   |   ...
```

The database is saved to `./chroma_db/` in the current directory.

> **Tip:** To index a different PDF, update `PDF_PATH` at the top of `DB/build_db.py` before running the script.

---

### Step 2 – Start the Backend API

```bash
# From the repository root
uvicorn requesthandler:app --reload
```

The API will be available at `http://localhost:8000`.  
Open `http://localhost:8000/docs` in your browser to explore the interactive Swagger UI.

---

### Step 3 – Open the Frontend

Open `webpage/index.html` directly in your browser:

```bash
# macOS
open webpage/index.html

# Linux
xdg-open webpage/index.html

# Windows
start webpage/index.html
```

Alternatively, serve it with any static file server to avoid browser CORS restrictions:

```bash
# Python built-in server (from the webpage/ directory)
cd webpage
python -m http.server 5500
# Then navigate to http://localhost:5500
```

You should now see the chat interface. Type a question and click **Send** (or press **Enter**) to interact with the bot.

---

## Configuration

| File | Setting | Description |
|------|---------|-------------|
| `DB/build_db.py` | `PDF_PATH` | Path to the PDF manual to index |
| `DB/build_db.py` | `CHUNK_SIZE` / `CHUNK_OVERLAP` | Controls granularity of text chunks |
| `DB/build_db.py` | `COLLECTION_NAME` | ChromaDB collection to write to |
| `DB/build_db.py` | `EMBEDDING_MODEL` | Sentence-transformer model name |
| `requesthandler.py` | `allow_origins` | Restrict CORS origins before deploying to production |
| `webpage/script.js` | `API_URL` | Backend URL (default: `http://localhost:8000/api/chat`) |
| `webpage/script.js` | `SESSION_ID` | Session identifier sent with every request |