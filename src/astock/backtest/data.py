from dataclasses import dataclass

import pandas as pd

from astock.data.store.db import DataStore
from astock.strategy.factors import adjusted_prices


@dataclass
class BacktestDataLoader:
    store: DataStore

    def load(self, start_date: str, end_date: str) -> dict[str, pd.DataFrame]:
        market = {
            "stock_basic": self._load_table("stock_basic"),
            "trade_cal": self._load_table("trade_cal", "cal_date", start_date, end_date),
            "daily": self._load_table("daily", "trade_date", start_date, end_date),
            "adj_factor": self._load_table("adj_factor", "trade_date", start_date, end_date),
            "daily_basic": self._load_table("daily_basic", "trade_date", start_date, end_date),
            "suspend_d": self._load_table("suspend_d", "trade_date", start_date, end_date),
            "tech_indicator": self._load_table("tech_indicator", "trade_date", start_date, end_date),
        }
        if not market["daily"].empty and not market["adj_factor"].empty:
            market["daily"] = adjusted_prices(market["daily"], market["adj_factor"])
        return market

    def _load_table(
        self,
        table: str,
        date_col: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        if not self.store.table_exists(table):
            return pd.DataFrame()
        table_dir = self.store.data_dir / table
        parquet_glob = str(table_dir / "*.parquet")
        query = f"SELECT * FROM read_parquet('{parquet_glob}', union_by_name=true)"
        params: list[str] = []
        if date_col and start_date and end_date:
            query += f" WHERE {date_col} >= ? AND {date_col} <= ?"
            params.extend([start_date, end_date])
        query += f" ORDER BY {date_col}, ts_code" if date_col and table != "trade_cal" else ""
        if date_col and table == "trade_cal":
            query += " ORDER BY cal_date, exchange"
        return self.store._conn.execute(query, params).df()

