FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps for asyncpg, geoalchemy2, rasterio, weasyprint, fiona
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev gcc g++ \
        libgdal-dev gdal-bin \
        libgeos-dev libproj-dev \
        libpango-1.0-0 libpangocairo-1.0-0 libcairo2 \
        libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info && \
    rm -rf /var/lib/apt/lists/*

# --------------- builder ---------------
FROM base AS builder

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir .

# --------------- runtime ---------------
FROM base AS runtime

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/uvicorn /usr/local/bin/uvicorn
COPY --from=builder /usr/local/bin/alembic /usr/local/bin/alembic

COPY alembic.ini ./
COPY migrations/ migrations/
COPY src/ src/

# Upload storage directory
RUN mkdir -p /data/uploads && chmod 777 /data/uploads
ENV UPLOAD_STORAGE_PATH=/data/uploads

EXPOSE 8000

CMD ["uvicorn", "openfmis.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
