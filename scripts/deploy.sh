#!/usr/bin/env bash
# ============================================================
# AI Blog Automation — VPS 배포 스크립트
#
# 사용법:
#   chmod +x scripts/deploy.sh
#   ./scripts/deploy.sh
#
# 전제 조건:
#   - Docker + Docker Compose 설치됨
#   - .env 파일이 프로젝트 루트에 존재
#   - git으로 소스가 클론되어 있음
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$PROJECT_DIR/docker-compose.prod.yml"

echo "=========================================="
echo " AI Blog Automation — 배포 시작"
echo "=========================================="

# 1. 최신 코드 가져오기
echo "[1/5] git pull..."
cd "$PROJECT_DIR"
git pull origin main

# 2. .env 파일 확인
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo "❌ .env 파일이 없습니다. .env.example을 참고하여 생성하세요."
    exit 1
fi
echo "[2/5] .env 확인 완료"

# 3. Docker 이미지 빌드
echo "[3/5] Docker 이미지 빌드..."
docker compose -f "$COMPOSE_FILE" build

# 4. 컨테이너 시작
echo "[4/5] 컨테이너 시작..."
docker compose -f "$COMPOSE_FILE" up -d

# 5. 헬스체크 대기
echo "[5/5] 헬스체크 대기 (최대 60초)..."
RETRIES=12
for i in $(seq 1 $RETRIES); do
    if docker compose -f "$COMPOSE_FILE" exec -T scheduler python cli.py health > /dev/null 2>&1; then
        echo "✅ 헬스체크 통과!"
        break
    fi
    if [ "$i" -eq "$RETRIES" ]; then
        echo "⚠️  헬스체크 타임아웃. 로그를 확인하세요:"
        echo "  docker compose -f docker-compose.prod.yml logs"
        exit 1
    fi
    echo "  대기 중... ($i/$RETRIES)"
    sleep 5
done

echo ""
echo "=========================================="
echo " 배포 완료!"
echo "=========================================="
echo " 로그 확인: docker compose -f docker-compose.prod.yml logs -f"
echo " 상태 확인: docker compose -f docker-compose.prod.yml ps"
echo " 중지:     docker compose -f docker-compose.prod.yml down"
