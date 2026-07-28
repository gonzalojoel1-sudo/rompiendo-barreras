# =============================================================================
# Rompiendo Barreras - vps_backend - Dockerfile multi-arch
# =============================================================================
# Imagen base: python:3.11-slim (optimizada para ARM64/Oracle Cloud)
# Build: docker build -t rb_vps_backend:latest .
# Run:   docker run --rm -p 8765:8765 --env-file .env rb_vps_backend:latest
# =============================================================================

FROM python:3.11-slim

# Metadatos
LABEL org.opencontainers.image.title="Rompiendo Barreras - VPS Backend" \
      org.opencontainers.image.description="Orca Memory Bridge + Notion sync (Sprint 3)" \
      org.opencontainers.image.source="https://github.com/rompiendo-barreras/vps_backend" \
      org.opencontainers.image.licenses="Proprietary"

# Variables de entorno Python (logging sin buffer, sin .pyc)
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app

# Dependencias del sistema: build-essential (compilar wheels) + curl (salud, debug)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Crear usuario no-root para runtime
RUN groupadd --system --gid 1000 appuser \
    && useradd  --system --uid 1000 --gid appuser --create-home --shell /bin/bash appuser

WORKDIR /app

# --- Capa 1: dependencias (cache de Docker) ---
COPY vps_backend/requirements.txt /app/vps_backend/requirements.txt
RUN pip install --no-cache-dir -r /app/vps_backend/requirements.txt \
    && pip install --no-cache-dir "uvicorn[standard]>=0.27.0"

# --- Capa 2: codigo de la aplicacion ---
COPY notion_bridge /app/notion_bridge
COPY vps_backend  /app/vps_backend
COPY manifests    /app/manifests
COPY config       /app/config
COPY scripts      /app/scripts

# Directorio de datos persistentes (montado como volumen)
RUN mkdir -p /app/data /app/logs /app/context_vault \
    && chown -R appuser:appuser /app

# Cambiar a usuario no-root
USER appuser

# Configuracion de runtime (sobreescribible en docker-compose.yml / .env)
ENV SCRATCHPAD_PATH=/app/data/agent_scratchpad.json \
    APP_HOST=0.0.0.0 \
    APP_PORT=8765

EXPOSE 8765

WORKDIR /app/vps_backend

# Healthcheck nativo de Docker (sin dependencia de curl/wget en la imagen slim).
# Timeout 30s: en e2-micro bajo carga (rebuild paralelo) curl puede tardar >5s.
HEALTHCHECK --interval=30s --timeout=30s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request, json, sys; r = urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=20); d = json.loads(r.read()); sys.exit(0 if d.get('status') == 'ok' else 1)"

# Comando de arranque
CMD ["uvicorn", "orca_memory_bridge:app", "--host", "0.0.0.0", "--port", "8765"]
