import os
import re
from dataclasses import dataclass
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

        token = data.get("tushare", {}).get("token", "")
        if not token:
            raise ConfigError("Missing tushare token or TUSHARE_TOKEN environment variable")

        return cls(
            tushare=TushareConfig(token=token),
            storage=StorageConfig(**data.get("storage", {})),
            sync=SyncConfig(**data.get("sync", {})),
            log=LogConfig(**data.get("log", {})),
        )
