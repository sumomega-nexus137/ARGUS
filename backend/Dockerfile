# ARGUS FloodOps API (FastAPI). Build context: repository root.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/argus/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY data/demo /srv/argus/data/demo
RUN mkdir -p /srv/argus/data/imports/validation /srv/argus/data/processed && useradd -r -u 10001 argus && chown -R argus /srv/argus/data
USER argus
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --retries=10 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/system/health')"
# PostgreSQL/PostGIS: apply migrations first; SQLite demo creates tables on startup. Demo data is seeded when empty.
CMD ["sh", "-c", "case \"$ARGUS_DATABASE_URL\" in postgresql*) alembic upgrade head ;; esac && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
