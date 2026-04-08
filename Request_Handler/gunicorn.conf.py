# Gunicorn configuration for the Request_Handler (FastAPI / ASGI).
#
# Run with:
#   gunicorn -c gunicorn.conf.py requesthandler:app

import multiprocessing

# ---------------------------------------------------------------------------
# Worker settings
# ---------------------------------------------------------------------------
# UvicornWorker bridges Gunicorn's process management with FastAPI's ASGI loop.
worker_class = "uvicorn.workers.UvicornWorker"

# 2 * CPU cores + 1 is the standard recommendation for I/O-bound services.
workers = 1
# ---------------------------------------------------------------------------
# Networking
# ---------------------------------------------------------------------------
bind = "0.0.0.0:8000"

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------
# LLM calls may take several seconds; keep the timeout generous.
timeout = 120
keepalive = 5

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
loglevel = "info"
accesslog = "-"   # stdout
errorlog = "-"    # stdout

# ---------------------------------------------------------------------------
# Process lifecycle
# ---------------------------------------------------------------------------
# Recycle workers after this many requests to avoid memory leaks.
max_requests = 1000
max_requests_jitter = 100
