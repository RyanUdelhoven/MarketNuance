FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN adduser --disabled-password --gecos "" --uid 10001 noodle

COPY app.py ./
COPY src/ ./src/
COPY --from=frontend-build /build/frontend/dist ./frontend/dist

RUN mkdir -p data/cache/sec data/snapshots data/exports \
    && chown -R noodle:noodle /app

USER noodle
EXPOSE 8765
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/stocks', timeout=3)"]

ENTRYPOINT ["python", "app.py"]
CMD ["--host", "0.0.0.0", "--port", "8765"]
