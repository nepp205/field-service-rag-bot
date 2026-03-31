FROM python:3.11-slim

# HuggingFace Spaces requires the app to listen on port 7860
ENV PORT=7860

WORKDIR /app

# Install Python dependencies first (layer-cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Default ChromaDB path – overridden to /data/chroma_db when HF persistent
# storage is mounted (set via Space environment variable or keep default)
ENV CHROMA_PATH=/data/chroma_db

# Azure AI Foundry placeholders – set the real values as HF Space Secrets
ENV AZURE_OPENAI_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com/
ENV AZURE_OPENAI_API_KEY=PLACEHOLDER
ENV AZURE_OPENAI_DEPLOYMENT=gpt-4o
ENV AZURE_OPENAI_API_VERSION=2024-02-01

EXPOSE 7860

CMD ["uvicorn", "requesthandler:app", "--host", "0.0.0.0", "--port", "7860"]
