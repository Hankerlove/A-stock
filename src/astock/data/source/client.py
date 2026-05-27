import time

import pandas as pd
import tushare as ts

from astock.core.exceptions import APIError


class TushareClient:
    """Client for fetching data from Tushare API with retry logic."""

    def __init__(self, token: str):
        self._pro = ts.pro_api(token)

    def _retry(self, func, *args, max_retries: int = 3, delay: int = 5, **kwargs):
        """Call func with retry and exponential backoff."""
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
