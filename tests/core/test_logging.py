import os
import tempfile
from dataclasses import dataclass


# Minimal LogConfig in case Task 3 isn't done yet
try:
    from astock.core.config import LogConfig
except ImportError:
    @dataclass
    class LogConfig:
        level: str = "INFO"
        file: str = "logs/astock.log"


from astock.core.logging import setup_logging


class TestLogging:
    def test_setup_logging_creates_log_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "test.log")
            cfg = LogConfig(level="DEBUG", file=log_path)
            setup_logging(cfg)

            import logging
            logger = logging.getLogger("astock")
            logger.debug("test message")

            assert os.path.exists(log_path)
            with open(log_path) as f:
                content = f.read()
            assert "test message" in content

    def test_setup_logging_returns_logger(self):
        cfg = LogConfig(level="INFO", file="/tmp/astock_test.log")
        logger = setup_logging(cfg)
        assert logger.name == "astock"
