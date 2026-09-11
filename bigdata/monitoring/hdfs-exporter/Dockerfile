FROM python:3.12-slim

WORKDIR /app
COPY hdfs_exporter.py /app/hdfs_exporter.py

EXPOSE 9120
USER 65534:65534

ENTRYPOINT ["python", "/app/hdfs_exporter.py"]
