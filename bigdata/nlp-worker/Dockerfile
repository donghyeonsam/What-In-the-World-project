# NLP Worker 실행을 위한 Python 기반 이미지
FROM python:3.12-slim

# 컨테이너 내부 작업 디렉토리
WORKDIR /app

# Python 의존성 파일 복사
COPY requirements.txt .

# 필요한 Python 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# NLP Worker 소스 코드 복사
COPY . .

# 컨테이너 실행 시 NLP Worker 시작
CMD ["python", "main.py"]