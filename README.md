# Field-Service RAG Bot

A Retrieval-Augmented Generation (RAG) chatbot designed for field-service technicians. The bot answers questions about Miele appliance documentation by retrieving relevant content from a Qdrant cloud vector database and generating accurate answers through Azure OpenAI — served through a conversational web interface.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Repository Structure](#repository-structure)
- [Services](#services)
  - [Context Handler](#context-handler)
  - [Request Handler](#request-handler)
  - [Webpage](#webpage)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Step 1 – Configure Environment Variables](#step-1--configure-environment-variables)
  - [Step 2 – Populate the Vector Database](#step-2--populate-the-vector-database)
  - [Step 3 – Start All Services with Docker Compose](#step-3--start-all-services-with-docker-compose)
  - [Step 4 – Open the Frontend](#step-4--open-the-frontend)
- [Environment Variables Reference](#environment-variables-reference)
- [Configuration Reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

```
PDF Manuals
    │
    ▼
Context_Handler/create_vector_db.py  ──►  Qdrant Cloud (vector DB)
                                                │
                                                │ similarity search
                                                ▼
Browser  ◄──►  webpage/  ◄──►  Request_Handler (FastAPI)  ──►  Azure OpenAI API
                                      │
                                      └── fetches context from Context_Handler (Flask)
```

The system consists of three independent microservices that run on a shared Docker network (`rag-network`):

1. **Context Handler** (port 5000) – A Flask service that embeds incoming queries using `intfloat/multilingual-e5-large` via Hugging Face and retrieves the most relevant PDF chunks from a Qdrant cloud vector database. Supports optional model-name filtering with fuzzy matching.
2. **Request Handler** (port 8000) – A FastAPI service that manages chat sessions, uses Azure OpenAI tool calling to collect structured fault information (problem, model, error code), then fetches context from the Context Handler and calls Azure OpenAI to generate a grounded answer. Runs under Gunicorn + UvicornWorker.
3. **Webpage** (port 8080) – A self-contained single-page chat interface with speech-to-text input, text-to-speech output, and a light/dark theme toggle. Served by Nginx inside Docker.

---

## Repository Structure

```
field-service-rag-bot/
├── Context_Handler/
│   ├── create_vector_db.py        # One-time script: index PDFs into Qdrant
│   ├── context_webserver.py       # Flask entry point (POST /context)
│   ├── Context_Handler.py         # Thin wrapper around rag.py
│   ├── rag.py                     # Core retrieval logic (Qdrant + embeddings)
│   ├── pdf_sources.json           # Maps PDF stems to public source URLs
│   ├── pdfs/                      # Place appliance PDF manuals here
│   ├── requirements.txt
│   ├── docker-compose.yml         # Stand-alone compose for this service
│   └── README_DOCKER.md
├── Request_Handler/
│   ├── requesthandler.py          # FastAPI application
│   ├── system_prompt.txt          # System prompt loaded at startup
│   ├── form.json                  # Structured form for problem/model/error_code (filled by LLM tool calling)
│   ├── gunicorn.conf.py           # Gunicorn/UvicornWorker settings
│   ├── requirements.txt
│   └── docker-compose.yml
├── webpage/
│   ├── index.html                 # Chat UI (single-page app)
│   ├── script.js                  # Chat logic, STT, TTS
│   ├── styles.css                 # Light/dark theme styles
│   ├── Dockerfile
│   └── docker-compose.yml
├── docker-compose.yml             # Root compose – starts all three services
├── .env.example                   # Template for required environment variables
└── README.md
```

---

## Services

### Context Handler

**Directory:** `Context_Handler/`  
**Port:** `5000`  
**Author:** Marvin Palsbröker

#### Responsibilities

- Embeds queries using the `intfloat/multilingual-e5-large` Hugging Face model.
- Searches a Qdrant cloud collection for the most semantically similar PDF chunks.
- Returns formatted context including PDF name, source URL, page label, and chunk text.
- Supports optional model-name filtering with typo-tolerant fuzzy matching (`rag.py → resolve_document_name`).

#### Key files

| File | Purpose |
|------|---------|
| `context_webserver.py` | Flask server – exposes `POST /context` |
| `Context_Handler.py` | Wrapper that delegates to `rag.get_context()` |
| `rag.py` | Core retrieval: embedding, Qdrant query, fuzzy document matching |
| `create_vector_db.py` | One-time indexing script: reads PDFs, chunks, embeds, and upserts into Qdrant |
| `pdf_sources.json` | Maps PDF filenames (without extension) to their public download URLs |

#### API

**`POST /context`**

Requires `Authorization: Bearer <WEBSERVER_TOKEN>` header.

Request body:

```json
{
  "query": "How do I replace the heating element?",
  "model": "W1"
}
```

> `model` is optional. When provided, only PDFs whose filename fuzzy-matches the value are searched.

Response body:

```json
{
  "context": "PDF Name: siemens-waschmaschine-W1.pdf\nWebLink zum PDF: https://...\nSeite: 12\n..."
}
```
#### Retrieval settings (`rag.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `COLLECTION_NAME` | `Manuals_pdfs` | Qdrant collection to query |
| `SIMILARITY_TOP_RES` | `5` | Maximum number of chunks to return |
| `SIMILARITY_CUTOFF` | `0.80` | Minimum cosine similarity score |
| `DOCUMENT_MATCH_THRESHOLD` | `0.80` | Minimum fuzzy score for model-name filter |
| `embed_model` | `intfloat/multilingual-e5-large` | Hugging Face embedding model (1024-dim) |

#### Vector database (`create_vector_db.py`)

Run once (or whenever PDF manuals change) to populate the Qdrant collection.

| Setting | Value |
|---------|-------|
| Chunk size | 800 characters |
| Chunk overlap | 150 characters |
| Batch size | 50 nodes per upsert |
| Collection vector size | 1024 (matches `multilingual-e5-large`) |
| Distance metric | Cosine |

Place PDF files in `Context_Handler/pdfs/` before running the script. Optionally add source URLs to `pdf_sources.json` so the bot can link back to the original document.

```bash
# Run from the repository root
python Context_Handler/create_vector_db.py
```

---

### Request Handler

**Directory:** `Request_Handler/`  
**Port:** `8000`

#### Responsibilities

- Maintains a global conversation history (system prompt + user/assistant turns).
- Uses Azure OpenAI **tool calling** to extract structured information (problem description, product model name, error code) from the user's messages and stores it in `form.json`.
- Only fetches context from the Context Handler **after** the form has been fully filled (problem, product_model_name, and error_code are all non-empty).
- Calls Azure OpenAI chat completions and returns the answer to the frontend.
- Exposes session management so the frontend can reset conversation history.

#### Key files

| File | Purpose |
|------|---------|
| `requesthandler.py` | FastAPI application with `/api/chat` and `/api/session/init` endpoints |
| `system_prompt.txt` | System instructions loaded at startup (can be edited without code changes) |
| `form.json` | Structured form filled by the LLM via tool calling (problem, product_model_name, error_code) |
| `gunicorn.conf.py` | Gunicorn config: 1 UvicornWorker, port 8000, 120 s timeout |

#### Conversation flow

The Request Handler uses a **two-phase** approach per chat session:

1. **Phase 1 – Form filling**: Until all three fields in `form.json` are populated, each user message is sent to the LLM with a `fill_json_form` tool. The LLM extracts `problem`, `product_model_name`, and `error_code` from the conversation and calls the tool to populate the form.
2. **Phase 2 – Context-grounded answers**: Once the form is complete, the Context Handler is queried for relevant PDF chunks before each LLM call, and the answer is grounded in the retrieved documentation.

The session can be reset (resetting both conversation history and the form) via `POST /api/session/init`.

**`POST /api/chat`**

Request body:

```json
{
  "message": "My dishwasher shows error F-404. What should I do?",
  "sessionId": "abc123",
  "model": "PFD 401"
}
```

> `model` is optional. When provided, it is forwarded to the Context Handler for document filtering.

Response body:

```json
{
  "answer": "Error F-404 indicates a water inlet issue. Please check..."
}
```

**`POST /api/session/init`**

Resets the global conversation history to the initial system prompt.

Request body:

```json
{
  "sessionId": "abc123"
}
```

Response body:

```json
{
  "status": "ok",
  "sessionId": "abc123"
}
```

Interactive API docs (Swagger UI) are available at `http://localhost:8000/docs`.

#### Configuration

| Variable / Setting | Default | Description |
|--------------------|---------|-------------|
| `MAX_TOKENS` | `100` | Maximum tokens per Azure OpenAI response |
| `CONTEXT_HANDLER_URL` | `http://localhost:5000/context` | Context Handler endpoint (overridden in Docker) |
| `system_prompt.txt` | See file | System instructions for the LLM |
| `allow_origins` | `["*"]` | CORS – restrict before deploying to production |
| Azure `api_version` | `2024-02-01` | Azure OpenAI API version |

---

### Webpage

**Directory:** `webpage/`  
**Port (Docker):** `8080` → served by Nginx on internal port 80  

A self-contained single-page application that requires no build step.

| Feature | Description |
|---------|-------------|
| **Chat interface** | User and bot messages displayed as styled bubbles in a scrollable window |
| **Scroll helper** | Floating ⬇ button jumps to the latest message when the user scrolls up |
| **Light / dark theme** | Toggle button (🌙) switches the `data-theme` attribute; CSS custom properties handle theming |
| **Speech-to-Text (STT)** | 🎤 button uses the Web Speech API (`de-DE`); transcript is inserted into the input field. Supported in Chrome, Edge, and Safari |
| **Text-to-Speech (TTS)** | 🔇/🔊 toggle button enables or disables bot reply read-aloud via the Web Speech API (`de-DE`, prefers Google/Hedda German voice). **Off by default.** |
| **Backend URL** | Configured via `API_URL` in `script.js` (default: `http://localhost:8000/api/chat`) |

---

## Getting Started

### Prerequisites

- **Docker** and **Docker Compose** (v2) installed
- An **Azure OpenAI** resource with a deployed chat model (e.g. `gpt-4o-mini`)
- A **Qdrant** cloud cluster with API credentials
- A **Hugging Face** account token (for downloading the embedding model)
- A modern browser with Web Speech API support (Chrome, Edge, or Safari) for voice features

---

### Step 1 – Configure Environment Variables

Copy the example file and fill in all values:

```bash
cp .env.example .env
```

Edit `.env` with your credentials (see [Environment Variables Reference](#environment-variables-reference) for details).

> ⚠️ **Never commit `.env` to version control.** It is already listed in `.gitignore`.

---

### Step 2 – Populate the Vector Database

Run this once (or whenever PDF manuals change) to index documents into Qdrant.

1. Place your appliance PDF manuals in `Context_Handler/pdfs/`.
2. Optionally add source URLs for each PDF in `Context_Handler/pdf_sources.json`:

```json
{
  "my-appliance-manual": {
    "source": "https://example.com/manuals/my-appliance-manual.pdf"
  }
}
```

3. Run the indexing script (requires Python 3.10+ and the Context Handler dependencies):

```bash
pip install -r Context_Handler/requirements.txt
python Context_Handler/create_vector_db.py
```

Expected output:

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

### Step 3 – Start All Services with Docker Compose

From the repository root:

```bash
docker compose up --build
```

This starts three containers on the shared `rag-network`:

| Container | Image built from | Exposed port |
|-----------|-----------------|--------------|
| `context-handler` | `Context_Handler/` | 5000 |
| `request-handler-cont` | `Request_Handler/` | 8000 |
| `webpage_deployment` | `webpage/` | 8080 |

To run in detached mode:

```bash
docker compose up --build -d
```

To stop all services:

```bash
docker compose down
```

---

### Step 4 – Open the Frontend

Open `http://localhost:8080` in your browser.

You should see the chat interface. Type a question (or press 🎤 for voice input) and click **Send** to interact with the bot.

The Request Handler Swagger UI is available at `http://localhost:8000/docs`.

---

## Environment Variables Reference

All variables are defined in `.env` (copy from `.env.example`).

| Variable | Required by | Description |
|----------|------------|-------------|
| `AZURE_OPENAI_ENDPOINT` | Request Handler | Azure OpenAI resource endpoint URL |
| `AZURE_OPENAI_API_KEY` | Request Handler | Azure OpenAI API key |
| `AZURE_OPENAI_DEPLOYMENT` | Request Handler | Azure deployment / model name (e.g. `gpt-4o-mini`) |
| `QDRANT_URL` | Context Handler | URL of the Qdrant cloud cluster |
| `QDRANT_API_KEY` | Context Handler | Qdrant API key |
| `HF_TOKEN` | Context Handler | Hugging Face token for downloading the embedding model |
| `WEBSERVER_TOKEN` | Both | Shared bearer token used by the Request Handler to authenticate calls to the Context Handler. Docker Compose exposes this as `CONTEXT_HANDLER_TOKEN` inside the request-handler container. |

---

## Configuration Reference

| File | Setting | Description |
|------|---------|-------------|
| `Context_Handler/rag.py` | `COLLECTION_NAME` | Qdrant collection to query (default: `Manuals_pdfs`) |
| `Context_Handler/rag.py` | `SIMILARITY_TOP_RES` | Max number of retrieved chunks |
| `Context_Handler/rag.py` | `SIMILARITY_CUTOFF` | Minimum similarity score (0–1) |
| `Context_Handler/rag.py` | `DOCUMENT_MATCH_THRESHOLD` | Fuzzy score threshold for model-name filter |
| `Context_Handler/create_vector_db.py` | `COLLECTION_NAME` | Target Qdrant collection for indexing (default: `Manuals_pdfs`) |
| `Context_Handler/create_vector_db.py` | `BATCH_SIZE` | Nodes per upsert batch |
| `Context_Handler/pdf_sources.json` | — | Maps PDF stems to public source URLs |
| `Request_Handler/requesthandler.py` | `MAX_TOKENS` | Maximum tokens per LLM response |
| `Request_Handler/requesthandler.py` | `CONTEXT_HANDLER_URL` | Context Handler endpoint |
| `Request_Handler/requesthandler.py` | `allow_origins` | CORS allowed origins (restrict for production) |
| `Request_Handler/system_prompt.txt` | — | System instructions for the LLM (edit without code changes) |
| `Request_Handler/form.json` | — | Structured form (problem, product_model_name, error_code) populated by LLM tool calling; reset on session init |
| `Request_Handler/gunicorn.conf.py` | `workers` | Number of Gunicorn workers (default: 1) |
| `webpage/script.js` | `API_URL` | Request Handler endpoint called by the frontend |

---

## Troubleshooting

### Container does not start

```bash
# View logs for a specific service
docker compose logs context-handler
docker compose logs request-handler
docker compose logs webpage

# Rebuild from scratch
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Context Handler cannot connect to Qdrant

- Verify `QDRANT_URL` and `QDRANT_API_KEY` in your `.env` file.
- Check network connectivity (firewall, proxy).
- Ensure the Qdrant collection has been created by running `create_vector_db.py`.

### Request Handler returns 503

The Azure OpenAI client failed to initialise. Check that `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, and `AZURE_OPENAI_DEPLOYMENT` are all set in `.env`.

### No context is retrieved (empty answers)

- Confirm PDFs have been indexed (`create_vector_db.py` completed successfully).
- Ensure `COLLECTION_NAME` in `rag.py` matches the collection used during indexing.
- Lower `SIMILARITY_CUTOFF` in `rag.py` if too few chunks pass the threshold.
- Check the Context Handler is reachable: `curl http://localhost:5000/context` (expects `400` or `401`, not a connection error).

### Voice features do not work

The Web Speech API requires a secure context (HTTPS) or `localhost`. If accessing the app from another machine, serve the frontend over HTTPS or use a tunnelling tool like `ngrok`.
