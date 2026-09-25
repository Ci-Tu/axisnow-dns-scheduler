# syntax=docker/dockerfile:1

# ---------- 前端构建 ----------
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 运行时 ----------
FROM python:3.12-slim

LABEL org.opencontainers.image.title="AxisNow DNS Scheduler" \
      org.opencontainers.image.description="Self-hosted console and pluggable scheduler for AxisNow DNS routing" \
      org.opencontainers.image.source="https://github.com/Ci-Tu/axisnow-dns-scheduler" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data \
    WEB_DIST=/app/web \
    PORT=4894 \
    PUID=1000 \
    PGID=1000

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/axisnow_scheduler ./axisnow_scheduler
COPY --from=web /web/dist ./web
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh && mkdir -p /app/data

EXPOSE 4894

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','4894')+'/healthz',timeout=4)"

ENTRYPOINT ["/entrypoint.sh"]
