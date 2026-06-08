import os

import pandas as pd

from astock.backtest.data import BacktestDataLoader
from astock.data.store.db import DataStore


def test_loader_reads_date_range_and_adds_adjusted_prices(temp_data_dir):
    store = DataStore(
        db_path=os.path.join(temp_data_dir, "test.duckdb"),
        data_dir=temp_data_dir,
    )
    store.save("daily", pd.DataFrame({
        "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ"],
        "trade_date": ["20240102", "20240103", "20240104"],
        "open": [10.0, 12.0, 14.0],
        "high": [10.0, 12.0, 14.0],
        "low": [10.0, 12.0, 14.0],
        "close": [10.0, 12.0, 14.0],
        "pre_close": [10.0, 10.0, 12.0],
        "pct_chg": [0.0, 20.0, 16.67],
        "vol": [100.0, 100.0, 100.0],
        "amount": [1000.0, 1200.0, 1400.0],
    }), mode="append")
    store.save("adj_factor", pd.DataFrame({
        "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ"],
        "trade_date": ["20240102", "20240103", "20240104"],
        "adj_factor": [1.0, 2.0, 2.0],
    }), mode="append")
    store.save("trade_cal", pd.DataFrame({
        "exchange": ["SSE", "SSE", "SSE"],
        "cal_date": ["20240102", "20240103", "20240104"],
        "is_open": [1, 1, 1],
    }), mode="append")

    market = BacktestDataLoader(store).load("20240103", "20240104")

    assert market["daily"]["trade_date"].tolist() == ["20240103", "20240104"]
    assert "adj_open" in market["daily"].columns
    assert market["daily"].iloc[0]["adj_close"] == 12.0
    assert market["trade_cal"]["cal_date"].tolist() == ["20240103", "20240104"]


def test_loader_returns_empty_optional_tables(temp_data_dir):
    store = DataStore(
        db_path=os.path.join(temp_data_dir, "test.duckdb"),
        data_dir=temp_data_dir,
    )
    store.save("daily", pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "trade_date": ["20240102"],
        "open": [10.0],
        "high": [10.0],
        "low": [10.0],
        "close": [10.0],
        "pre_close": [10.0],
        "pct_chg": [0.0],
        "vol": [100.0],
        "amount": [1000.0],
    }), mode="append")

    market = BacktestDataLoader(store).load("20240102", "20240102")

    assert market["daily"].shape[0] == 1
    assert market["adj_factor"].empty
    assert market["daily_basic"].empty
    assert market["suspend_d"].empty
