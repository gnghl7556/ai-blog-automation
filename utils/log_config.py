"""
로그 설정 모듈 — structlog + RotatingFileHandler + 오래된 로그 삭제
config/settings.yaml의 logging 섹션 기반으로 로그를 설정합니다.
"""

import logging
import os
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog
import yaml


def setup_logging(
    log_level: str = "INFO",
    log_file: str = "logs/app.log",
    error_log_file: str = "logs/error.log",
    max_size_mb: int = 50,
    backup_count: int = 5,
) -> None:
    """structlog + 표준 logging 설정

    Args:
        log_level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR)
        log_file: 메인 로그 파일 경로
        error_log_file: 에러 전용 로그 파일 경로
        max_size_mb: 로그 파일 최대 크기 (MB)
        backup_count: 보관할 로그 파일 수
    """
    # 로그 디렉토리 생성
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    Path(error_log_file).parent.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, log_level.upper(), logging.INFO)
    max_bytes = max_size_mb * 1024 * 1024

    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 기존 핸들러 제거
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 메인 로그 파일 (RotatingFileHandler)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # 에러 전용 로그 파일
    error_handler = RotatingFileHandler(
        error_log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)

    # structlog 설정
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def cleanup_old_logs(
    log_dir: str = "logs",
    retention_days: int = 30,
) -> int:
    """오래된 로그 파일 삭제

    Args:
        log_dir: 로그 디렉토리 경로
        retention_days: 보존 기간 (일)

    Returns:
        삭제된 파일 수
    """
    log_path = Path(log_dir)
    if not log_path.exists():
        return 0

    cutoff = time.time() - (retention_days * 86400)
    deleted = 0

    for f in log_path.glob("*.log*"):
        if f.is_file() and os.path.getmtime(str(f)) < cutoff:
            f.unlink()
            deleted += 1

    return deleted


def setup_logging_from_config(
    config_path: str = "config/settings.yaml",
) -> None:
    """settings.yaml에서 로그 설정 로드 후 적용"""
    config_file = Path(config_path)
    if not config_file.exists():
        setup_logging()
        return

    with open(config_file, encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}

    log_config = config.get("logging", {})
    setup_logging(
        log_level=log_config.get("level", "INFO"),
        log_file=log_config.get("file", "logs/app.log"),
        error_log_file=log_config.get("error_file", "logs/error.log"),
        max_size_mb=log_config.get("max_size_mb", 50),
        backup_count=log_config.get("backup_count", 5),
    )
