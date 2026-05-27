import os
import tempfile
import pytest
from astock.core.config import Config, TushareConfig, StorageConfig, SyncConfig, LogConfig
from astock.core.exceptions import ConfigError


SAMPLE_YAML = """
tushare:
  token: "${TUSHARE_TOKEN}"

storage:
  data_dir: "data/"
  db_path: "data/astock.duckdb"

sync:
  batch_size: 5000
  retry: 3
  retry_delay: 5

log:
  level: "INFO"
  file: "logs/astock.log"
"""


class TestConfig:
    def test_load_from_yaml_resolves_env_var(self):
        os.environ["TUSHARE_TOKEN"] = "test-token-123"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(SAMPLE_YAML)
            path = f.name
        try:
            cfg = Config.from_yaml(path)
            assert cfg.tushare.token == "test-token-123"
        finally:
            os.unlink(path)

    def test_load_from_yaml_missing_env_var_raises(self):
        os.environ.pop("TUSHARE_TOKEN", None)
        yaml_no_env = SAMPLE_YAML.replace("${TUSHARE_TOKEN}", "")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_no_env)
            path = f.name
        try:
            with pytest.raises(ConfigError, match="token"):
                Config.from_yaml(path)
        finally:
            os.unlink(path)

    def test_default_values(self):
        cfg = Config(
            tushare=TushareConfig(token="x"),
            storage=StorageConfig(),
            sync=SyncConfig(),
            log=LogConfig(),
        )
        assert cfg.storage.data_dir == "data/"
        assert cfg.sync.retry == 3
        assert cfg.log.level == "INFO"

    def test_config_file_not_found(self):
        with pytest.raises(ConfigError, match="not found"):
            Config.from_yaml("/nonexistent/config.yaml")
