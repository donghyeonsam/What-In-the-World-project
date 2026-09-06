FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY collection_kafka_producer_v2.py /app/collection_kafka_producer_v2.py
COPY registry.csv /app/registry.csv

ENTRYPOINT ["python", "/app/collection_kafka_producer_v2.py"]
