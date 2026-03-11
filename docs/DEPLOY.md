# 배포 가이드

## 전체 배포 구조

```
[내 PC (Windows 11)]                    [GitHub]                      [VPS (나중에)]
     │                                      │                              │
     │  git push                            │                              │
     ├─────────────────────────────────────>│                              │
     │                                      │  GitHub Actions              │
     │                                      │  1. 테스트 실행              │
     │                                      │  2. SSH로 서버 접속          │
     │                                      │  3. git pull                 │
     │                                      │  4. docker compose up        │
     │                                      ├─────────────────────────────>│
     │                                      │                              │
     │                                      │                    [Docker Compose]
     │                                      │                    ├─ app (Python)
     │                                      │                    ├─ n8n
     │                                      │                    └─ redis
```

---

## 단계 1: 로컬 개발 환경 (Phase 1~2)

### 사전 요구사항
- Python 3.12+
- Git
- Docker Desktop (선택, 로컬 테스트용)

### 설정

```bash
# 프로젝트 클론
git clone https://github.com/YOUR_USERNAME/ai-blog-automation.git
cd ai-blog-automation

# 가상환경 생성
python -m venv .venv
.venv\Scripts\activate  # Windows

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
copy .env.example .env
# .env 파일에 ANTHROPIC_API_KEY 등 입력

# 초기화
python cli.py init
```

### 로컬에서 실행

```bash
# CLI로 글 생성 테스트
python cli.py generate "ChatGPT 새 기능" --content-type news_briefing

# Docker로 전체 서비스 실행 (선택)
docker compose up -d
```

---

## 단계 2: GitHub 저장소 설정

### 저장소 생성

1. GitHub에서 새 Private 레포 생성: `ai-blog-automation`
2. 로컬에서 연결:

```bash
git init
git add .
git commit -m "Initial commit: project setup"
git remote add origin https://github.com/YOUR_USERNAME/ai-blog-automation.git
git push -u origin main
```

### 브랜치 전략

main 브랜치 단독 사용 (혼자 개발):

```bash
# 일반적인 워크플로우
git add .
git commit -m "feat: writing_agent 구현"
git push
# → GitHub Actions가 자동으로 테스트 실행
# → (VPS 연결 후) 서버에 자동 배포
```

### 커밋 메시지 규칙

```
feat: 새 기능 추가
fix: 버그 수정
refactor: 코드 개선
config: 설정 변경
prompt: 프롬프트 수정
docs: 문서 수정
test: 테스트 추가
```

---

## 단계 3: VPS 배포 (Phase 3 이후)

### VPS 선택 및 가입

추천 순서:
1. **Oracle Cloud 무료 티어** — ARM 인스턴스 (4 OCPU, 24GB RAM 평생 무료)
2. **Vultr** — $5/월 (1 vCPU, 1GB RAM)
3. **AWS Lightsail** — $5/월

### VPS 초기 세팅

```bash
# 1. SSH 접속
ssh ubuntu@YOUR_SERVER_IP

# 2. Docker 설치
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# 재접속

# 3. Docker Compose 설치 (최신 버전은 Docker에 내장)
docker compose version  # 확인

# 4. 프로젝트 클론
git clone https://github.com/YOUR_USERNAME/ai-blog-automation.git
cd ai-blog-automation

# 5. 환경 변수 설정
cp .env.example .env
nano .env  # API 키 등 입력

# 6. 서비스 시작
docker compose up -d

# 7. 확인
docker compose ps        # 컨테이너 상태
docker compose logs -f   # 로그 실시간
```

### GitHub Actions 자동 배포 활성화

1. VPS에서 SSH 키 생성:
```bash
ssh-keygen -t ed25519 -C "github-actions-deploy"
cat ~/.ssh/id_ed25519.pub >> ~/.ssh/authorized_keys
cat ~/.ssh/id_ed25519  # 이 개인키를 GitHub에 등록
```

2. GitHub 저장소 → Settings → Secrets and variables → Actions:
   - `SERVER_HOST`: VPS IP 주소
   - `SERVER_USER`: ubuntu (또는 접속 계정)
   - `SERVER_SSH_KEY`: 위에서 생성한 개인키 전체 내용

3. `.github/workflows/ci-cd.yml`에서 deploy job 주석 해제

4. 이제 `git push`하면:
   - GitHub Actions가 테스트 실행
   - 테스트 통과 시 VPS에 SSH 접속
   - `git pull` + `docker compose up -d --build` 자동 실행

---

## 단계 4: 운영 관리

### 자주 쓰는 명령어

```bash
# 서비스 상태 확인
docker compose ps

# 로그 보기
docker compose logs -f app        # Python 앱 로그
docker compose logs -f n8n        # n8n 로그

# 서비스 재시작
docker compose restart app

# 전체 재빌드 (코드 변경 후)
docker compose up -d --build

# 서비스 중지
docker compose down

# DB 백업
cp data/blog.db data/blog.db.backup.$(date +%Y%m%d)
```

### n8n 접속

- URL: `http://YOUR_SERVER_IP:5678`
- 로그인: .env에 설정한 N8N_USER / N8N_PASSWORD

### 모니터링

```bash
# 디스크 사용량
df -h

# 메모리 사용량
free -h

# Docker 리소스 사용
docker stats
```

### 백업 자동화 (crontab)

```bash
# 매일 새벽 3시 DB 백업
crontab -e
# 추가:
0 3 * * * cp /home/ubuntu/ai-blog-automation/data/blog.db /home/ubuntu/backups/blog.db.$(date +\%Y\%m\%d)
```

---

## 환경별 .env 차이

| 변수 | 로컬 (PC) | 운영 (VPS) |
|------|-----------|-----------|
| DATABASE_URL | sqlite:///data/blog.db | 동일 (또는 PostgreSQL URL) |
| REDIS_URL | redis://localhost:6379 | redis://redis:6379 (Docker 내부) |
| N8N_USER | admin | (보안 강화된 ID) |
| N8N_PASSWORD | changeme | (보안 강화된 PW) |

---

## 문제 해결

### Docker Compose가 안 올라올 때
```bash
docker compose down
docker compose up -d --build --force-recreate
docker compose logs
```

### 디스크 공간 부족
```bash
docker system prune -a  # 사용하지 않는 이미지/컨테이너 정리
```

### n8n 접속 안 될 때
```bash
docker compose restart n8n
# 방화벽 확인
sudo ufw allow 5678
```
