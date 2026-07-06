from dataclasses import dataclass

import pandas as pd

from astock.data.store.db import DataStore
from astock.strategy.factors import adjusted_prices

# 各表回测实际需要的列，按需加载以减少内存占用。
# tech_indicator 在回测中未被策略或引擎使用，直接跳过。
_COLUMNS = {
    "stock_basic": ["ts_code", "list_status", "list_date", "delist_date"],
    "trade_cal": ["cal_date", "is_open", "exchange"],
    "daily": [
        "ts_code", "trade_date", "open", "high", "low", "close",
        "pre_close", "vol", "amount", "pct_chg",
    ],
    "adj_factor": ["ts_code", "trade_date", "adj_factor"],
    "daily_basic": [
        "ts_code", "trade_date", "dv_ttm", "dv_ratio", "pb", "pe",
        "pe_ttm", "total_mv", "turnover_rate",
    ],
    "suspend_d": ["ts_code", "trade_date", "suspend_type"],
}


@dataclass
class BacktestDataLoader:
    store: DataStore

    def load(self, start_date: str, end_date: str) -> dict[str, pd.DataFrame]:
        market: dict[str, pd.DataFrame] = {}
        for table, columns in _COLUMNS.items():
            date_col = _date_col(table)
            market[table] = self._load_table(table, columns, date_col, start_date, end_date)
        if not market["daily"].empty and not market["adj_factor"].empty:
            market["daily"] = adjusted_prices(market["daily"], market["adj_factor"])
        return market

    def _load_table(
        self,
        table: str,
        columns: list[str],
        date_col: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        if not self.store.table_exists(table):
            return pd.DataFrame()
        table_dir = self.store.data_dir / table
        parquet_glob = str(table_dir / "*.parquet")
        col_list = ", ".join(columns)
        query = f"SELECT {col_list} FROM read_parquet('{parquet_glob}', union_by_name=true)"
        params: list[str] = []
        if date_col and start_date and end_date:
            query += f" WHERE {date_col} >= ? AND {date_col} <= ?"
            params.extend([start_date, end_date])
        if date_col and table != "trade_cal":
            query += " ORDER BY trade_date, ts_code"
        elif date_col and table == "trade_cal":
            query += " ORDER BY cal_date, exchange"
        return self.store._conn.execute(query, params).df()


def _date_col(table: str) -> str | None:
    """返回表的日期列名，无日期列的表返回 None。"""
    date_cols = {
        "stock_basic": None,
        "trade_cal": "cal_date",
        "daily": "trade_date",
        "adj_factor": "trade_date",
        "daily_basic": "trade_date",
        "suspend_d": "trade_date",
    }
    return date_cols.get(table)

