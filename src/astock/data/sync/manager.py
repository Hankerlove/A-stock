import time
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
            self._do_sync(dep_table, "inc")
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
        if not self.store.table_exists("trade_cal"):
            return []
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
            (trade_cal["is_open"].astype(str) == "1")
        ]["cal_date"].sort_values().tolist()
        return trade_days

    def _get_active_stocks(self, trade_date: str) -> list[str]:
        stocks = self.store.load("stock_basic")
        active = []
        suspended = set(self.store.get_suspended_stocks(trade_date))
        for _, row in stocks.iterrows():
            if row["list_status"] != "L":
                continue
            if pd.notna(row["list_date"]) and row["list_date"] > trade_date:
                continue
            if pd.notna(row["delist_date"]) and row["delist_date"] < trade_date:
                continue
            if row["ts_code"] not in suspended:
                active.append(row["ts_code"])
        return active

    def _sync_stock_basic(self, mode: str) -> SyncResult:
        try:
            df = self.client.fetch_stock_basic()
            self.store.save("stock_basic", df, mode="replace")
            return SyncResult(
                table="stock_basic", mode=mode, rows=len(df), status="success",
            )
        except Exception as e:
            return SyncResult(
                table="stock_basic", mode=mode, rows=0,
                status="failed", error=str(e),
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
        # Overlap 5 calendar days on resume to catch incomplete dates from prior failures
        if latest is not None and mode != "full":
            overlap_dt = datetime.strptime(latest, "%Y%m%d") - timedelta(days=5)
            latest = overlap_dt.strftime("%Y%m%d")
        trade_days = self._get_trade_days_since(latest)
        batch_size = min(self.config.batch_size, 1000)
        total_rows = 0
        for trade_date in trade_days:
            active_stocks = self._get_active_stocks(trade_date)
            date_rows = []
            for i in range(0, len(active_stocks), batch_size):
                batch = active_stocks[i:i + batch_size]
                ts_codes = ",".join(batch)
                df = self.client.fetch_daily(ts_code=ts_codes, trade_date=trade_date)
                if not df.empty:
                    date_rows.append(df)
                time.sleep(0.4)
            if date_rows:
                merged = pd.concat(date_rows, ignore_index=True)
                self.store.save("daily", merged, mode="append")
                total_rows += len(merged)
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
            time.sleep(0.4)
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
            time.sleep(0.4)
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
                time.sleep(0.4)
        return SyncResult(table="suspend_d", mode=mode, rows=total_rows, status="success")
