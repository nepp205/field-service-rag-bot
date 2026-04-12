# Von GitHub Copilot generiert, angepasst von Niklas
# Gunicorn-Konfiguration für den Request_Handler (FastAPI / ASGI)

worker_class = "uvicorn.workers.UvicornWorker"  # asgi-worker für fastapi
workers = 1  # ein worker reicht für den anfang

bind = "0.0.0.0:8000"  # auf allen interfaces lauschen

timeout = 120  # anfragen dürfen max. 120s dauern
keepalive = 5  # verbindung 5s offen halten nach antwort

loglevel = "info"  # log-level
accesslog = "-"  # zugriffslogs nach stdout
errorlog = "-"   # fehlerlogs nach stdout

max_requests = 1000        # worker nach 1000 anfragen neu starten (memory leak vermeiden)
max_requests_jitter = 100  # zufälliger offset damit nicht alle gleichzeitig neustarten
