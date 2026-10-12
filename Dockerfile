# Imagen web Fase 9: sin torch / chroma / gemini. Cabe en 512 MB con holgura.
FROM node:22-bookworm-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    FORWARDED_ALLOW_IPS=* \
    SESSION_HTTPS_ONLY=1

COPY requirements-web.txt .
RUN pip install --no-cache-dir -r requirements-web.txt \
 && python -c "import torch" 2>/dev/null && exit 1 || true \
 && python -c "import chromadb" 2>/dev/null && exit 1 || true \
 && python -c "import sentence_transformers" 2>/dev/null && exit 1 || true \
 && python -c "import google.genai" 2>/dev/null && exit 1 || true

COPY backend ./backend
COPY --from=frontend /frontend/dist ./frontend/dist

EXPOSE 8000

# --proxy-headers: X-Forwarded-For / Proto detrás de Render
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
