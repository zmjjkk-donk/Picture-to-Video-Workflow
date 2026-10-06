# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim@sha256:43ac6c60b8f89723f746e8a92ce91abd5017e627ce1ddfe4238355d3a30b772c AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
ARG VITE_API_BASE=/api
ENV VITE_API_BASE=${VITE_API_BASE}
RUN npm run build

FROM frontend-build AS frontend-test
RUN npm run test -- --reporter=dot --maxWorkers=1

FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3 AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_DATA_DIR=/app/data \
    IMAGEIO_FFMPEG_EXE=/usr/bin/ffmpeg
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home app \
    && mkdir -p /app/data \
    && chown app:app /app/data
COPY requirements.txt ./
RUN /usr/local/bin/python -m pip install -r requirements.txt \
    && /usr/local/bin/python -m pip check
COPY backend/__init__.py ./backend/__init__.py
COPY backend/app/ ./backend/app/
COPY README.md ./README.md
COPY --from=frontend-build /build/frontend/dist/ ./frontend/dist/
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["/usr/local/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).close()"]
CMD ["/usr/local/bin/python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--timeout-graceful-shutdown", "120"]
