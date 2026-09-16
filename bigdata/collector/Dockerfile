FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY collection_kafka_producer_v2.py /app/collection_kafka_producer_v2.py
COPY crawl_quality_v5.py /app/crawl_quality_v5.py
COPY safe_http.py /app/safe_http.py
COPY healthcheck.py /app/healthcheck.py
COPY registry.csv /app/registry.csv
COPY registry_50country.csv /app/registry_50country.csv

HEALTHCHECK --interval=30s --timeout=10s --start-period=5m --retries=3 \
    CMD ["python", "/app/healthcheck.py"]

ENTRYPOINT ["python", "/app/collection_kafka_producer_v2.py"]
