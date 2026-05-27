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
