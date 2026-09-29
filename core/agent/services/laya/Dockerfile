# The System-1 decision service. Checkpoint arrives by VOLUME (read-only mount)
# or an HF id in LAYA_CHECKPOINT — weights are never baked into the image
# (gate:licenses records baked weights in the SBOM; volumes keep images small).
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir ".[runtime,mcp]"

EXPOSE 8400
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
    CMD python -c "import urllib.request;import sys;r=urllib.request.urlopen('http://127.0.0.1:8400/health',timeout=3);sys.exit(0 if r.status==200 else 1)"
CMD ["uvicorn", "laya_svc.main:app", "--host", "0.0.0.0", "--port", "8400"]
