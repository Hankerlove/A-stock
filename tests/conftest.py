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
