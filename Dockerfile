# syntax=docker/dockerfile:1
# Backend image: FastAPI + LangGraph agents + RAG in ONE process, one container.
# The frontend has its own Dockerfile (frontend/Dockerfile).
# Every choice here traces to context/final_docker_descision.md.
#
# NOT in this image (see .dockerignore, an allowlist):
#   knowledge_base/ logs/ uploads/ outputs/   volumes, mounted at /app/<name>
#   the Hugging Face models                   a volume, mounted at /models (fragile: see the reminders)
#   tests/ test_work/ .env .venv .git         never
FROM python:3.12-slim

# HF_HOME: where the models volume is mounted (decision 3).
# The two PYTHON* and two PIP* settings are plain Docker hygiene, not project decisions.
ENV HF_HOME=/models \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 1. CPU-only PyTorch first, from the CPU index (decision 2). Its own layer: it rarely changes.
RUN pip install torch==2.12.1 --index-url https://download.pytorch.org/whl/cpu

# 2. Everything else from the frozen list (decision 7). Copied alone, so editing code reinstalls nothing.
COPY requirements.lock ./
RUN pip install -r requirements.lock

# 3. Non-root user (decision 1). The uid is fixed at 10001 so the host folders can be chowned to match.
#    The empty mount points are created and owned by it; the code stays owned by root.
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin app \
 && mkdir -p /app/knowledge_base /app/logs /app/uploads /app/outputs /models \
 && chown 10001:10001 /app/knowledge_base /app/logs /app/uploads /app/outputs /models

# 4. The code, and only the code. .dockerignore enforces the same list.
COPY config.py ./
COPY agents ./agents
COPY backend ./backend
COPY evaluation ./evaluation
COPY learning ./learning
COPY state ./state
COPY utils ./utils
COPY vectordb ./vectordb
COPY prompts ./prompts
COPY scripts/frontend_api.py ./scripts/

USER app
EXPOSE 8000

# Decision 6: a HEALTHCHECK on /api/health, the one open route. It costs nothing because the
# models load lazily on the first run. No curl in the slim image, so Python makes the request.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

# Decision 1: --host 0.0.0.0 (or the port is unreachable from outside the container)
# and --workers 1 (the run registry is in memory; SQLite and Chroma allow one writer).
CMD ["uvicorn", "scripts.frontend_api:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
