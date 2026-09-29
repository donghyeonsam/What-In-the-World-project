FROM python:3.12-slim

USER root

# 운영과 같은 HDBSCAN 구현 및 수치 라이브러리 버전을 사용한다.
RUN python3 -m pip install --no-cache-dir \
        'numpy==1.26.4' \
        'scikit-learn==1.6.1'

WORKDIR /opt/benchmark

# Benchmark 이미지는 운영 Streaming 코드와 분리하되 실제 클러스터링
# 알고리즘은 운영 소스의 동일 파일을 포함한다. Spark는 사용하지 않는다.
COPY spark/apps/issue_clustering.py /opt/benchmark/issue_clustering.py
COPY benchmark/apps/benchmark_common.py /opt/benchmark/benchmark_common.py
COPY benchmark/apps/prepare_datasets.py /opt/benchmark/prepare_datasets.py
COPY benchmark/apps/make_assignments.py /opt/benchmark/make_assignments.py
COPY benchmark/apps/worker.py /opt/benchmark/worker.py
COPY benchmark/apps/merge_results.py /opt/benchmark/merge_results.py

RUN useradd --create-home --uid 185 benchmark
USER benchmark
