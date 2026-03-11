# RULES.md — AI 블로그 자동화 프로젝트

## 프로젝트 개요
네이버 블로그 + 티스토리에 AI 관련 콘텐츠를 자동 생성·발행하는 파이프라인.
주 7회 발행 목표, 양 플랫폼 동시 발행, 텔레그램 승인 게이트.

## 기술 스택
- Python 3.12+
- Claude API (Anthropic SDK) — AI 엔진
- n8n (셀프호스팅) — 워크플로우 오케스트레이션
- SQLite (초기) → PostgreSQL (확장 시)
- Redis — 캐시/큐
- Telegram Bot API — 승인 게이트
- Playwright — 네이버 발행 자동화
- Git — 코드 + 프롬프트 버전 관리

## 핵심 아키텍처

### 파이프라인 흐름
```
주제발굴 → 리서치 → 관점분화 → [네이버작성 | 티스토리작성] (병렬)
→ [네이버편집 | 티스토리편집] (병렬) → [네이버SEO | 티스토리SEO] (병렬)
→ 썸네일생성 → 텔레그램승인 → 발행 → 성과분석 → 피드백
```

### 플랫폼 차별화 (핵심!)
- **네이버**: "이해"시키기. 독자=완전 일반인. 설민석 강연 스타일. ~거든요 체.
- **티스토리**: "학습"시키기. 독자=IT종사 비개발자. 전문 리뷰어 스타일. ~입니다 체.
- 같은 주제를 다른 관점·깊이로 작성. 유사도 55% 이하 유지.

### 에이전트 실행 방식
- 부분 병렬: 네이버+티스토리 작성/편집/SEO를 동시 실행
- 에러: 자동 재시도 최대 3회 (지수 백오프 5초→15초→60초) → 실패 시 텔레그램 알림

## 폴더 구조
```
ai-blog-automation/
├── config/                    # 모든 설정 파일 (YAML)
│   ├── settings.yaml          # 전역 설정 (API 키 경로, DB 경로 등)
│   ├── categories.yaml        # 카테고리 체계
│   ├── content_types.yaml     # 글 유형 정의
│   ├── balance_rules.yaml     # 카테고리 균형 규칙
│   ├── data_sources.yaml      # 데이터 수집 소스
│   ├── thumbnail_template.yaml # 썸네일 설정
│   ├── platforms/             # 플랫폼별 설정
│   └── prompts/               # 프롬프트 템플릿
│       ├── writing/           # 글 유형별 (persona 포함)
│       ├── editing/           # 편집 단계별
│       └── seo/               # SEO 최적화
├── agents/                    # 에이전트 모듈
├── approval/                  # 텔레그램 승인 게이트
├── collectors/                # 데이터 수집기
├── publishers/                # 플랫폼별 발행기
├── analytics/                 # 성과 분석
├── database/                  # DB 모델 + 마이그레이션
├── utils/                     # 유틸리티
├── templates/thumbnails/      # 썸네일 템플릿
├── n8n-workflows/             # n8n 워크플로우 JSON
├── tests/                     # 테스트
└── logs/                      # 로그
```

## 코딩 컨벤션

### Python
- Python 3.12+ 기능 활용 (match-case, type hints 등)
- 비동기: asyncio + async/await (모든 에이전트는 async)
- 타입 힌트: 모든 함수에 필수
- Docstring: Google 스타일
- 변수명: snake_case, 클래스명: PascalCase
- 한 파일 최대 300줄 (초과 시 분리)

### 에이전트 구현 규칙
- 모든 에이전트는 BaseAgent를 상속
- Claude API 호출은 반드시 self.claude_call() 사용 (재시도, 비용 추적 내장)
- 에이전트 간 데이터 전달은 Pydantic 모델 사용
- 각 에이전트는 독립적으로 테스트 가능해야 함

### 설정 관리
- 하드코딩 금지. 모든 설정은 config/*.yaml 또는 .env에서 로드
- API 키는 절대 코드에 포함하지 않음 (.env 사용)
- 프롬프트는 config/prompts/*.yaml에서 관리

### 에러 처리
- 모든 에이전트 작업은 try-except로 감싸기
- AgentError 클래스 사용 (recoverable 플래그)
- 3회 재시도 후 실패 시 텔레그램 알림

### 로깅
- structlog 사용 (구조화 로그)
- 레벨: DEBUG(개발), INFO(운영), WARNING(주의), ERROR(에러), CRITICAL(긴급)
- 모든 API 호출에 비용/토큰 로깅

## 구현 로드맵 (Phase 1 MVP)

### 1주차: 프로젝트 뼈대
- [x] 프로젝트 구조 세팅
- [x] 설정 파일 작성
- [ ] Claude API 래퍼 (utils/claude_client.py)
- [ ] BaseAgent 구현 (agents/base_agent.py)
- [ ] DB 모델 (database/models.py)

### 2주차: 글 작성 파이프라인
- [ ] ContentSplitter (관점 분화)
- [ ] WritingAgent (플랫폼별 작성)
- [ ] EditorAgent (팩트체크→가독성→톤→맞춤법)
- [ ] 품질 평가 + 중복도 검사

### 3주차: 통합 + 포맷
- [ ] 플랫폼별 포맷 변환 (HTML/Markdown)
- [ ] 파이프라인 오케스트레이터
- [ ] 기본 CLI (수동 주제 입력 → 글 생성)
- [ ] 테스트

## Git / CI/CD / 배포

### Git
- 플랫폼: GitHub (Private 레포)
- 브랜치: main 단독 (혼자 개발)
- 커밋 규칙: `feat:`, `fix:`, `refactor:`, `config:`, `prompt:`, `docs:`, `test:`

### CI/CD
- GitHub Actions: main push 시 자동 테스트 → 서버 배포
- 테스트: pytest
- 배포: SSH로 VPS 접속 → git pull → docker compose up --build

### 배포
- 방식: Docker Compose (app + n8n + Redis)
- 초기: 로컬 PC에서 개발/테스트
- 이후: VPS로 이전 (Docker Compose라 이전 간단)
- 상세 가이드: docs/DEPLOY.md

## 환경 변수 (.env)
```
ANTHROPIC_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
TISTORY_APP_ID=...
TISTORY_SECRET_KEY=...
TISTORY_ACCESS_TOKEN=...
NAVER_CLIENT_ID=...
NAVER_CLIENT_SECRET=...
DATABASE_URL=sqlite:///data/blog.db
REDIS_URL=redis://localhost:6379
```
