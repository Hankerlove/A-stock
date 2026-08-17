import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

import pandas as pd

from astock.core.config import SyncConfig
from astock.data.indicator.compute import compute_indicators
from astock.data.source.client import TushareClient
from astock.data.store.db import DataStore

DEPENDENCIES = {
    "stock_basic": [],
    "trade_cal": [],
    "daily": ["stock_basic", "trade_cal"],
    "adj_factor": ["daily"],
    "daily_basic": ["daily"],
    "suspend_d": ["stock_basic"],
    "tech_indicator": ["daily", "adj_factor"],
}

TABLE_DATE_COLS = {
    "stock_basic": None,
    "trade_cal": "cal_date",
    "daily": "trade_date",
    "adj_factor": "trade_date",
    "daily_basic": "trade_date",
    "suspend_d": "trade_date",
    "tech_indicator": "trade_date",
}

SYNC_ORDER = ["stock_basic", "trade_cal", "daily", "adj_factor", "daily_basic", "suspend_d", "tech_indicator"]


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
        self._safe_today_cache: str | None = None

    def _get_safe_today(self, max_probe_days: int = 5) -> str:
        """获取本次同步的安全截止日期。

        从今天往回探测 Tushare daily 接口，找到最近一个有日线数据的日期。
        不依赖本地 trade_cal（可能过期），直接从 API 层探测，避免鸡生蛋问题。
        结果会缓存，同一 SyncManager 实例多次调用只探测一次。
        """
        if self._safe_today_cache is not None:
            return self._safe_today_cache

        today = datetime.now()
        for offset in range(max_probe_days):
            date = (today - timedelta(days=offset)).strftime("%Y%m%d")
            try:
                # 用一只流动性好的股票探测该日期是否有日线数据
                df = self.client.fetch_daily(ts_code="000001.SZ", trade_date=date)
                if not df.empty:
                    self._safe_today_cache = date
                    print(f"  [sync] 安全截止日期: {date} (日线数据可用)", flush=True)
                    return date
            except Exception:
                continue

        # 探测范围内都没有数据（如长假后），返回今天
        fallback = today.strftime("%Y%m%d")
        self._safe_today_cache = fallback
        print(f"  [sync] 安全截止日期: {fallback} (未探测到日线数据，使用今天)", flush=True)
        return fallback

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
        end_date = self._get_safe_today()
        start = "19900101" if latest_date is None else (
            datetime.strptime(latest_date, "%Y%m%d") + timedelta(days=1)
        ).strftime("%Y%m%d")
        if start > end_date:
            return []
        trade_cal = self.store.load("trade_cal")
        trade_days = trade_cal[
            (trade_cal["cal_date"] >= start) &
            (trade_cal["cal_date"] <= end_date) &
            (trade_cal["is_open"].astype(str) == "1")
        ]["cal_date"].drop_duplicates().sort_values().tolist()
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
            print("  [stock_basic] 拉取中...", flush=True)
            df = self.client.fetch_stock_basic()
            self.store.save("stock_basic", df, mode="replace")
            print(f"  [stock_basic] 完成，{len(df)} 条记录", flush=True)
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
            print("  [trade_cal] 全量拉取 SSE + SZSE ...", flush=True)
            end_date = self._get_safe_today()
            df_sse = self.client.fetch_trade_cal(exchange="SSE", start_date="19900101", end_date=end_date)
            df_szse = self.client.fetch_trade_cal(exchange="SZSE", start_date="19900101", end_date=end_date)
            df = pd.concat([df_sse, df_szse]).drop_duplicates()
            self.store.save("trade_cal", df, mode="replace")
            print(f"  [trade_cal] 完成，{len(df)} 条记录", flush=True)
            return SyncResult(table="trade_cal", mode="full", rows=len(df), status="success")
        else:
            latest = self.store.get_latest_date("trade_cal", "cal_date")
            if latest is None:
                return self._sync_trade_cal("full")
            start = (datetime.strptime(latest, "%Y%m%d") + timedelta(days=1)).strftime("%Y%m%d")
            end_date = self._get_safe_today()
            if start > end_date:
                return SyncResult(table="trade_cal", mode="inc", rows=0, status="success")
            df_sse = self.client.fetch_trade_cal(exchange="SSE", start_date=start, end_date=end_date)
            df_szse = self.client.fetch_trade_cal(exchange="SZSE", start_date=start, end_date=end_date)
            df = pd.concat([df_sse, df_szse]).drop_duplicates()
            self.store.save("trade_cal", df, mode="append")
            return SyncResult(table="trade_cal", mode="inc", rows=len(df), status="success")

    def _sync_daily(self, mode: str) -> SyncResult:
        latest = (
            None if mode == "full" or not self.store.table_exists("daily")
            else self.store.get_latest_date("daily", "trade_date")
        )
        trade_days = self._get_trade_days_since(latest)
        if not trade_days:
            print("  [daily] 已是最新", flush=True)
            return SyncResult(table="daily", mode=mode, rows=0, status="success")

        batch_size = min(self.config.batch_size, 1000)
        total_rows = 0
        total_dates = len(trade_days)
        print(f"  [daily] 共 {total_dates} 个交易日待同步 (batch={batch_size})", flush=True)

        for idx, trade_date in enumerate(trade_days):
            active_stocks = self._get_active_stocks(trade_date)
            batches = (len(active_stocks) + batch_size - 1) // batch_size
            date_rows = []
            for i in range(0, len(active_stocks), batch_size):
                batch = active_stocks[i:i + batch_size]
                ts_codes = ",".join(batch)
                df = self.client.fetch_daily(ts_code=ts_codes, trade_date=trade_date)
                if not df.empty:
                    date_rows.append(df)
                time.sleep(3.0)
            if date_rows:
                merged = pd.concat(date_rows, ignore_index=True)
                self.store.save("daily", merged, mode="append")
                total_rows += len(merged)

            # 进度：每 50 个交易日或最后一个打印
            if (idx + 1) % 50 == 0 or idx == total_dates - 1:
                pct = (idx + 1) * 100 // total_dates
                print(f"  [daily] {idx + 1}/{total_dates} ({pct}%)  {trade_date}  "
                      f"stocks={len(active_stocks)} 累计={total_rows:,}行", flush=True)

        return SyncResult(table="daily", mode=mode, rows=total_rows, status="success")

    def _sync_adj_factor(self, mode: str) -> SyncResult:
        latest = (
            None if mode == "full" or not self.store.table_exists("adj_factor")
            else self.store.get_latest_date("adj_factor", "trade_date")
        )
        trade_days = self._get_trade_days_since(latest)
        if not trade_days:
            print("  [adj_factor] 已是最新", flush=True)
            return SyncResult(table="adj_factor", mode=mode, rows=0, status="success")

        total_rows = 0
        total_dates = len(trade_days)
        print(f"  [adj_factor] 共 {total_dates} 个交易日待同步", flush=True)

        for idx, trade_date in enumerate(trade_days):
            df = self.client.fetch_adj_factor(trade_date=trade_date)
            if not df.empty:
                self.store.save("adj_factor", df, mode="append")
                total_rows += len(df)
            time.sleep(0.5)
            if (idx + 1) % 100 == 0 or idx == total_dates - 1:
                pct = (idx + 1) * 100 // total_dates
                print(f"  [adj_factor] {idx + 1}/{total_dates} ({pct}%)  "
                      f"{trade_date} 累计={total_rows:,}行", flush=True)

        return SyncResult(table="adj_factor", mode=mode, rows=total_rows, status="success")

    def _sync_daily_basic(self, mode: str) -> SyncResult:
        latest = (
            None if mode == "full" or not self.store.table_exists("daily_basic")
            else self.store.get_latest_date("daily_basic", "trade_date")
        )
        trade_days = self._get_trade_days_since(latest)
        if not trade_days:
            print("  [daily_basic] 已是最新", flush=True)
            return SyncResult(table="daily_basic", mode=mode, rows=0, status="success")

        total_rows = 0
        total_dates = len(trade_days)
        print(f"  [daily_basic] 共 {total_dates} 个交易日待同步", flush=True)

        for idx, trade_date in enumerate(trade_days):
            df = self.client.fetch_daily_basic(trade_date=trade_date)
            if not df.empty:
                self.store.save("daily_basic", df, mode="append")
                total_rows += len(df)
            time.sleep(3.0)
            if (idx + 1) % 100 == 0 or idx == total_dates - 1:
                pct = (idx + 1) * 100 // total_dates
                print(f"  [daily_basic] {idx + 1}/{total_dates} ({pct}%)  "
                      f"{trade_date} 累计={total_rows:,}行", flush=True)

        return SyncResult(table="daily_basic", mode=mode, rows=total_rows, status="success")

    def _sync_suspend_d(self, mode: str) -> SyncResult:
        latest = (
            None if mode == "full" or not self.store.table_exists("suspend_d")
            else self.store.get_latest_date("suspend_d", "trade_date")
        )
        trade_days = self._get_trade_days_since(latest)
        if not trade_days:
            print("  [suspend_d] 已是最新", flush=True)
            return SyncResult(table="suspend_d", mode=mode, rows=0, status="success")

        total_rows = 0
        total_dates = len(trade_days)
        print(f"  [suspend_d] 共 {total_dates} 个交易日待同步", flush=True)

        for idx, trade_date in enumerate(trade_days):
            for stype in ["S", "R"]:
                df = self.client.fetch_suspend_d(trade_date=trade_date, suspend_type=stype)
                if not df.empty:
                    self.store.save("suspend_d", df, mode="append")
                    total_rows += len(df)
                time.sleep(2.0)
            if (idx + 1) % 50 == 0 or idx == total_dates - 1:
                pct = (idx + 1) * 100 // total_dates
                print(f"  [suspend_d] {idx + 1}/{total_dates} ({pct}%)  "
                      f"{trade_date} 累计={total_rows:,}行", flush=True)

        return SyncResult(table="suspend_d", mode=mode, rows=total_rows, status="success")

    def _load_table_for_stocks(self, table: str, ts_codes: list[str], date_start: str, date_end: str) -> pd.DataFrame:
        """Load parquet data for specific stocks within a date range via DuckDB.

        Avoids loading the entire table into memory. Returns empty DataFrame
        when the table has no parquet files or the stock list is empty.
        """
        if not ts_codes:
            return pd.DataFrame()
        table_dir = self.store._table_dir(table)
        if not any(table_dir.glob("*.parquet")):
            return pd.DataFrame()
        parquet_glob = str(table_dir / "*.parquet")
        codes_fmt = ", ".join(f"'{c}'" for c in ts_codes)
        query = (
            f"SELECT * FROM read_parquet('{parquet_glob}', union_by_name=true) "
            f"WHERE ts_code IN ({codes_fmt}) "
            f"AND trade_date >= '{date_start}' "
            f"AND trade_date <= '{date_end}'"
        )
        return self.store._conn.execute(query).df()

    def _sync_tech_indicator(self, mode: str) -> SyncResult:
        is_full = mode == "full" or not self.store.table_exists("tech_indicator")
        latest = None if is_full else self.store.get_latest_date("tech_indicator", "trade_date")
        trade_days = self._get_trade_days_since(latest)
        if not is_full and not trade_days:
            print("  [tech_indicator] 已是最新", flush=True)
            return SyncResult(table="tech_indicator", mode=mode, rows=0, status="success")

        if is_full:
            print("  [tech_indicator] 全量模式，按 chunk 分批处理...", flush=True)
        else:
            print(f"  [tech_indicator] 增量模式，{len(trade_days)} 个新交易日", flush=True)

        # Get active stock codes
        stocks = self.store.load("stock_basic")
        active_codes = stocks[stocks["list_status"] == "L"]["ts_code"].tolist()
        if not active_codes:
            print("  [tech_indicator] 无有效股票", flush=True)
            return SyncResult(table="tech_indicator", mode=mode, rows=0, status="success")

        # Date bounds: for inc mode, load 120 calendar days before first new
        # trade day to ensure enough history for MA60 and other indicators
        date_end = datetime.now().strftime("%Y%m%d")
        if is_full:
            date_start = "19900101"
        else:
            date_start = (
                datetime.strptime(trade_days[0], "%Y%m%d") - timedelta(days=120)
            ).strftime("%Y%m%d")

        total_saved = 0
        processed = 0
        total_stocks = len(active_codes)
        chunk_size = 200
        is_first_chunk = True

        for chunk_start in range(0, len(active_codes), chunk_size):
            chunk_codes = active_codes[chunk_start:chunk_start + chunk_size]

            # Load per-chunk via DuckDB instead of loading everything upfront
            daily = self._load_table_for_stocks("daily", chunk_codes, date_start, date_end)
            adj = self._load_table_for_stocks("adj_factor", chunk_codes, date_start, date_end)
            if daily.empty or adj.empty:
                processed += len(chunk_codes)
                continue

            # Clean legacy index column from parquet load
            for c in ["__index_level_0__"]:
                if c in daily.columns:
                    daily = daily.drop(columns=[c])
                if c in adj.columns:
                    adj = adj.drop(columns=[c])

            merged = pd.merge(daily, adj, on=["ts_code", "trade_date"], how="inner")
            if merged.empty:
                processed += len(chunk_codes)
                continue
            merged = merged.sort_values(["ts_code", "trade_date"])

            # Process each stock in this chunk
            chunk_results = []
            chunk_stocks_in_data = 0
            for ts_code, group in merged.groupby("ts_code"):
                group = group.sort_values("trade_date")
                adj_vals = group["adj_factor"]
                if len(adj_vals) == 0 or adj_vals.iloc[-1] == 0:
                    continue

                group = group.copy()
                ratio = group["adj_factor"].to_numpy(dtype=float) / float(adj_vals.iloc[-1])
                group["adj_open"] = group["open"].to_numpy(dtype=float) * ratio
                group["adj_high"] = group["high"].to_numpy(dtype=float) * ratio
                group["adj_low"] = group["low"].to_numpy(dtype=float) * ratio
                group["adj_close"] = group["close"].to_numpy(dtype=float) * ratio

                indicators = compute_indicators(group)
                if not is_full and trade_days:
                    indicators = indicators[indicators["trade_date"].isin(trade_days)]

                if not indicators.empty and not indicators.iloc[:, 2:].isna().all(axis=1).all():
                    chunk_results.append(indicators)
                    total_saved += len(indicators)

                chunk_stocks_in_data += 1

            processed += len(chunk_codes)

            # Save chunk results immediately and free memory
            if chunk_results:
                chunk_df = pd.concat(chunk_results, ignore_index=True)
                if is_full and is_first_chunk:
                    self.store.save("tech_indicator", chunk_df, mode="replace")
                    is_first_chunk = False
                else:
                    self.store.save("tech_indicator", chunk_df, mode="append")

            # Explicitly free per-chunk DataFrames
            del daily, adj, merged, chunk_results
            if 'chunk_df' in locals():
                del chunk_df

            # Progress: report at chunk granularity
            pct = processed * 100 // total_stocks
            print(f"  [tech_indicator] {processed}/{total_stocks} ({pct}%)  "
                  f"累计={total_saved:,}行", flush=True)

        if total_saved > 0:
            if not is_full:
                removed = self.store.deduplicate("tech_indicator", ["ts_code", "trade_date"])
                if removed > 0:
                    print(f"  [tech_indicator] 去重删除 {removed} 行", flush=True)
            print(f"  [tech_indicator] 完成，{total_saved:,} 行", flush=True)
        else:
            print("  [tech_indicator] 无新数据", flush=True)

        return SyncResult(table="tech_indicator", mode=mode, rows=total_saved, status="success")
