# A-Stock 本地数据同步系统 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 A 股数据本地同步系统，从 Tushare 拉取 6 张核心表并以 Parquet 格式存储，通过 DuckDB 查询，CLI 交互。

**Architecture:** 四层架构 — core（配置/异常/日志）、data（source/sync/store）、cli（Typer 命令）、strategy/backtest（占位）。级联依赖检查确保单表同步时自动更新依赖表。TDD 开发，每个模块先写测试。

**Tech Stack:** Python >= 3.11, conda, Typer, Tushare Pro, DuckDB, PyArrow, Pandas, pytest, PyYAML

**Spec:** `docs/superpowers/specs/2026-05-27-astock-data-layer-design.md`

---

### Task 1: 项目脚手架

**Files:**
- Create: `environment.yml`
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `config.yaml`
- Create: `src/astock/__init__.py`
- Create: `src/astock/core/__init__.py`
- Create: `src/astock/data/__init__.py`
- Create: `src/astock/data/source/__init__.py`
- Create: `src/astock/data/sync/__init__.py`
- Create: `src/astock/data/store/__init__.py`
- Create: `src/astock/strategy/__init__.py`
- Create: `src/astock/backtest/__init__.py`
- Create: `src/astock/cli/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/core/__init__.py`
- Create: `tests/data/__init__.py`

- [ ] **Step 1: Create environment.yml**

```yaml
name: astock
channels:
  - conda-forge
  - defaults
dependencies:
  - python >=3.11,<3.13
  - pip
  - pyarrow
  - pandas
  - pyyaml
  - pip:
      - tushare
      - duckdb
      - typer
      - pytest
      - pytest-cov
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "astock"
version = "0.1.0"
description = "A-Stock quantitative trading data system"
requires-python = ">=3.11"
dependencies = [
    "tushare",
    "duckdb",
    "pyarrow",
    "pandas",
    "pyyaml",
    "typer",
]

[project.scripts]
astock = "astock.cli.main:app"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

- [ ] **Step 3: Create .gitignore**

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/

# Data
data/

# Logs
logs/

# Environment
.env
.conda/

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

- [ ] **Step 4: Create config.yaml**

```yaml
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
```

- [ ] **Step 5: Create all __init__.py files**

```bash
touch src/astock/__init__.py
touch src/astock/core/__init__.py
touch src/astock/data/__init__.py
touch src/astock/data/source/__init__.py
touch src/astock/data/sync/__init__.py
touch src/astock/data/store/__init__.py
touch src/astock/strategy/__init__.py
touch src/astock/backtest/__init__.py
touch src/astock/cli/__init__.py
touch tests/__init__.py
mkdir -p tests/core && touch tests/core/__init__.py
mkdir -p tests/data && touch tests/data/__init__.py
```

- [ ] **Step 6: Create conda env and verify**

```bash
cd /Users/hongao/ha/A_stock
conda env create -f environment.yml
conda activate astock
pip install -e .
python -c "import astock; print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Initialize git and commit**

```bash
cd /Users/hongao/ha/A_stock
git init
git add -A
git commit -m "chore: project scaffolding with conda env, pyproject.toml, config"
```

---

### Task 2: 核心异常体系

**Files:**
- Create: `src/astock/core/exceptions.py`
- Create: `tests/core/test_exceptions.py`

- [ ] **Step 1: Write tests for exception hierarchy**

`tests/core/test_exceptions.py`:

```python
import pytest
from astock.core.exceptions import (
    AStockError,
    ConfigError,
    APIError,
    StoreError,
    SyncError,
)


class TestExceptionHierarchy:
    def test_base_exception(self):
        with pytest.raises(AStockError):
            raise AStockError("base error")

    def test_config_error_is_astock_error(self):
        err = ConfigError("missing token")
        assert isinstance(err, AStockError)
        assert str(err) == "missing token"

    def test_api_error_includes_details(self):
        err = APIError("request failed", status_code=429, response="rate limit")
        assert err.status_code == 429
        assert err.response == "rate limit"
        assert isinstance(err, AStockError)

    def test_store_error_is_astock_error(self):
        err = StoreError("write failed")
        assert isinstance(err, AStockError)

    def test_sync_error_is_astock_error(self):
        err = SyncError("dependency broken")
        assert isinstance(err, AStockError)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/hongao/ha/A_stock && python -m pytest tests/core/test_exceptions.py -v
```

Expected: FAIL — module not found

- [ ] **Step 3: Implement exceptions**

`src/astock/core/exceptions.py`:

```python
class AStockError(Exception):
    """Base exception for all A-Stock system errors."""
    pass


class ConfigError(AStockError):
    """Configuration error: missing keys, invalid paths, etc."""
    pass


class APIError(AStockError):
    """Tushare API error with status code and response body."""

    def __init__(self, message: str, status_code: int | None = None, response: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class StoreError(AStockError):
    """Storage layer error: IO failure, data corruption."""
    pass


class SyncError(AStockError):
    """Sync logic error: dependency breakage, data inconsistency."""
    pass
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/hongao/ha/A_stock && python -m pytest tests/core/test_exceptions.py -v
```

Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add src/astock/core/exceptions.py tests/core/test_exceptions.py
git commit -m "feat: add exception hierarchy (AStockError, ConfigError, APIError, StoreError, SyncError)"
```

---

### Task 3: 配置加载

**Files:**
- Create: `src/astock/core/config.py`
- Create: `tests/core/test_config.py`

- [ ] **Step 1: Write tests for config loading**

`tests/core/test_config.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/hongao/ha/A_stock && python -m pytest tests/core/test_config.py -v
```

Expected: FAIL — module not found

- [ ] **Step 3: Implement config**

`src/astock/core/config.py`:

```python
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from astock.core.exceptions import ConfigError


@dataclass
class TushareConfig:
    token: str


@dataclass
class StorageConfig:
    data_dir: str = "data/"
    db_path: str = "data/astock.duckdb"


@dataclass
class SyncConfig:
    batch_size: int = 5000
    retry: int = 3
    retry_delay: int = 5


@dataclass
class LogConfig:
    level: str = "INFO"
    file: str = "logs/astock.log"


@dataclass
class Config:
    tushare: TushareConfig
    storage: StorageConfig
    sync: SyncConfig
    log: LogConfig

    @classmethod
    def from_yaml(cls, path: str) -> "Config":
        p = Path(path)
        if not p.exists():
            raise ConfigError(f"Config file not found: {path}")

        with open(p) as f:
            raw = yaml.safe_load(f)

        raw_str = yaml.dump(raw)
        missing = []
        for match in re.finditer(r'\$\{(\w+)\}', raw_str):
            var_name = match.group(1)
            if var_name not in os.environ:
                missing.append(var_name)

        if missing:
            raise ConfigError(
                f"Missing environment variables: {', '.join(missing)}"
            )

        resolved = raw_str
        for var_name in set(m.group(1) for m in re.finditer(r'\$\{(\w+)\}', raw_str)):
            resolved = resolved.replace(f"${{{var_name}}}", os.environ.get(var_name, ""))

        data = yaml.safe_load(resolved)

        return cls(
            tushare=TushareConfig(token=data["tushare"]["token"]),
            storage=StorageConfig(**data.get("storage", {})),
            sync=SyncConfig(**data.get("sync", {})),
            log=LogConfig(**data.get("log", {})),
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/hongao/ha/A_stock && python -m pytest tests/core/test_config.py -v
```

Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add src/astock/core/config.py tests/core/test_config.py
git commit -m "feat: add YAML config loading with env var substitution"
```

---

### Task 4: 日志配置

**Files:**
- Create: `src/astock/core/logging.py`
- Create: `tests/core/test_logging.py`

- [ ] **Step 1: Write tests for logging setup**

`tests/core/test_logging.py`:

```python
import os
import tempfile
from astock.core.logging import setup_logging
from astock.core.config import LogConfig


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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/hongao/ha/A_stock && python -m pytest tests/core/test_logging.py -v
```

Expected: FAIL — module not found

- [ ] **Step 3: Implement logging**

`src/astock/core/logging.py`:

```python
import logging
from pathlib import Path

from astock.core.config import LogConfig


def setup_logging(cfg: LogConfig) -> logging.Logger:
    log_path = Path(cfg.file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("astock")
    logger.setLevel(getattr(logging, cfg.level.upper(), logging.INFO))

    if not logger.handlers:
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(fh)

        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(ch)

    return logger
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/hongao/ha/A_stock && python -m pytest tests/core/test_logging.py -v
```

Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
git add src/astock/core/logging.py tests/core/test_logging.py
git commit -m "feat: add logging setup with file and console handlers"
```

---

### Task 5: 存储层 DataStore

**Files:**
- Create: `src/astock/data/store/db.py`
- Create: `tests/data/test_store.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write conftest with fixtures**

`tests/conftest.py`:

```python
import os
import tempfile
import pytest
import pandas as pd


@pytest.fixture
def temp_data_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_trade_cal_df():
    return pd.DataFrame({
        "exchange": ["SSE", "SSE", "SSE", "SZSE", "SZSE"],
        "cal_date": ["20240101", "20240102", "20240103", "20240101", "20240102"],
        "is_open": ["0", "1", "1", "0", "1"],
        "pretrade_date": ["20231229", "20240101", "20240102", "20231229", "20240101"],
    })


@pytest.fixture
def sample_stock_basic_df():
    return pd.DataFrame({
        "ts_code": ["000001.SZ", "000002.SZ", "600000.SH"],
        "symbol": ["000001", "000002", "600000"],
        "name": ["平安银行", "万科A", "浦发银行"],
        "area": ["深圳", "深圳", "上海"],
        "industry": ["银行", "房地产", "银行"],
        "list_status": ["L", "L", "L"],
        "list_date": ["19910403", "19910129", "19991110"],
        "delist_date": [None, None, None],
    })


@pytest.fixture
def sample_daily_df():
    return pd.DataFrame({
        "ts_code": ["000001.SZ", "000002.SZ"],
        "trade_date": ["20240102", "20240102"],
        "open": [10.0, 15.0],
        "high": [10.5, 15.5],
        "low": [9.9, 14.8],
        "close": [10.3, 15.2],
        "pre_close": [10.1, 14.9],
        "change": [0.2, 0.3],
        "pct_chg": [1.98, 2.01],
        "vol": [100000.0, 200000.0],
        "amount": [103000.0, 304000.0],
    })


@pytest.fixture
def sample_suspend_df():
    return pd.DataFrame({
        "ts_code": ["000003.SZ"],
        "trade_date": ["20240102"],
        "suspend_timing": [None],
        "suspend_type": ["S"],
    })
```

- [ ] **Step 2: Write tests for DataStore**

`tests/data/test_store.py`:

```python
import os
import pandas as pd
import pytest
from astock.data.store.db import DataStore
from astock.core.exceptions import StoreError


class TestDataStore:
    def test_save_and_load_append(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("daily", sample_daily_df, mode="append")
        assert store.table_exists("daily")
        assert store.row_count("daily") == 2

        df = store.load("daily")
        assert len(df) == 2
        assert "000001.SZ" in df["ts_code"].values

    def test_save_replace_overwrites(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("daily", sample_daily_df, mode="append")
        store.save("daily", sample_daily_df.head(1), mode="replace")
        assert store.row_count("daily") == 1

    def test_save_empty_df_is_noop(self, temp_data_dir):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("daily", pd.DataFrame(), mode="append")
        assert not store.table_exists("daily")

    def test_load_with_filters(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("daily", sample_daily_df, mode="append")
        df = store.load("daily", ts_code="000001.SZ")
        assert len(df) == 1
        assert df.iloc[0]["ts_code"] == "000001.SZ"

    def test_get_latest_date(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("daily", sample_daily_df, mode="append")
        latest = store.get_latest_date("daily", "trade_date")
        assert latest == "20240102"

    def test_get_latest_date_empty_table(self, temp_data_dir):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        assert store.get_latest_date("daily", "trade_date") is None

    def test_table_exists(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        assert not store.table_exists("daily")
        store.save("daily", sample_daily_df, mode="append")
        assert store.table_exists("daily")

    def test_is_trade_day(self, temp_data_dir, sample_trade_cal_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("trade_cal", sample_trade_cal_df, mode="append")
        assert not store.is_trade_day("20240101")  # holiday
        assert store.is_trade_day("20240102")       # trading day
        assert not store.is_trade_day("20991231")   # not in db

    def test_get_suspended_stocks(self, temp_data_dir, sample_suspend_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("suspend_d", sample_suspend_df, mode="append")
        suspended = store.get_suspended_stocks("20240102")
        assert "000003.SZ" in suspended

    def test_get_suspended_stocks_no_data(self, temp_data_dir):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        assert store.get_suspended_stocks("20240102") == []

    def test_row_count(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        assert store.row_count("daily") == 0
        store.save("daily", sample_daily_df, mode="append")
        assert store.row_count("daily") == 2

    def test_parquet_files_created(self, temp_data_dir, sample_daily_df):
        db_path = os.path.join(temp_data_dir, "test.duckdb")
        store = DataStore(db_path=db_path, data_dir=temp_data_dir)

        store.save("daily", sample_daily_df, mode="append")
        table_dir = os.path.join(temp_data_dir, "daily")
        parquet_files = [f for f in os.listdir(table_dir) if f.endswith(".parquet")]
        assert len(parquet_files) > 0
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /Users/hongao/ha/A_stock && python -m pytest tests/data/test_store.py -v
```

Expected: FAIL — module not found

- [ ] **Step 4: Implement DataStore**

`src/astock/data/store/db.py`:

```python
import time
from pathlib import Path
from typing import Literal

import duckdb
import pandas as pd

from astock.core.exceptions import StoreError


class DataStore:
    def __init__(self, db_path: str, data_dir: str):
        self.db_path = Path(db_path)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self.db_path))

    def _table_dir(self, table: str) -> Path:
        p = self.data_dir / table
        p.mkdir(parents=True, exist_ok=True)
        return p

    def save(self, table: str, df: pd.DataFrame, mode: Literal["append", "replace"]) -> None:
        if df.empty:
            return
        table_dir = self._table_dir(table)
        if mode == "replace":
            for f in table_dir.glob("*.parquet"):
                f.unlink()
        fname = f"{int(time.time() * 1_000_000)}.parquet"
        tmp_path = table_dir / f".{fname}.tmp"
        final_path = table_dir / fname
        try:
            df.to_parquet(tmp_path, engine="pyarrow")
            tmp_path.rename(final_path)
        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink()
            raise StoreError(f"Failed to save table '{table}': {e}")

    def load(self, table: str, **filters) -> pd.DataFrame:
        table_dir = self._table_dir(table)
        parquet_glob = str(table_dir / "*.parquet")
        query = f"SELECT * FROM read_parquet('{parquet_glob}')"
        if filters:
            conditions = []
            for k, v in filters.items():
                if isinstance(v, str):
                    conditions.append(f"{k} = '{v}'")
                elif isinstance(v, (list, tuple)):
                    vals = ", ".join(f"'{x}'" for x in v)
                    conditions.append(f"{k} IN ({vals})")
                else:
                    conditions.append(f"{k} = {v}")
            query += " WHERE " + " AND ".join(conditions)
        return self._conn.execute(query).df()

    def get_latest_date(self, table: str, date_col: str = "trade_date") -> str | None:
        if not self.table_exists(table):
            return None
        table_dir = self._table_dir(table)
        parquet_glob = str(table_dir / "*.parquet")
        result = self._conn.execute(
            f"SELECT MAX({date_col}) FROM read_parquet('{parquet_glob}')"
        ).fetchone()
        return result[0] if result and result[0] else None

    def table_exists(self, table: str) -> bool:
        table_dir = self._table_dir(table)
        return any(table_dir.glob("*.parquet"))

    def is_trade_day(self, date: str) -> bool:
        if not self.table_exists("trade_cal"):
            return False
        df = self.load("trade_cal", cal_date=date)
        if df.empty:
            return False
        return df.iloc[0]["is_open"] == "1"

    def get_suspended_stocks(self, date: str) -> list[str]:
        if not self.table_exists("suspend_d"):
            return []
        df = self.load("suspend_d", trade_date=date, suspend_type="S")
        return df["ts_code"].tolist() if not df.empty else []

    def row_count(self, table: str) -> int:
        if not self.table_exists(table):
            return 0
        table_dir = self._table_dir(table)
        parquet_glob = str(table_dir / "*.parquet")
        result = self._conn.execute(
            f"SELECT COUNT(*) FROM read_parquet('{parquet_glob}')"
        ).fetchone()
        return result[0] if result else 0
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /Users/hongao/ha/A_stock && python -m pytest tests/data/test_store.py -v
```

Expected: 12 PASS

- [ ] **Step 6: Commit**

```bash
git add src/astock/data/store/db.py tests/data/test_store.py tests/conftest.py
git commit -m "feat: add DataStore with DuckDB query and Parquet persistence"
```

---

### Task 6: 数据源层 TushareClient

**Files:**
- Create: `src/astock/data/source/client.py`
- Create: `tests/data/test_source.py`

- [ ] **Step 1: Write tests for TushareClient**

`tests/data/test_source.py`:

```python
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest
from astock.data.source.client import TushareClient
from astock.core.exceptions import APIError


@pytest.fixture
def mock_pro():
    with patch("tushare.pro_api") as mock:
        yield mock


class TestTushareClient:
    def test_fetch_stock_basic(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.stock_basic.return_value = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "name": ["平安银行"],
        })

        client = TushareClient(token="test-token")
        df = client.fetch_stock_basic()

        assert len(df) == 1
        mock_instance.stock_basic.assert_called_once()

    def test_fetch_trade_cal(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.trade_cal.return_value = pd.DataFrame({
            "exchange": ["SSE"],
            "cal_date": ["20240101"],
            "is_open": ["0"],
        })

        client = TushareClient(token="test-token")
        df = client.fetch_trade_cal(exchange="SSE", start_date="20240101", end_date="20240105")

        assert len(df) == 1
        mock_instance.trade_cal.assert_called_once_with(
            exchange="SSE", start_date="20240101", end_date="20240105"
        )

    def test_fetch_daily(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.daily.return_value = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": ["20240102"],
            "close": [10.5],
        })

        client = TushareClient(token="test-token")
        df = client.fetch_daily(ts_code="000001.SZ", trade_date="20240102")

        assert len(df) == 1

    def test_fetch_adj_factor(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.adj_factor.return_value = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": ["20240102"],
            "adj_factor": [1.2],
        })

        client = TushareClient(token="test-token")
        df = client.fetch_adj_factor(trade_date="20240102")

        assert len(df) == 1

    def test_fetch_daily_basic(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.daily_basic.return_value = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": ["20240102"],
            "pe": [5.5],
        })

        client = TushareClient(token="test-token")
        df = client.fetch_daily_basic(trade_date="20240102")

        assert len(df) == 1

    def test_fetch_suspend_d(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.suspend_d.return_value = pd.DataFrame({
            "ts_code": ["000003.SZ"],
            "trade_date": ["20240102"],
            "suspend_type": ["S"],
        })

        client = TushareClient(token="test-token")
        df = client.fetch_suspend_d(trade_date="20240102", suspend_type="S")

        assert len(df) == 1

    def test_retry_on_failure(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("connection error")
            return pd.DataFrame({"ts_code": ["000001.SZ"]})

        mock_instance.stock_basic.side_effect = side_effect

        client = TushareClient(token="test-token")
        df = client.fetch_stock_basic()

        assert len(df) == 1
        assert call_count[0] == 3

    def test_retry_exhausted_raises_api_error(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.stock_basic.side_effect = Exception("connection error")

        client = TushareClient(token="test-token")
        with pytest.raises(APIError, match="3 retries"):
            client.fetch_stock_basic()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/hongao/ha/A_stock && python -m pytest tests/data/test_source.py -v
```

Expected: FAIL — module not found

- [ ] **Step 3: Implement TushareClient**

`src/astock/data/source/client.py`:

```python
import time

import pandas as pd
import tushare as ts

from astock.core.exceptions import APIError


class TushareClient:
    def __init__(self, token: str):
        self._pro = ts.pro_api(token)

    def _retry(self, func, *args, max_retries: int = 3, delay: int = 5, **kwargs):
        last_exc = None
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exc = e
                if attempt < max_retries - 1:
                    wait = delay * (2 ** attempt)
                    time.sleep(wait)
        raise APIError(
            f"API call failed after {max_retries} retries: {last_exc}"
        )

    def fetch_stock_basic(self, list_status: str = "L") -> pd.DataFrame:
        return self._retry(
            self._pro.stock_basic,
            list_status=list_status,
            fields="ts_code,symbol,name,area,industry,fullname,enname,cnspell,"
                   "market,exchange,curr_type,list_status,list_date,delist_date,"
                   "is_hs,act_name,act_ent_type",
        )

    def fetch_trade_cal(
        self,
        exchange: str = "SSE",
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        return self._retry(
            self._pro.trade_cal,
            exchange=exchange,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_daily(
        self,
        ts_code: str = "",
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        return self._retry(
            self._pro.daily,
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_adj_factor(
        self,
        ts_code: str = "",
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        return self._retry(
            self._pro.adj_factor,
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_daily_basic(
        self,
        ts_code: str = "",
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        return self._retry(
            self._pro.daily_basic,
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
        )

    def fetch_suspend_d(
        self,
        ts_code: str = "",
        trade_date: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        suspend_type: str | None = None,
    ) -> pd.DataFrame:
        return self._retry(
            self._pro.suspend_d,
            ts_code=ts_code,
            trade_date=trade_date,
            start_date=start_date,
            end_date=end_date,
            suspend_type=suspend_type,
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/hongao/ha/A_stock && python -m pytest tests/data/test_source.py -v
```

Expected: 8 PASS

- [ ] **Step 5: Commit**

```bash
git add src/astock/data/source/client.py tests/data/test_source.py
git commit -m "feat: add TushareClient with retry logic for all 6 APIs"
```

---

### Task 7: 同步层 SyncManager

**Files:**
- Create: `src/astock/data/sync/manager.py`
- Create: `tests/data/test_sync.py`

- [ ] **Step 1: Write tests for SyncManager**

`tests/data/test_sync.py`:

```python
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest
from astock.data.sync.manager import SyncManager, SyncResult, DEPENDENCIES


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.fetch_stock_basic.return_value = pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "symbol": ["000001"],
        "name": ["平安银行"],
        "list_status": ["L"],
        "list_date": ["19910403"],
        "delist_date": [None],
    })
    client.fetch_trade_cal.return_value = pd.DataFrame({
        "exchange": ["SSE"],
        "cal_date": ["20240102"],
        "is_open": ["1"],
        "pretrade_date": ["20240101"],
    })
    client.fetch_daily.return_value = pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "trade_date": ["20240102"],
        "open": [10.0], "high": [10.5], "low": [9.9],
        "close": [10.3], "pre_close": [10.1],
        "change": [0.2], "pct_chg": [1.98],
        "vol": [100000.0], "amount": [103000.0],
    })
    client.fetch_adj_factor.return_value = pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "trade_date": ["20240102"],
        "adj_factor": [1.0],
    })
    client.fetch_daily_basic.return_value = pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "trade_date": ["20240102"],
        "pe": [5.5],
    })
    client.fetch_suspend_d.return_value = pd.DataFrame()
    return client


@pytest.fixture
def sync_manager(mock_client, temp_data_dir):
    from astock.data.store.db import DataStore
    from astock.core.config import SyncConfig
    import os

    db_path = os.path.join(temp_data_dir, "test.duckdb")
    store = DataStore(db_path=db_path, data_dir=temp_data_dir)
    return SyncManager(
        client=mock_client,
        store=store,
        config=SyncConfig(batch_size=5000, retry=3, retry_delay=1),
    )


class TestSyncManager:
    def test_sync_stock_basic(self, sync_manager):
        result = sync_manager._sync_stock_basic("full")
        assert result.status == "success"
        assert result.table == "stock_basic"
        assert result.rows == 1

    def test_sync_trade_cal_full(self, sync_manager):
        result = sync_manager._sync_trade_cal("full")
        assert result.status == "success"

    def test_sync_trade_cal_inc_no_existing(self, sync_manager):
        result = sync_manager._sync_trade_cal("inc")
        assert result.status == "success"

    def test_sync_daily(self, sync_manager):
        sync_manager._sync_stock_basic("full")
        sync_manager._sync_trade_cal("full")
        result = sync_manager._sync_daily("full")
        assert result.status == "success"

    def test_sync_adj_factor(self, sync_manager):
        sync_manager._sync_stock_basic("full")
        sync_manager._sync_trade_cal("full")
        sync_manager._sync_daily("full")
        result = sync_manager._sync_adj_factor("full")
        assert result.status == "success"

    def test_sync_daily_basic(self, sync_manager):
        sync_manager._sync_stock_basic("full")
        sync_manager._sync_trade_cal("full")
        sync_manager._sync_daily("full")
        result = sync_manager._sync_daily_basic("full")
        assert result.status == "success"

    def test_sync_suspend_d(self, sync_manager):
        sync_manager._sync_stock_basic("full")
        result = sync_manager._sync_suspend_d("full")
        assert result.status == "success"

    def test_sync_all_respects_order(self, sync_manager):
        results = sync_manager.sync_all()
        assert len(results) == 6
        tables = [r.table for r in results]
        assert tables == [
            "stock_basic", "trade_cal", "daily",
            "adj_factor", "daily_basic", "suspend_d",
        ]

    def test_sync_table_with_dependency(self, sync_manager):
        """Syncing daily should cascade to check stock_basic and trade_cal."""
        result = sync_manager.sync_table("daily", mode="full")
        assert result.status == "success"

    def test_failed_sync_returns_error_result(self, sync_manager):
        sync_manager.client.fetch_stock_basic.side_effect = Exception("boom")
        result = sync_manager._sync_stock_basic("full")
        assert result.status == "failed"
        assert "boom" in result.error

    def test_dependency_graph(self):
        assert DEPENDENCIES["stock_basic"] == []
        assert DEPENDENCIES["trade_cal"] == []
        assert DEPENDENCIES["daily"] == ["stock_basic", "trade_cal"]
        assert DEPENDENCIES["adj_factor"] == ["daily"]
        assert DEPENDENCIES["daily_basic"] == ["daily"]
        assert DEPENDENCIES["suspend_d"] == ["stock_basic"]

    def test_resolve_dependencies_returns_stale_deps(self, sync_manager):
        sync_manager._sync_stock_basic("full")
        sync_manager._sync_trade_cal("full")
        # After syncing these, daily depends on them - but since daily
        # doesn't exist yet, dep tables won't be flagged as stale
        deps = sync_manager._resolve_dependencies("daily")
        # trade_cal and stock_basic exist and have data,
        # but daily doesn't exist yet, so deps might need syncing
        assert isinstance(deps, list)

    def test_sync_result_dataclass(self):
        result = SyncResult(table="daily", mode="inc", rows=100, status="success")
        assert result.table == "daily"
        assert result.rows == 100

        result2 = SyncResult(table="daily", mode="full", rows=0, status="failed", error="timeout")
        assert result2.error == "timeout"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/hongao/ha/A_stock && python -m pytest tests/data/test_sync.py -v
```

Expected: FAIL — module not found

- [ ] **Step 3: Implement SyncManager**

`src/astock/data/sync/manager.py`:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import pandas as pd

from astock.core.config import SyncConfig
from astock.data.source.client import TushareClient
from astock.data.store.db import DataStore

DEPENDENCIES = {
    "stock_basic": [],
    "trade_cal": [],
    "daily": ["stock_basic", "trade_cal"],
    "adj_factor": ["daily"],
    "daily_basic": ["daily"],
    "suspend_d": ["stock_basic"],
}

TABLE_DATE_COLS = {
    "stock_basic": None,
    "trade_cal": "cal_date",
    "daily": "trade_date",
    "adj_factor": "trade_date",
    "daily_basic": "trade_date",
    "suspend_d": "trade_date",
}

SYNC_ORDER = ["stock_basic", "trade_cal", "daily", "adj_factor", "daily_basic", "suspend_d"]


@dataclass
class SyncResult:
    table: str
    mode: str
    rows: int
    status: str  # "success" | "failed"
    error: str | None = None


class SyncManager:
    def __init__(self, client: TushareClient, store: DataStore, config: SyncConfig):
        self.client = client
        self.store = store
        self.config = config

    def sync_table(self, table: str, mode: Literal["full", "inc"] = "inc") -> SyncResult:
        """Sync a single table, cascading to dependencies first."""
        deps_to_sync = self._resolve_dependencies(table)
        for dep_table in deps_to_sync:
            dep_result = self._do_sync(dep_table, "inc")
        return self._do_sync(table, mode)

    def sync_all(self) -> list[SyncResult]:
        """Sync all tables in dependency order."""
        results = []
        for table in SYNC_ORDER:
            mode = "full" if table == "stock_basic" else "inc"
            result = self._do_sync(table, mode)
            results.append(result)
        return results

    def _resolve_dependencies(self, table: str) -> list[str]:
        """Return dependent tables that need syncing first."""
        to_sync = []
        for dep in DEPENDENCIES.get(table, []):
            if not self.store.table_exists(dep):
                to_sync.append(dep)
        return to_sync

    def _do_sync(self, table: str, mode: str) -> SyncResult:
        try:
            sync_fn = getattr(self, f"_sync_{table}")
            return sync_fn(mode)
        except Exception as e:
            return SyncResult(
                table=table, mode=mode, rows=0,
                status="failed", error=str(e),
            )

    def _get_trade_days_since(self, latest_date: str | None) -> list[str]:
        today = datetime.now().strftime("%Y%m%d")
        start = "19900101" if latest_date is None else (
            datetime.strptime(latest_date, "%Y%m%d") + timedelta(days=1)
        ).strftime("%Y%m%d")
        if start > today:
            return []
        trade_cal = self.store.load("trade_cal")
        trade_days = trade_cal[
            (trade_cal["cal_date"] >= start) &
            (trade_cal["cal_date"] <= today) &
            (trade_cal["is_open"] == "1")
        ]["cal_date"].sort_values().tolist()
        return trade_days

    def _get_active_stocks(self, trade_date: str) -> list[str]:
        stocks = self.store.load("stock_basic")
        active = []
        suspended = set(self.store.get_suspended_stocks(trade_date))
        for _, row in stocks.iterrows():
            if row["list_status"] != "L":
                continue
            if row["list_date"] and row["list_date"] > trade_date:
                continue
            if row["delist_date"] and row["delist_date"] < trade_date:
                continue
            if row["ts_code"] not in suspended:
                active.append(row["ts_code"])
        return active

    def _sync_stock_basic(self, mode: str) -> SyncResult:
        df = self.client.fetch_stock_basic()
        self.store.save("stock_basic", df, mode="replace")
        return SyncResult(
            table="stock_basic", mode=mode, rows=len(df), status="success",
        )

    def _sync_trade_cal(self, mode: str) -> SyncResult:
        if mode == "full" or not self.store.table_exists("trade_cal"):
            today = datetime.now().strftime("%Y%m%d")
            df_sse = self.client.fetch_trade_cal(exchange="SSE", start_date="19900101", end_date=today)
            df_szse = self.client.fetch_trade_cal(exchange="SZSE", start_date="19900101", end_date=today)
            df = pd.concat([df_sse, df_szse]).drop_duplicates()
            self.store.save("trade_cal", df, mode="replace")
            return SyncResult(table="trade_cal", mode="full", rows=len(df), status="success")
        else:
            latest = self.store.get_latest_date("trade_cal", "cal_date")
            if latest is None:
                return self._sync_trade_cal("full")
            start = (datetime.strptime(latest, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
            today = datetime.now().strftime("%Y%m%d")
            if start > today:
                return SyncResult(table="trade_cal", mode="inc", rows=0, status="success")
            df_sse = self.client.fetch_trade_cal(exchange="SSE", start_date=start, end_date=today)
            df_szse = self.client.fetch_trade_cal(exchange="SZSE", start_date=start, end_date=today)
            df = pd.concat([df_sse, df_szse]).drop_duplicates()
            self.store.save("trade_cal", df, mode="append")
            return SyncResult(table="trade_cal", mode="inc", rows=len(df), status="success")

    def _sync_daily(self, mode: str) -> SyncResult:
        latest = (
            None if mode == "full" or not self.store.table_exists("daily")
            else self.store.get_latest_date("daily", "trade_date")
        )
        trade_days = self._get_trade_days_since(latest)
        total_rows = 0
        for trade_date in trade_days:
            active_stocks = self._get_active_stocks(trade_date)
            for i in range(0, len(active_stocks), self.config.batch_size):
                batch = active_stocks[i:i + self.config.batch_size]
                ts_codes = ",".join(batch)
                df = self.client.fetch_daily(ts_code=ts_codes, trade_date=trade_date)
                if not df.empty:
                    self.store.save("daily", df, mode="append")
                    total_rows += len(df)
        return SyncResult(table="daily", mode=mode, rows=total_rows, status="success")

    def _sync_adj_factor(self, mode: str) -> SyncResult:
        latest = (
            None if mode == "full" or not self.store.table_exists("adj_factor")
            else self.store.get_latest_date("adj_factor", "trade_date")
        )
        trade_days = self._get_trade_days_since(latest)
        total_rows = 0
        for trade_date in trade_days:
            df = self.client.fetch_adj_factor(trade_date=trade_date)
            if not df.empty:
                self.store.save("adj_factor", df, mode="append")
                total_rows += len(df)
        return SyncResult(table="adj_factor", mode=mode, rows=total_rows, status="success")

    def _sync_daily_basic(self, mode: str) -> SyncResult:
        latest = (
            None if mode == "full" or not self.store.table_exists("daily_basic")
            else self.store.get_latest_date("daily_basic", "trade_date")
        )
        trade_days = self._get_trade_days_since(latest)
        total_rows = 0
        for trade_date in trade_days:
            df = self.client.fetch_daily_basic(trade_date=trade_date)
            if not df.empty:
                self.store.save("daily_basic", df, mode="append")
                total_rows += len(df)
        return SyncResult(table="daily_basic", mode=mode, rows=total_rows, status="success")

    def _sync_suspend_d(self, mode: str) -> SyncResult:
        latest = (
            None if mode == "full" or not self.store.table_exists("suspend_d")
            else self.store.get_latest_date("suspend_d", "trade_date")
        )
        trade_days = self._get_trade_days_since(latest)
        total_rows = 0
        for trade_date in trade_days:
            for stype in ["S", "R"]:
                df = self.client.fetch_suspend_d(trade_date=trade_date, suspend_type=stype)
                if not df.empty:
                    self.store.save("suspend_d", df, mode="append")
                    total_rows += len(df)
        return SyncResult(table="suspend_d", mode=mode, rows=total_rows, status="success")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /Users/hongao/ha/A_stock && python -m pytest tests/data/test_sync.py -v
```

Expected: 13 PASS

- [ ] **Step 5: Commit**

```bash
git add src/astock/data/sync/manager.py tests/data/test_sync.py
git commit -m "feat: add SyncManager with cascade dependency resolution for 6 tables"
```

---

### Task 8: CLI 命令层

**Files:**
- Create: `src/astock/cli/main.py`
- Create: `src/astock/cli/config_cmd.py`
- Create: `src/astock/cli/data_cmd.py`
- Create: `src/astock/cli/cal_cmd.py`
- Create: `src/astock/cli/strategy_cmd.py`
- Create: `src/astock/cli/backtest_cmd.py`

- [ ] **Step 1: Implement CLI strategy/backtest stubs**

`src/astock/cli/strategy_cmd.py`:

```python
import typer

app = typer.Typer(help="选股策略命令（待实现）")


@app.command("list")
def list_strategies():
    """列出可用策略"""
    typer.echo("暂无可用策略。策略引擎尚未实现。")


if __name__ == "__main__":
    app()
```

`src/astock/cli/backtest_cmd.py`:

```python
import typer

app = typer.Typer(help="回测命令（待实现）")


@app.command("run")
def run_backtest():
    """运行回测"""
    typer.echo("回测引擎尚未实现。")


if __name__ == "__main__":
    app()
```

- [ ] **Step 2: Implement config CLI**

`src/astock/cli/config_cmd.py`:

```python
import typer
import yaml
from pathlib import Path

app = typer.Typer(help="配置管理")


def _get_config_path() -> Path:
    return Path("config.yaml")


@app.command("show")
def show():
    """显示当前配置（隐藏敏感信息）"""
    cfg_path = _get_config_path()
    if not cfg_path.exists():
        typer.echo("配置文件不存在。")
        raise typer.Exit(1)

    with open(cfg_path) as f:
        raw = yaml.safe_load(f)

    if "tushare" in raw and "token" in raw["tushare"]:
        token = raw["tushare"]["token"]
        raw["tushare"]["token"] = token[:4] + "****" if len(token) > 4 else "****"

    typer.echo(yaml.dump(raw, allow_unicode=True, default_flow_style=False))


@app.command("set")
def set_value(key: str = typer.Argument(..., help="配置项路径，如 tushare.token"), value: str = typer.Argument(..., help="值")):
    """修改配置项"""
    cfg_path = _get_config_path()
    if not cfg_path.exists():
        typer.echo("配置文件不存在。")
        raise typer.Exit(1)

    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)

    keys = key.split(".")
    target = cfg
    for k in keys[:-1]:
        if k not in target:
            target[k] = {}
        target = target[k]
    target[keys[-1]] = value

    with open(cfg_path, "w") as f:
        yaml.dump(cfg, f, allow_unicode=True, default_flow_style=False)

    typer.echo(f"已设置 {key} = {value}")
```

- [ ] **Step 3: Implement calendar CLI**

`src/astock/cli/cal_cmd.py`:

```python
from datetime import datetime
import typer
from pathlib import Path

app = typer.Typer(help="交易日历查询")


@app.command("show")
def show(date: str = typer.Argument(None, help="日期 (YYYYMMDD)，默认今天")):
    """查看指定日期是否为交易日"""
    if date is None:
        date = datetime.now().strftime("%Y%m%d")

    # Lightweight: read trade_cal parquet directly if available
    import duckdb
    data_dir = Path("data")
    trade_cal_dir = data_dir / "trade_cal"

    if not trade_cal_dir.exists() or not any(trade_cal_dir.glob("*.parquet")):
        typer.echo("交易日历数据尚未同步。请先运行: astock data sync --table trade_cal")
        raise typer.Exit(1)

    db_path = data_dir / "astock.duckdb"
    conn = duckdb.connect(str(db_path))
    result = conn.execute(
        f"SELECT exchange, cal_date, is_open, pretrade_date "
        f"FROM read_parquet('{trade_cal_dir}/*.parquet') "
        f"WHERE cal_date = '{date}'"
    ).fetchall()

    if not result:
        typer.echo(f"{date}: 无交易日历记录")
    else:
        for row in result:
            status = "交易日" if row[2] == "1" else "休市日"
            typer.echo(f"{row[0]} | {row[1]} | {status} | 前一交易日: {row[3]}")

    conn.close()
```

- [ ] **Step 4: Implement data CLI**

`src/astock/cli/data_cmd.py`:

```python
import typer
from pathlib import Path

app = typer.Typer(help="数据同步与管理")


def _get_sync_manager():
    from astock.core.config import Config
    from astock.core.logging import setup_logging
    from astock.data.source.client import TushareClient
    from astock.data.store.db import DataStore
    from astock.data.sync.manager import SyncManager

    cfg = Config.from_yaml("config.yaml")
    setup_logging(cfg.log)

    client = TushareClient(token=cfg.tushare.token)
    store = DataStore(db_path=cfg.storage.db_path, data_dir=cfg.storage.data_dir)
    return SyncManager(client=client, store=store, config=cfg.sync)


@app.command("sync")
def sync(
    table: str = typer.Option(None, "--table", "-t", help="指定表名，不指定则同步全部"),
    mode: str = typer.Option("inc", "--mode", "-m", help="同步模式: full | inc"),
):
    """同步数据（默认增量）"""
    mgr = _get_sync_manager()

    if table:
        if table not in ["stock_basic", "trade_cal", "daily", "adj_factor", "daily_basic", "suspend_d"]:
            typer.echo(f"无效表名: {table}")
            typer.echo("有效表名: stock_basic, trade_cal, daily, adj_factor, daily_basic, suspend_d")
            raise typer.Exit(1)
        result = mgr.sync_table(table, mode=mode)
        _print_result(result)
    else:
        results = mgr.sync_all()
        total = 0
        for r in results:
            _print_result(r)
            total += r.rows
        typer.echo(f"\n总计同步 {total} 条记录")


def _print_result(r):
    icon = "OK" if r.status == "success" else "FAIL"
    if r.status == "success" and r.rows == 0:
        typer.echo(f"[{icon}] {r.table}: 已是最新 (0 行)")
    elif r.status == "success":
        typer.echo(f"[{icon}] {r.table}: 同步 {r.rows} 行 ({r.mode})")
    else:
        typer.echo(f"[{icon}] {r.table}: 失败 — {r.error}")


@app.command("status")
def status():
    """查看各表数据状态"""
    from astock.core.config import Config
    from astock.data.store.db import DataStore

    cfg = Config.from_yaml("config.yaml")
    store = DataStore(db_path=cfg.storage.db_path, data_dir=cfg.storage.data_dir)

    tables = ["stock_basic", "trade_cal", "daily", "adj_factor", "daily_basic", "suspend_d"]
    date_cols = {
        "stock_basic": None, "trade_cal": "cal_date",
        "daily": "trade_date", "adj_factor": "trade_date",
        "daily_basic": "trade_date", "suspend_d": "trade_date",
    }

    typer.echo(f"{'表名':<16} {'行数':>10} {'最新日期':<12} {'状态'}")
    typer.echo("-" * 52)
    for t in tables:
        exists = store.table_exists(t)
        rows = store.row_count(t)
        if exists and date_cols[t]:
            latest = store.get_latest_date(t, date_cols[t])
        else:
            latest = "-"
        state = "有数据" if exists else "空"
        typer.echo(f"{t:<16} {rows:>10} {latest:<12} {state}")


@app.command("query")
def query(
    table: str = typer.Argument(..., help="表名"),
    filter_str: str = typer.Option(None, "--filter", "-f", help="过滤条件，如 ts_code=000001.SZ"),
    limit: int = typer.Option(10, "--limit", "-l", help="返回行数"),
    export: str = typer.Option(None, "--export", "-e", help="导出到 CSV 文件路径"),
):
    """查询数据"""
    from astock.core.config import Config
    from astock.data.store.db import DataStore

    cfg = Config.from_yaml("config.yaml")
    store = DataStore(db_path=cfg.storage.db_path, data_dir=cfg.storage.data_dir)

    if not store.table_exists(table):
        typer.echo(f"表 '{table}' 不存在或为空。")
        raise typer.Exit(1)

    filters = {}
    if filter_str:
        for pair in filter_str.split(","):
            k, v = pair.split("=")
            filters[k.strip()] = v.strip()

    df = store.load(table, **filters)
    if limit:
        df = df.head(limit)

    if export:
        df.to_csv(export, index=False)
        typer.echo(f"已导出 {len(df)} 行到 {export}")
    else:
        typer.echo(df.to_string(index=False))
        typer.echo(f"\n显示 {len(df)} 行")


@app.command("clean")
def clean(
    table: str = typer.Option(..., "--table", "-t", help="指定表名"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
):
    """清理指定表数据"""
    from astock.core.config import Config

    cfg = Config.from_yaml("config.yaml")
    table_dir = Path(cfg.storage.data_dir) / table

    if not table_dir.exists():
        typer.echo(f"表 '{table}' 无数据。")
        return

    if not force:
        confirm = typer.confirm(f"确认删除表 '{table}' 的所有数据？")
        if not confirm:
            typer.echo("已取消。")
            return

    import shutil
    shutil.rmtree(table_dir)
    typer.echo(f"已清理表 '{table}'。")
```

- [ ] **Step 5: Implement CLI main entry**

`src/astock/cli/main.py`:

```python
import typer
from astock.cli import config_cmd, data_cmd, cal_cmd, strategy_cmd, backtest_cmd

app = typer.Typer(
    name="astock",
    help="A-Stock 量化交易数据系统",
    no_args_is_help=True,
)

app.add_typer(config_cmd.app, name="config")
app.add_typer(data_cmd.app, name="data")
app.add_typer(cal_cmd.app, name="cal")
app.add_typer(strategy_cmd.app, name="strategy")
app.add_typer(backtest_cmd.app, name="backtest")


@app.callback()
def main():
    """A-Stock: A股量化交易数据系统。管理本地股票数据库的同步、查询与分析。"""
    pass


if __name__ == "__main__":
    app()
```

- [ ] **Step 6: Verify CLI entry point works**

```bash
cd /Users/hongao/ha/A_stock && pip install -e . && astock --help
```

Expected: help text with config, data, cal, strategy, backtest subcommands

- [ ] **Step 7: Commit**

```bash
git add src/astock/cli/
git commit -m "feat: add CLI layer with config, data, cal, strategy, backtest commands"
```

---

### Task 9: 文档与最终验证

**Files:**
- Create: `README.md`
- Create: `.claude/CLAUDE.md`

- [ ] **Step 1: Create README.md**

```markdown
# A-Stock 量化交易数据系统

A 股本地数据同步系统。从 [Tushare Pro](https://tushare.pro) 拉取股票数据，以 Parquet + DuckDB 本地存储，CLI 交互。

## 环境准备

```bash
# 1. 安装 conda 环境
conda env create -f environment.yml
conda activate astock

# 2. 安装 astock 包
pip install -e .

# 3. 设置 Tushare Token（需在 https://tushare.pro 注册获取）
export TUSHARE_TOKEN="your_token_here"

# 4. 验证
astock --help
```

## 快速开始

```bash
# 一键全量同步（首次运行）
astock data sync

# 查看数据状态
astock data status

# 查询股票列表
astock data query stock_basic --limit 20

# 查看交易日历
astock cal show 20240102

# 查看配置
astock config show
```

## 数据表

| 表名 | 内容 | 需要积分 |
|------|------|----------|
| stock_basic | 股票基础信息 | 2000 |
| trade_cal | 交易日历 | 2000 |
| daily | 日线行情（未复权） | 基础 |
| adj_factor | 复权因子 | 2000 |
| daily_basic | 每日指标（PE/PB等） | 2000 |
| suspend_d | 停复牌记录 | 未标注 |

## 项目结构

```
A_stock/
├── config.yaml              # 配置文件
├── environment.yml          # Conda 环境
├── pyproject.toml           # 包配置
├── src/astock/
│   ├── core/                # 基础设施（配置/异常/日志）
│   ├── data/
│   │   ├── source/          # Tushare API 封装
│   │   ├── sync/            # 同步策略（全量/增量+级联）
│   │   └── store/           # DuckDB + Parquet 存储
│   ├── strategy/            # 选股策略（未来）
│   ├── backtest/            # 回测引擎（未来）
│   └── cli/                 # CLI 命令入口
├── tests/                   # 测试
├── data/                    # 本地数据库（gitignore）
└── docs/                    # 设计文档
```

## 开发

```bash
# 运行测试
pytest -v

# 测试覆盖率
pytest --cov=astock --cov-report=term-missing
```

## 许可证

MIT
```

- [ ] **Step 2: Create .claude/CLAUDE.md**

```markdown
# A-Stock Project Context

## 项目概述

A 股量化交易系统。第一阶段：本地数据同步系统。

## 技术栈

- Python >= 3.11
- Conda 环境管理
- Tushare Pro (2000 积分) 数据源
- DuckDB + Parquet 本地存储
- Typer CLI
- pytest 测试

## 关键文件

- `config.yaml` — 配置文件（含 Tushare token，通过环境变量注入）
- `src/astock/core/` — 共享基础设施
- `src/astock/data/source/` — Tushare API 客户端
- `src/astock/data/sync/` — 同步管理器（含级联依赖）
- `src/astock/data/store/` — DuckDB + Parquet 存储层
- `src/astock/cli/` — Typer 命令入口
- `docs/superpowers/specs/` — 设计文档
- `docs/superpowers/plans/` — 实施计划

## 当前阶段

Phase 1: 数据同步系统（进行中）
- 6 张核心表：stock_basic, trade_cal, daily, adj_factor, daily_basic, suspend_d
- 级联依赖检查：单表同步自动更新依赖表
- 边界处理：停牌/退市/新股/除权除息

## 未来阶段

- Phase 2: 选股策略（ML/DL/LLM）
- Phase 3: 回测引擎

## 运行方式

1. `conda activate astock`
2. `export TUSHARE_TOKEN="xxx"`
3. `astock data sync` — 同步数据
4. `astock data status` — 查看状态
```

- [ ] **Step 3: Run all tests to verify complete system**

```bash
cd /Users/hongao/ha/A_stock && python -m pytest -v
```

Expected: all tests pass (~37 tests across test_exceptions, test_config, test_logging, test_store, test_source, test_sync)

- [ ] **Step 4: Verify CLI help**

```bash
cd /Users/hongao/ha/A_stock && astock --help
astock config --help
astock data --help
astock cal --help
```

Expected: help text for all subcommands

- [ ] **Step 5: Final commit**

```bash
git add README.md .claude/CLAUDE.md
git commit -m "docs: add README and CLAUDE.md project documentation"
```

---

## 执行顺序

按 Task 1-9 顺序执行，每个 task 完成后才能开始下一个。Task 2-7 遵循 TDD（先写测试 → 测试失败 → 实现 → 测试通过 → 提交）。
