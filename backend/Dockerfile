# ARGUS FloodOps API (FastAPI). Build context: repository root.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv/argus/backend
# rasterio / pyogrio manylinux wheels link against libexpat, which python:3.11-slim no longer ships
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY data/demo /srv/argus/data/demo
# curated real-data inputs (pack lock file, exercise plans, curated events/hydrology) — small text files only;
# the pack archives themselves are installed at first start into the /srv/argus/packs volume (never in the image)
COPY data/realdata /srv/argus/data/realdata
ENV ARGUS_REALDATA_DIR=/srv/argus/packs
RUN mkdir -p /srv/argus/data/imports/validation /srv/argus/data/processed /srv/argus/data/runtime /srv/argus/packs \
    && useradd -r -u 10001 argus && chown -R argus /srv/argus/data /srv/argus/packs
USER argus
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --retries=30 CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/api/system/health')"
# installs real-data packs once (verified), applies PostGIS migrations, starts the API; seeded when empty
CMD ["sh", "/srv/argus/backend/docker/entrypoint.sh"]
