# Claude Code Agent Teams 가이드

> AI Blog Automation 프로젝트에서 Agent Teams를 활용하여
> 병렬로 모듈을 개발하는 방법을 안내합니다.

---

## Agent Teams란?

여러 Claude Code 인스턴스가 하나의 팀처럼 협업하는 기능입니다.
한 세션이 팀 리더(Team Lead) 역할을 하고, 나머지가 팀원(Teammate)으로 병렬 작업합니다.

일반 멀티 터미널과 다른 점은 **에이전트 간 소통이 가능**하다는 것입니다.
팀원 A가 API 인터페이스를 변경하면, 팀원 B에게 "인터페이스가 바뀌었어"라고 알릴 수 있어요.

---

## 사전 요구사항

| 항목 | 요구사항 |
|------|----------|
| Claude Code 버전 | v2.1.32 이상 |
| 모델 | Opus 4.6 (Agent Teams에 필요) |
| 플랜 | Claude Max 구독 (Momo 현재 사용 중) |
| 터미널 | PowerShell (Windows, tmux 없이도 가능) |

### 버전 확인

```powershell
claude --version
# v2.1.32 이상이어야 함

# 최신 버전 업데이트
npm update -g @anthropic-ai/claude-code
```

---

## 설정 방법

### 방법 1: settings.json에 추가 (권장, 영구 적용)

```powershell
# Claude Code 설정 파일 위치 확인
# Windows: %USERPROFILE%\.claude\settings.json

# 설정 파일 열기
notepad $env:USERPROFILE\.claude\settings.json
```

settings.json에 아래 내용 추가:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

※ 이미 다른 설정이 있으면 env 안에 추가만 하세요.

### 방법 2: 환경 변수로 설정 (임시, 세션마다)

```powershell
# PowerShell에서 실행
$env:CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS = "1"
claude
```

### 설정 확인

Claude Code 실행 후 물어보세요:

```
agent teams 기능이 활성화되어 있어?
```

응답: "Yes, agent teams are enabled (experimental feature)."

---

## 이 프로젝트에서의 Agent Teams 활용법

### 핵심 원칙

Agent Teams는 **서로 다른 파일을 동시에 작업할 때** 가장 효과적입니다.
같은 파일을 여러 에이전트가 수정하면 충돌이 발생하므로 피해야 합니다.

이 프로젝트는 모듈이 명확히 분리되어 있어서 Agent Teams에 매우 적합합니다.

### 추천 팀 구성 — Phase 1 MVP

Phase 1에서는 3개 에이전트 팀이 최적입니다:

```
[팀 리더 (내 메인 세션)]
    ├── 팀원 1: 글 작성 파이프라인 담당
    │   → content_splitter.py + writing_agent.py
    │
    ├── 팀원 2: 편집 파이프라인 담당
    │   → editor_agent.py + utils/text_utils.py
    │
    └── 팀원 3: 테스트 + 품질 관리 담당
        → tests/ 폴더 전체 + 통합 테스트
```

### 실제 사용 예시

Claude Code에서 이렇게 지시하세요:

```
RULES.md를 읽고 Phase 1 MVP를 구현하자.

에이전트 팀을 만들어줘. 3명의 팀원이 필요해:

팀원 1 - "Writer" (글 작성 담당):
- agents/content_splitter.py 구현 (관점 분화 에이전트)
- agents/writing_agent.py 구현 (플랫폼별 글 작성 에이전트)
- config/prompts/writing/ 폴더의 페르소나 YAML을 참고해서 구현
- 기존 base_agent.py와 data_models.py를 상속/활용

팀원 2 - "Editor" (편집 담당):
- agents/editor_agent.py 구현 (팩트체크, 가독성, 톤 검수)
- utils/text_utils.py 구현 (한국어 텍스트 처리 유틸리티)
- 품질 평가 로직 구현

팀원 3 - "Tester" (테스트 담당):
- tests/test_content_splitter.py 작성
- tests/test_writing_agent.py 작성
- tests/test_editor_agent.py 작성
- 팀원 1, 2가 구현을 완료하면 테스트 실행

각 팀원은 자기 파일만 수정하고, 다른 팀원의 파일은 건드리지 마.
공통 파일(base_agent.py, data_models.py)은 읽기만 해.
```

### 추천 팀 구성 — Phase 2

```
[팀 리더]
    ├── 팀원 1: SEO 담당
    │   → agents/seo_agent.py (네이버 + 구글 SEO)
    │
    ├── 팀원 2: 발행 담당
    │   → publishers/naver_publisher.py + publishers/tistory_publisher.py
    │
    └── 팀원 3: 승인 게이트 담당
        → approval/telegram_bot.py + approval/preview_generator.py
```

### 추천 팀 구성 — Phase 3

```
[팀 리더]
    ├── 팀원 1: RSS/웹 수집 담당
    │   → collectors/rss_collector.py + collectors/web_scraper.py
    │
    ├── 팀원 2: API 수집 담당
    │   → collectors/reddit_collector.py + collectors/trend_collector.py
    │
    └── 팀원 3: 주제 선정 + 리서치 담당
        → agents/topic_curator_agent.py + agents/research_agent.py
```

---

## 팀 운영 팁

### 1. 파일 충돌 방지 규칙

CLAUDE.md (프로젝트 루트)에 아래 내용을 추가하면 팀원들이 자동으로 따릅니다:

```markdown
## Agent Teams 규칙

### 파일 소유권
- 각 팀원은 할당된 파일만 수정합니다
- 공통 파일 (base_agent.py, data_models.py, models.py)은 읽기 전용입니다
- 공통 파일 수정이 필요하면 팀 리더에게 요청합니다

### 소통 규칙
- 인터페이스 변경 시 반드시 다른 팀원에게 알립니다
- data_models.py의 Pydantic 모델을 사용해서 데이터를 주고받습니다
- 구현 완료 시 팀 리더에게 보고합니다
```

### 2. 키보드 단축키

| 단축키 | 기능 |
|--------|------|
| Shift + ↑/↓ | 팀원 세션 선택 |
| Ctrl + T | 작업 목록 보기 |
| Enter | 선택한 세션 열기 |
| Escape | 현재 작업 중단 |

### 3. 팀원과 직접 대화

팀 리더를 거치지 않고 특정 팀원에게 직접 지시할 수 있습니다:

```
# Shift+↑/↓로 팀원 선택 후 Enter
# 해당 팀원 세션에서 직접 지시:

writing_agent.py에서 네이버 버전 작성 시 humor_level 파라미터를
config에서 읽어오도록 수정해줘.
```

### 4. 팀 종료

작업이 끝나면 반드시 정리하세요:

```
모든 팀원에게 작업을 마무리하고 종료하라고 알려줘.
그리고 팀을 정리해줘.
```

---

## 비용 및 주의사항

### 토큰 비용

Agent Teams는 팀원 수만큼 토큰을 소비합니다:

| 구성 | 토큰 사용량 (대략) |
|------|-------------------|
| 단일 세션 | 1x (기준) |
| 팀원 2명 | 2.5~3x |
| 팀원 3명 | 3.5~4x |

Phase 1 MVP 기준으로, 3명 팀으로 하루 작업하면 약 $3~8 정도 예상됩니다.
Claude Max 구독이면 사용량 한도 내에서 추가 비용 없이 사용 가능합니다.

### 주의사항

1. **실험적 기능**: 아직 실험 단계라 가끔 세션 복원이 안 되거나 예상치 못한 동작이 있을 수 있습니다.

2. **같은 파일 수정 금지**: 두 팀원이 같은 파일을 수정하면 충돌합니다. 반드시 파일 소유권을 명확히 나누세요.

3. **종료가 느릴 수 있음**: 팀원이 현재 작업을 마치고 종료하므로 시간이 걸릴 수 있습니다.

4. **Windows 제한**: tmux 분할 화면은 Windows에서 지원되지 않지만, in-process 모드는 정상 동작합니다. 팀원 세션 간 전환은 키보드 단축키로 가능합니다.

---

## Subagent vs Agent Teams 비교

이 프로젝트에서 언제 뭘 쓸지 정리:

| 상황 | 추천 도구 | 이유 |
|------|----------|------|
| 여러 모듈 동시 구현 | **Agent Teams** | 독립적인 파일, 팀원 간 소통 필요 |
| 파일 하나 리팩토링 | **단일 세션** | 같은 파일 작업, 병렬 불필요 |
| 여러 소스 리서치 | **Subagent** | 빠르게 조사 후 보고, 소통 불필요 |
| 버그 원인 탐색 | **Agent Teams** | 여러 가설 병렬 테스트 |
| 테스트 작성 | **Agent Teams** | 모듈별 독립적 테스트 파일 |

---

## 프로젝트 CLAUDE.md 설정

프로젝트 루트에 CLAUDE.md를 만들면 모든 팀원이 자동으로 참조합니다:

```powershell
# 프로젝트 루트에 생성
# ai-blog-automation/CLAUDE.md
```

```markdown
# AI Blog Automation — Claude Code 지침

## 프로젝트 이해
- RULES.md를 먼저 읽고 전체 아키텍처를 파악하세요
- config/ 폴더의 YAML 파일들이 모든 설정의 근원입니다
- agents/data_models.py의 Pydantic 모델로 에이전트 간 데이터를 주고받습니다

## 코딩 규칙
- 모든 에이전트는 agents/base_agent.py의 BaseAgent를 상속합니다
- Claude API 호출은 반드시 self.claude_call()을 사용합니다 (재시도, 비용 추적 내장)
- 타입 힌트 필수, Google 스타일 Docstring 필수
- 하드코딩 금지, 설정은 config/*.yaml에서 로드

## Agent Teams 규칙
- 각 팀원은 할당된 파일만 수정합니다
- 공통 파일 수정이 필요하면 팀 리더에게 요청합니다
- 인터페이스 변경 시 다른 팀원에게 알립니다
- 구현 완료 시 팀 리더에게 보고합니다

## 파일 소유권 (Phase 1)
- Writer 팀원: agents/content_splitter.py, agents/writing_agent.py
- Editor 팀원: agents/editor_agent.py, utils/text_utils.py
- Tester 팀원: tests/ 폴더 전체
- 공통 (읽기 전용): agents/base_agent.py, agents/data_models.py, database/models.py, utils/claude_client.py

## 테스트
- 모든 에이전트는 독립적으로 테스트 가능해야 합니다
- pytest 사용, 비동기 테스트는 pytest-asyncio 사용
```

---

## 빠른 시작 체크리스트

```
□ Claude Code v2.1.32 이상 확인
□ settings.json에 CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: "1" 추가
□ Claude Code 재시작
□ "agent teams 기능 활성화 확인" 질문으로 확인
□ 프로젝트 루트에 CLAUDE.md 생성
□ 프로젝트 폴더에서 claude 실행
□ "RULES.md를 읽고 에이전트 팀을 만들어줘" 지시
□ 팀원별 작업 진행 모니터링
□ 작업 완료 후 팀 종료 및 정리
```
