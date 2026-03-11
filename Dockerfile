# ============================================================
# AI Blog Automation — Dockerfile
# Python 앱 컨테이너 이미지
# ============================================================

FROM python:3.12-slim

# 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Playwright 브라우저 설치 (네이버 발행용, Phase 2에서 활성화)
# RUN pip install playwright && playwright install chromium --with-deps

# 작업 디렉토리
WORKDIR /app

# 의존성 설치 (캐시 활용을 위해 requirements.txt만 먼저 복사)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 앱 코드 복사
COPY . .

# 데이터/로그 디렉토리 생성
RUN mkdir -p data logs logs/costs

# 진입점
CMD ["python", "cli.py", "status"]
