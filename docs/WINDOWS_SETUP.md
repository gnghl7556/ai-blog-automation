# 완전 새 PC 셋업 가이드 (처음부터 끝까지)

> Windows 11 새 PC에서 Claude Code를 처음 설치하고,
> AI Blog Automation 프로젝트를 시작하기까지의 전체 과정입니다.
> 모든 단계를 순서대로 따라하세요.

---

## 전체 순서 요약

```
Step 1: Git for Windows 설치 (Claude Code 필수 의존성)
Step 2: Python 3.12+ 설치
Step 3: Claude Code 설치
Step 4: Claude Code 로그인 및 확인
Step 5: Agent Teams 활성화
Step 6: 프로젝트 파일 준비 (ZIP 압축 해제)
Step 7: Python 가상환경 + 의존성 설치
Step 8: 환경 변수 (.env) 설정
Step 9: 프로젝트 초기화 + API 테스트
Step 10: GitHub 저장소 연결
Step 11: Claude Code로 개발 시작
```

예상 소요 시간: 약 30~45분

---

## Step 1: Git for Windows 설치

Claude Code는 내부적으로 Git Bash를 사용하므로 반드시 필요합니다.

### 1-1. 다운로드

1. https://gitforwindows.org/ 접속
2. "Download" 버튼 클릭
3. 다운로드된 설치 파일 실행

### 1-2. 설치 옵션

설치 과정에서 대부분 기본값(Next)으로 진행하되, 아래 항목만 확인:

- **Adjusting your PATH environment**: "Git from the command line and also from 3rd-party software" 선택 (기본값)
- **Default editor**: 원하는 에디터 선택 (VS Code 추천)
- **Default branch name**: "main" 선택 추천
- 나머지는 모두 기본값 Next

### 1-3. 설치 확인

설치 완료 후 **PowerShell을 새로 열고** 확인:

```powershell
git --version
# 예상 결과: git version 2.47.x.windows.x
```

---

## Step 2: Python 3.12+ 설치

### 2-1. 다운로드

1. https://www.python.org/downloads/ 접속
2. "Download Python 3.12.x" (또는 최신 3.12+) 버튼 클릭
3. 다운로드된 설치 파일 실행

### 2-2. 설치 옵션 (중요!)

설치 첫 화면에서 반드시 체크:

```
☑ Add python.exe to PATH    ← 반드시 체크!
☑ Use admin privileges when installing py
```

그 다음 "Install Now" 클릭

### 2-3. 설치 확인

**PowerShell을 새로 열고** 확인:

```powershell
python --version
# 예상 결과: Python 3.12.x

pip --version
# 예상 결과: pip 24.x.x from ...
```

---

## Step 3: Claude Code 설치

Claude Code는 이제 Windows에서 네이티브로 실행됩니다 (WSL 불필요).

### 3-1. 설치 (PowerShell에서 실행)

```powershell
# 공식 네이티브 설치 (권장, Node.js 불필요)
irm https://claude.ai/install.ps1 | iex
```

설치가 완료되면 **PowerShell을 닫고 새로 열어주세요** (PATH 적용을 위해).

### 3-2. 설치 확인

```powershell
claude --version
# 버전 번호가 표시되면 성공
```

### 3-3. 만약 'claude'를 인식하지 못하면

```powershell
# PATH에 수동 추가
[Environment]::SetEnvironmentVariable(
    "PATH",
    "$env:PATH;$env:USERPROFILE\.local\bin",
    [EnvironmentVariableTarget]::User
)

# 현재 세션에도 적용
$env:PATH = "$env:PATH;$env:USERPROFILE\.local\bin"

# 다시 확인
claude --version
```

### 3-4. 대안: winget으로 설치

```powershell
winget install Anthropic.ClaudeCode
```

---

## Step 4: Claude Code 로그인

### 4-1. 최초 실행 및 인증

```powershell
claude
```

처음 실행하면 브라우저가 열리며 로그인을 요청합니다.

1. 브라우저에서 Claude 계정으로 로그인
2. "Allow Claude Code to access your account" 승인
3. 터미널로 돌아오면 인증 완료

※ Claude Code 사용에는 **Pro, Max, Teams, Enterprise, 또는 Console 계정**이 필요합니다.
  무료 플랜으로는 사용할 수 없습니다.

### 4-2. 로그인 확인

```powershell
# 로그인 후 간단한 테스트
# Claude Code 세션 안에서:
안녕, 잘 동작하는지 테스트야
# Claude가 응답하면 성공!
```

### 4-3. 종료

```
/quit
```

---

## Step 5: Agent Teams 활성화

### 5-1. settings.json 편집

```powershell
# 폴더 생성 (없을 수 있으므로)
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude"

# 메모장으로 편집
notepad "$env:USERPROFILE\.claude\settings.json"
```

메모장에 아래 내용 입력 후 저장:

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

※ 이미 다른 내용이 있으면 "env" 블록 안에 추가만 하세요.

### 5-2. 활성화 확인

```powershell
claude
```

Claude Code 실행 후:

```
agent teams 기능이 활성화되어 있어?
```

"Yes, agent teams are enabled" 응답 확인 후 `/quit`

---

## Step 6: 프로젝트 파일 준비

### 6-1. 작업 폴더 생성

```powershell
mkdir D:\Projects
cd D:\Projects
```

### 6-2. ZIP 파일 압축 해제

Claude.ai에서 다운로드한 `ai-blog-automation.zip`을 `D:\Projects`에 복사한 후:

```powershell
Expand-Archive -Path "ai-blog-automation.zip" -DestinationPath "."
cd ai-blog-automation
```

### 6-3. 파일 확인

```powershell
ls
# RULES.md, CLAUDE.md, cli.py, requirements.txt 등이 보여야 함
```

---

## Step 7: Python 가상환경 + 의존성 설치

### 7-1. 가상환경 생성 + 활성화

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

프롬프트가 `(.venv) PS D:\Projects\ai-blog-automation>`로 변경되면 성공.

※ 실행 정책 오류 시:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 7-2. 의존성 설치

```powershell
pip install -r requirements.txt
```

※ 일부 패키지 에러 시, 핵심만 먼저:
```powershell
pip install anthropic pydantic pyyaml python-dotenv sqlalchemy aiosqlite structlog typer rich httpx jinja2
```

---

## Step 8: 환경 변수 (.env) 설정

### 8-1. .env 파일 생성 + 편집

```powershell
Copy-Item .env.example .env
notepad .env
```

최소 입력값:

```
ANTHROPIC_API_KEY=sk-ant-여기에-실제-키-입력
```

### 8-2. API Key 발급

1. https://console.anthropic.com 접속 → 로그인
2. 왼쪽 메뉴 "API Keys" → "Create Key"
3. 생성된 키 복사 (sk-ant-로 시작) → .env에 붙여넣기

---

## Step 9: 프로젝트 초기화 + API 테스트

```powershell
# 가상환경 활성화 확인 후
python cli.py init
python cli.py generate "ChatGPT 새 기능 출시" --content-type news_briefing --keywords "ChatGPT,AI"
```

"✅ Claude API 연결 성공"이 보이면 준비 완료!

---

## Step 10: GitHub 저장소 연결

### 10-1. Git 초기 설정

```powershell
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

### 10-2. GitHub 레포 생성 + Push

1. https://github.com/new → `ai-blog-automation` (Private) 생성

```powershell
git init
git add .
git commit -m "feat: initial project setup"
git remote add origin https://github.com/YOUR_USERNAME/ai-blog-automation.git
git branch -M main
git push -u origin main
```

---

## Step 11: Claude Code로 개발 시작

### 11-1. 실행

```powershell
cd D:\Projects\ai-blog-automation
.venv\Scripts\Activate.ps1
claude
```

### 11-2. 프로젝트 파악

```
RULES.md와 CLAUDE.md를 읽고 프로젝트 전체 구조를 파악해줘.
config/ 폴더의 YAML 파일들도 확인하고,
현재 구현된 파일과 아직 구현되지 않은 파일을 정리해줘.
```

### 11-3. Agent Teams로 병렬 개발

```
Phase 1 MVP를 구현하자.
에이전트 팀을 만들어줘. 3명의 팀원이 필요해:

팀원 1 - "Writer":
- agents/content_splitter.py 구현
- agents/writing_agent.py 구현

팀원 2 - "Editor":
- agents/editor_agent.py 구현
- utils/text_utils.py 구현

팀원 3 - "Tester":
- tests/ 폴더에 각 모듈 테스트 작성

CLAUDE.md의 파일 소유권 규칙을 따라줘.
```

### 11-4. 팀 모니터링 단축키

| 단축키 | 기능 |
|--------|------|
| Shift + ↑/↓ | 팀원 세션 선택 |
| Ctrl + T | 작업 목록 보기 |
| Enter | 선택한 세션 열기 |
| Escape | 현재 작업 중단 |

### 11-5. 작업 완료 후

```powershell
# 커밋 + Push
git add .
git commit -m "feat: Phase 1 writing pipeline 구현"
git push
```

---

## 문제 해결 (FAQ)

### `claude` 명령어를 인식 못 함
→ PowerShell을 완전히 닫고 새로 열기. 그래도 안 되면 Step 3-3의 PATH 수동 추가.

### Claude Code에서 Git Bash 에러
→ settings.json에 Git Bash 경로 추가:
```json
{
  "gitBashPath": "C:\\Program Files\\Git\\bin\\bash.exe",
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

### Agent Teams가 동작 안 함
→ `claude --version`으로 v2.1.32 이상 확인. 미만이면 `claude update`.

### pip install 에러
→ `python -m pip install --upgrade pip` 후 재시도.

### git push 인증 에러
→ `winget install GitHub.cli` 후 `gh auth login`

---

## 전체 설치 확인 체크리스트

```
□ git --version             → 버전 표시
□ python --version          → 3.12+ 표시
□ claude --version          → 버전 표시
□ claude 실행 → 로그인 완료
□ settings.json에 Agent Teams 설정 완료
□ ZIP 압축 해제 완료
□ 가상환경 + 의존성 설치 완료
□ .env에 API Key 입력 완료
□ python cli.py init 성공
□ python cli.py generate 테스트 성공
□ GitHub 레포 + git push 완료
□ Claude Code에서 프로젝트 열기 성공
□ Agent Teams 활성화 확인
```
