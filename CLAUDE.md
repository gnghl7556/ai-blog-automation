# AI Blog Automation — Claude Code 지침

## 프로젝트 이해
- RULES.md를 먼저 읽고 전체 아키텍처를 파악하세요
- config/ 폴더의 YAML 파일들이 모든 설정의 근원입니다
- agents/data_models.py의 Pydantic 모델로 에이전트 간 데이터를 주고받습니다

## 코딩 규칙
- Python 3.12+, 비동기 (async/await), 타입 힌트 필수
- 모든 에이전트는 agents/base_agent.py의 BaseAgent를 상속합니다
- Claude API 호출은 반드시 self.claude_call()을 사용합니다 (재시도, 비용 추적 내장)
- Google 스타일 Docstring 필수
- 하드코딩 금지, 설정은 config/*.yaml에서 로드
- 한 파일 최대 300줄 (초과 시 분리)

## Agent Teams 규칙
- 각 팀원은 할당된 파일만 수정합니다
- 공통 파일 수정이 필요하면 팀 리더에게 요청합니다
- 인터페이스 변경 시 다른 팀원에게 알립니다
- 구현 완료 시 팀 리더에게 보고합니다

## 파일 소유권 (Phase 1)
- Writer 팀원: agents/content_splitter.py, agents/writing_agent.py
- Editor 팀원: agents/editor_agent.py, utils/text_utils.py
- Tester 팀원: tests/ 폴더 전체
- 공통 (읽기 전용): agents/base_agent.py, agents/data_models.py, database/models.py, utils/claude_client.py, utils/cost_tracker.py

## 핵심 아키텍처
- 네이버: "이해"시키기 (설민석 강연 스타일, ~거든요 체, 전문용어 배제)
- 티스토리: "학습"시키기 (전문 리뷰어 스타일, ~입니다 체, 용어+간단설명)
- 부분 병렬: 네이버+티스토리 작성/편집/SEO 동시 실행
- 에러: 자동 재시도 3회 → 텔레그램 알림

## 테스트
- pytest + pytest-asyncio 사용
- 모든 에이전트는 독립적으로 테스트 가능해야 합니다
