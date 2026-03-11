# AI Blog Automation

네이버 블로그 + 티스토리에 AI 관련 콘텐츠를 자동 생성·발행하는 파이프라인.

## 빠른 시작

```bash
# 1. 의존성 설치
pip install -r requirements.txt

# 2. 환경 변수 설정
cp .env.example .env
# .env 파일에 API 키 입력

# 3. 프로젝트 초기화
python cli.py init

# 4. 글 생성 테스트
python cli.py generate "ChatGPT 새 기능 출시" --content-type news_briefing --keywords "ChatGPT,AI"
```

## 프로젝트 구조

자세한 내용은 [RULES.md](RULES.md) 참조.

## 구현 로드맵

- **Phase 1** (1~3주): 글 작성 & 편집 자동화 (MVP)
- **Phase 2** (4~6주): 승인 게이트 & SEO & 발행
- **Phase 3** (7~9주): 주제 발굴 & 리서치 자동화
- **Phase 4** (10~12주): 성과 분석 & 최적화
