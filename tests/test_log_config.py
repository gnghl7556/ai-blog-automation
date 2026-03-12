"""로그 설정 모듈 테스트"""

import logging
from pathlib import Path

import pytest

from utils.log_config import (
    setup_logging,
    setup_logging_from_config,
    cleanup_old_logs,
)


class TestSetupLogging:
    def test_default_setup(self, tmp_path):
        """기본 로그 설정"""
        log_file = str(tmp_path / "app.log")
        error_file = str(tmp_path / "error.log")

        setup_logging(
            log_file=log_file,
            error_log_file=error_file,
        )

        root = logging.getLogger()
        # 콘솔 + 파일 + 에러 파일 = 3개 핸들러
        assert len(root.handlers) >= 3
        assert root.level == logging.INFO

    def test_debug_level(self, tmp_path):
        """DEBUG 레벨 설정"""
        log_file = str(tmp_path / "debug.log")
        error_file = str(tmp_path / "error.log")

        setup_logging(
            log_level="DEBUG",
            log_file=log_file,
            error_log_file=error_file,
        )

        root = logging.getLogger()
        assert root.level == logging.DEBUG

    def test_log_file_created(self, tmp_path):
        """로그 파일 디렉토리 자동 생성"""
        log_dir = tmp_path / "subdir"
        log_file = str(log_dir / "app.log")
        error_file = str(log_dir / "error.log")

        setup_logging(
            log_file=log_file,
            error_log_file=error_file,
        )

        assert log_dir.exists()

    def test_error_handler_level(self, tmp_path):
        """에러 핸들러는 ERROR 레벨 이상만"""
        log_file = str(tmp_path / "app.log")
        error_file = str(tmp_path / "error.log")

        setup_logging(
            log_file=log_file,
            error_log_file=error_file,
        )

        root = logging.getLogger()
        error_handlers = [
            h for h in root.handlers
            if h.level == logging.ERROR
        ]
        assert len(error_handlers) >= 1


class TestSetupLoggingFromConfig:
    def test_missing_config(self, tmp_path):
        """설정 파일 없으면 기본값 사용"""
        setup_logging_from_config(
            config_path=str(tmp_path / "nonexistent.yaml")
        )
        root = logging.getLogger()
        assert root.level == logging.INFO

    def test_with_config(self, tmp_path):
        """설정 파일에서 로드"""
        config_file = tmp_path / "settings.yaml"
        log_file = str(tmp_path / "test.log")
        error_file = str(tmp_path / "test_error.log")
        config_file.write_text(
            f"logging:\n"
            f"  level: WARNING\n"
            f"  file: {log_file}\n"
            f"  error_file: {error_file}\n"
            f"  max_size_mb: 10\n"
            f"  backup_count: 3\n"
        )

        setup_logging_from_config(str(config_file))
        root = logging.getLogger()
        assert root.level == logging.WARNING


class TestCleanupOldLogs:
    def test_deletes_old_files(self, tmp_path):
        """30일 이상 된 로그 파일 삭제"""
        import os
        import time

        # 오래된 로그 파일 생성
        old_file = tmp_path / "old.log"
        old_file.write_text("old log")
        # 40일 전으로 mtime 설정
        old_time = time.time() - (40 * 86400)
        os.utime(str(old_file), (old_time, old_time))

        # 최근 로그 파일 생성
        new_file = tmp_path / "new.log"
        new_file.write_text("new log")

        deleted = cleanup_old_logs(
            log_dir=str(tmp_path), retention_days=30
        )
        assert deleted == 1
        assert not old_file.exists()
        assert new_file.exists()

    def test_no_files_to_delete(self, tmp_path):
        """삭제할 파일 없음"""
        new_file = tmp_path / "recent.log"
        new_file.write_text("recent log")

        deleted = cleanup_old_logs(
            log_dir=str(tmp_path), retention_days=30
        )
        assert deleted == 0

    def test_nonexistent_dir(self, tmp_path):
        """존재하지 않는 디렉토리"""
        deleted = cleanup_old_logs(
            log_dir=str(tmp_path / "nonexistent"),
            retention_days=30,
        )
        assert deleted == 0
