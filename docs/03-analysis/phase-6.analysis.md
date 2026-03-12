# Phase 6 (운영 안정화 + 인프라) Gap Analysis Report

> **Analysis Type**: Gap Analysis (Design vs Implementation)
>
> **Project**: AI Blog Automation
> **Analyst**: Claude Code (gap-detector)
> **Date**: 2026-03-13
> **Plan Doc**: [roadmap-phase6-plus.plan.md](../01-plan/features/roadmap-phase6-plus.plan.md)

---

## 1. Analysis Overview

### 1.1 분석 목적

Phase 6 계획 문서(roadmap-phase6-plus.plan.md)에 정의된 4개 하위 항목(6-1 ~ 6-4)의 구현 완성도를 점검하고, 미구현 항목 및 차이점을 식별한다.

### 1.2 분석 범위

- **계획 문서**: `docs/01-plan/features/roadmap-phase6-plus.plan.md` (Phase 6 섹션)
- **구현 파일**: `utils/`, `scripts/`, `config/`, `alembic/`, `cli.py`, `cli_auto.py`, `docker-compose.prod.yml`, `Dockerfile`, `tests/`
- **분석일**: 2026-03-13

---

## 2. Gap Analysis (계획 vs 구현)

### 2.1 Sub-item 6-1: 배포 인프라

| 계획 항목 | 구현 파일 | 상태 | 비고 |
|-----------|-----------|:----:|------|
| systemd 서비스 파일 (`ai-blog-automation.service`) | `scripts/ai-blog-automation.service` | ✅ | 구현 완료 |
| - 서버 재부팅 시 자동 시작 (`WantedBy=multi-user.target`) | service 파일 L26 | ✅ | `[Install]` 섹션에 포함 |
| - 비정상 종료 시 자동 재시작 (`Restart=on-failure`) | service 파일 L12 | ✅ | `RestartSec=30` 포함 |
| Docker Compose 운영 프로필 (`docker-compose.prod.yml`) | `docker-compose.prod.yml` | ✅ | 구현 완료 |
| - app 컨테이너 | scheduler + bot 2개 서비스 | ✅ | 계획보다 세분화 (개선) |
| - healthcheck 설정 | scheduler 서비스에 healthcheck 블록 | ✅ | interval=5m, retries=3 |
| - Redis 컨테이너 | - | ❌ 미구현 | 계획에 Redis 포함, 구현에 없음 |
| - (선택) PostgreSQL 컨테이너 | - | ⚠️ 미구현 | 계획에서 "선택"으로 표기 |
| - 볼륨 마운트: `data/`, `logs/` | docker-compose.prod.yml L21-23 | ✅ | `config/`도 추가 마운트 (개선) |
| VPS 배포 스크립트 (`scripts/deploy.sh`) | `scripts/deploy.sh` | ✅ | 구현 완료 |
| - git pull | deploy.sh L27-28 | ✅ | `git pull origin main` |
| - docker compose up --build | deploy.sh L39-43 | ✅ | build + up -d |
| - health check | deploy.sh L46-60 | ✅ | 최대 60초 대기, 12회 재시도 |

**추가 구현 (계획에 없음)**:

| 항목 | 구현 파일 | 비고 |
|------|-----------|------|
| Telegram Bot용 별도 systemd 서비스 | `scripts/ai-blog-bot.service` | scheduler와 분리 운영, 의존성 설정 포함 |
| systemd 보안 강화 설정 | 두 service 파일 | `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`, `PrivateTmp` |
| Dockerfile | `Dockerfile` | Python 3.12-slim 기반 컨테이너 이미지 |
| DEPLOY.md 문서 | `docs/DEPLOY.md` | VPS 배포 전체 가이드 |

**6-1 일치율: 90%** (Redis 컨테이너 미포함 외 모두 구현)

---

### 2.2 Sub-item 6-2: 헬스체크 + 자동 복구

| 계획 항목 | 구현 파일 | 상태 | 비고 |
|-----------|-----------|:----:|------|
| `utils/health_checker.py` 작성 | `utils/health_checker.py` | ✅ | 186줄, 잘 구조화됨 |
| - Claude API 응답 여부 확인 | `_check_claude_api_key()` | ⚠️ 부분 | API 키 존재/형식만 확인. 실제 API 호출(응답 여부)은 미확인 |
| - DB 연결 상태 확인 | `_check_db()` | ✅ | `SELECT 1` 쿼리 실행, 지연시간 측정 |
| - Telegram Bot 연결 상태 확인 | `_check_telegram()` | ✅ | `getMe` API 호출, 지연시간 측정 |
| 시작 시 헬스체크 실행 | - | ❌ 미구현 | 스케줄러/봇 시작 시 자동 헬스체크 로직 없음 |
| 실패 시 텔레그램 알림 | - | ❌ 미구현 | 헬스체크 실패 시 텔레그램 알림 연동 없음 |
| 실패 시 프로세스 종료 | - | ❌ 미구현 | 시작 시 자동 종료 로직 없음 (CLI에서 수동 exit만) |
| `cli.py health` 커맨드 | `cli_auto.py` health 함수 | ✅ | Rich 테이블 출력, 실패 시 exit(1) |

**추가 구현 (계획에 없음)**:

| 항목 | 구현 파일 | 비고 |
|------|-----------|------|
| 필수 디렉토리 존재 확인 | `_check_directories()` | data, logs, config 디렉토리 점검 |
| CheckResult / HealthReport 데이터 모델 | health_checker.py L16-40 | 구조화된 결과 반환 |
| 헬스체크 테스트 | `tests/test_health_checker.py` | 198줄, 충실한 테스트 커버리지 |

**6-2 일치율: 60%** (핵심 체커는 구현되었으나, "시작 시 자동 실행 + 알림 + 종료" 통합 로직 미구현)

---

### 2.3 Sub-item 6-3: 로그 관리

| 계획 항목 | 구현 파일 | 상태 | 비고 |
|-----------|-----------|:----:|------|
| 로그 로테이션 설정 (Python RotatingFileHandler) | `utils/log_config.py` | ✅ | RotatingFileHandler, maxBytes + backupCount |
| 에러 로그 별도 파일 분리 (`logs/error.log`) | `utils/log_config.py` L68-76 | ✅ | ERROR 레벨 이상만 별도 파일 |
| config/settings.yaml에 logging 설정 | `config/settings.yaml` L61-67 | ✅ | level, file, error_file, max_size_mb, backup_count |
| 30일 이상 로그 자동 삭제 | - | ❌ 미구현 | 로그 로테이션은 있으나 오래된 로그 자동 삭제 기능 없음 |

**추가 구현 (계획에 없음)**:

| 항목 | 구현 파일 | 비고 |
|------|-----------|------|
| structlog 통합 설정 | `utils/log_config.py` L79-92 | JSON 포맷, 타임스탬프, 로그레벨 |
| settings.yaml 기반 설정 로드 | `setup_logging_from_config()` | YAML에서 로그 설정 자동 로드 |
| 로그 설정 테스트 | `tests/test_log_config.py` | 98줄, 핸들러/레벨 검증 |

**6-3 일치율: 75%** (로테이션 + 에러 분리 완료, 30일 자동 삭제만 미구현)

---

### 2.4 Sub-item 6-4: DB 마이그레이션 전략

| 계획 항목 | 구현 파일 | 상태 | 비고 |
|-----------|-----------|:----:|------|
| Alembic 도입 | `alembic.ini`, `alembic/env.py` | ✅ | 완전한 Alembic 설정 |
| - 초기 마이그레이션 | `alembic/versions/19efb82ffbc3_initial_schema.py` | ✅ | raw_topics 테이블 생성 |
| - DATABASE_URL 환경변수 지원 | `alembic/env.py` L16-18 | ✅ | .env에서 오버라이드 가능 |
| - render_as_batch (SQLite 호환) | `alembic/env.py` L37, L56 | ✅ | SQLite ALTER TABLE 제약 대응 |
| SQLite -> PostgreSQL 전환 가이드 문서 | - | ❌ 미구현 | 별도 전환 가이드 문서 없음 |
| `cli.py db migrate` 커맨드 | `cli_auto.py` db_migrate 함수 | ✅ | Alembic autogenerate 래핑 |
| `cli.py db upgrade` 커맨드 (계획: `db migrate`) | `cli_auto.py` db_upgrade 함수 | ✅ | 커맨드명이 세분화됨 (개선) |

**추가 구현 (계획에 없음)**:

| 항목 | 구현 파일 | 비고 |
|------|-----------|------|
| db-migrate / db-upgrade 분리 | cli_auto.py | 생성과 적용을 분리하여 안전성 향상 |

**6-4 일치율: 80%** (Alembic + CLI 완료, PostgreSQL 전환 가이드 문서만 미구현)

---

## 3. Overall Score Summary

| 카테고리 | 점수 | 상태 |
|----------|:----:|:----:|
| 6-1. 배포 인프라 | 90% | ✅ |
| 6-2. 헬스체크 + 자동 복구 | 60% | ⚠️ |
| 6-3. 로그 관리 | 75% | ⚠️ |
| 6-4. DB 마이그레이션 전략 | 80% | ✅ |
| **전체 Phase 6** | **76%** | **⚠️** |

```
+---------------------------------------------+
|  Overall Match Rate: 76%                     |
+---------------------------------------------+
|  ✅ 완전 구현:        16 items (64%)          |
|  ⚠️ 부분 구현:         3 items (12%)          |
|  ❌ 미구현:            6 items (24%)          |
+---------------------------------------------+
```

---

## 4. Differences Found

### 4.1 Missing Features (계획 O, 구현 X)

| 항목 | 계획 위치 | 설명 | 영향도 |
|------|-----------|------|--------|
| 시작 시 헬스체크 자동 실행 | 6-2 (L66) | 스케줄러/봇 시작 시 헬스체크 -> 실패 시 종료 | High |
| 헬스체크 실패 시 텔레그램 알림 | 6-2 (L66) | 헬스체크 실패를 텔레그램으로 알림 | High |
| 30일 이상 로그 자동 삭제 | 6-3 (L72) | 오래된 로그 파일 자동 정리 | Medium |
| SQLite -> PostgreSQL 전환 가이드 | 6-4 (L76) | DB 전환 절차 문서화 | Low |
| Redis 컨테이너 (docker-compose) | 6-1 (L56) | docker-compose.prod.yml에 Redis 서비스 미포함 | Low |
| Claude API 실제 응답 테스트 | 6-2 (L63) | API 키 형식만 확인, 실제 호출 미수행 | Medium |

### 4.2 Added Features (계획 X, 구현 O)

| 항목 | 구현 위치 | 설명 |
|------|-----------|------|
| Telegram Bot 전용 systemd 서비스 | `scripts/ai-blog-bot.service` | scheduler와 bot을 분리 운영 |
| systemd 보안 강화 설정 | 두 service 파일 | NoNewPrivileges, ProtectSystem 등 |
| Dockerfile | `Dockerfile` | 컨테이너 이미지 정의 |
| 배포 가이드 문서 | `docs/DEPLOY.md` | VPS 배포 전체 프로세스 문서화 |
| 디렉토리 존재 헬스체크 | `health_checker.py` | data, logs, config 디렉토리 점검 |
| structlog 통합 | `log_config.py` | JSON 구조화 로깅 |
| db-migrate / db-upgrade 커맨드 분리 | `cli_auto.py` | 마이그레이션 생성과 적용을 분리 |
| 테스트 파일 | tests/ | health_checker, log_config 테스트 |

### 4.3 Changed Features (계획 != 구현)

| 항목 | 계획 | 구현 | 영향도 |
|------|------|------|--------|
| Claude API 체크 방식 | API 응답 여부 확인 | API 키 존재/형식만 확인 | Medium |
| Docker 서비스 구성 | 단일 app 서비스 | scheduler + bot 2개 분리 | Low (개선) |
| CLI 커맨드명 | `cli.py db migrate` | `cli.py db-migrate` + `cli.py db-upgrade` | Low (개선) |
| docker-compose 서비스 | app + Redis + (PostgreSQL) | scheduler + bot (DB/Redis 없음) | Medium |

---

## 5. Test Coverage

| 모듈 | 테스트 파일 | 테스트 수 | 상태 |
|------|------------|:---------:|:----:|
| health_checker.py | tests/test_health_checker.py | 11개 | ✅ 충실 |
| log_config.py | tests/test_log_config.py | 5개 | ✅ 충실 |
| deploy.sh | - | 0개 | ⚠️ 셸 스크립트 |
| systemd services | - | 0개 | ⚠️ 인프라 설정 |
| docker-compose.prod.yml | - | 0개 | ⚠️ 인프라 설정 |
| Alembic 마이그레이션 | - | 0개 | ⚠️ 스키마 검증 없음 |

---

## 6. Code Quality

### 6.1 코드 품질 양호 항목

- `health_checker.py`: dataclass 기반 구조화, async/await 활용, 적절한 에러 핸들링
- `log_config.py`: 설정 기반 초기화, RotatingFileHandler 올바른 사용
- `deploy.sh`: `set -euo pipefail` 사용, 단계별 출력, 에러 처리
- systemd service: 보안 강화 옵션 적용 (ProtectSystem, NoNewPrivileges 등)

### 6.2 개선 필요 항목

| 파일 | 위치 | 이슈 | 심각도 |
|------|------|------|--------|
| health_checker.py | L80-82 | `__import__` 사용 (일반적이지 않은 패턴) | Low |
| cli_auto.py | L410-440 | subprocess로 alembic 호출 (Python API 직접 사용 가능) | Low |

---

## 7. Recommended Actions

### 7.1 즉시 조치 (High Priority)

| 우선순위 | 항목 | 구현 방법 |
|:--------:|------|-----------|
| 1 | 스케줄러/봇 시작 시 헬스체크 통합 | `scheduler/runner.py`와 `approval/bot_runner.py`의 `start()` 메서드에 `HealthChecker.check_all()` 호출 추가. 실패 시 텔레그램 알림 후 sys.exit(1) |
| 2 | 헬스체크 실패 시 텔레그램 알림 | `health_checker.py`에 `notify_on_failure()` 메서드 추가, `TelegramNotifier` 연동 |
| 3 | Claude API 실제 응답 확인 | `_check_claude_api_key()` -> `_check_claude_api()`로 변경, 간단한 API 호출(messages.create)로 응답 확인 |

### 7.2 단기 조치 (Medium Priority, 1주 내)

| 우선순위 | 항목 | 구현 방법 |
|:--------:|------|-----------|
| 4 | 30일 이상 로그 자동 삭제 | `utils/log_config.py`에 `cleanup_old_logs(days=30)` 함수 추가. 스케줄러에 일일 작업으로 등록 |
| 5 | docker-compose.prod.yml에 Redis 추가 | Redis 서비스 블록 추가 (현재 Redis 의존성이 없으면 생략 가능, 사용 여부 확인 필요) |

### 7.3 장기 조치 (Low Priority, 백로그)

| 항목 | 구현 방법 |
|------|-----------|
| SQLite -> PostgreSQL 전환 가이드 | `docs/MIGRATION-GUIDE.md` 작성 (환경변수 변경, Alembic 재실행, 데이터 이관 절차) |
| Alembic 마이그레이션 테스트 | `tests/test_alembic.py` 작성 (upgrade/downgrade 왕복 검증) |

---

## 8. 계획 문서 업데이트 필요 사항

다음 항목은 구현이 계획보다 개선되었으므로, 계획 문서에 반영 권장:

- [ ] systemd 서비스를 scheduler + bot 2개로 분리 운영한다는 내용 추가
- [ ] 보안 강화 설정 (NoNewPrivileges, ProtectSystem 등) 명시
- [ ] `db-migrate` / `db-upgrade` 커맨드 분리 반영
- [ ] Dockerfile 존재 명시
- [ ] DEPLOY.md 배포 가이드 문서 참조 추가
- [ ] Redis 컨테이너 필요 여부 재확인 (현재 코드에서 Redis 미사용 시 계획에서 제거)

---

## 9. Next Steps

- [ ] High Priority 3개 항목 구현 (시작 시 헬스체크 + 알림 + API 실제 확인)
- [ ] 30일 로그 자동 삭제 구현
- [ ] 구현 완료 후 재분석 실행하여 90% 이상 도달 확인
- [ ] Phase 6 완료 보고서 작성 (`phase-6.report.md`)

---

## Version History

| Version | Date | Changes | Author |
|---------|------|---------|--------|
| 1.0 | 2026-03-13 | 초기 Gap Analysis | Claude Code (gap-detector) |
