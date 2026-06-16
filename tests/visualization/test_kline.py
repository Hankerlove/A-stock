import os
from datetime import date

import pandas as pd
import pytest

from astock.data.store.db import DataStore


def _store_with_kline_data(temp_data_dir):
    store = DataStore(
        db_path=os.path.join(temp_data_dir, "test.duckdb"),
        data_dir=temp_data_dir,
    )
    stock_basic = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "600000.SH"],
            "symbol": ["000001", "600000"],
            "name": ["平安银行", "浦发银行"],
        }
    )
    daily = pd.DataFrame(
        {
            "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ", "600000.SH"],
            "trade_date": ["20240102", "20240103", "20240104", "20240102"],
            "open": [10.0, 10.3, 10.5, 8.0],
            "high": [10.5, 10.8, 11.2, 8.4],
            "low": [9.9, 10.1, 10.2, 7.9],
            "close": [10.3, 10.6, 11.0, 8.2],
            "vol": [100000.0, 120000.0, 130000.0, 90000.0],
            "amount": [103000.0, 127200.0, 143000.0, 73800.0],
        }
    )
    store.save("stock_basic", stock_basic, mode="append")
    store.save("daily", daily, mode="append")
    return store


def test_default_kline_date_range_uses_latest_open_trade_day(temp_data_dir):
    from astock.visualization.kline import default_kline_date_range

    store = _store_with_kline_data(temp_data_dir)
    store.save(
        "trade_cal",
        pd.DataFrame(
                {
                    "exchange": ["SSE", "SSE", "SSE"],
                    "cal_date": ["20260613", "20260614", "20260615"],
                    "is_open": [0, 0, 1],
                }
            ),
        mode="append",
    )

    start, end = default_kline_date_range(store, today=date(2026, 6, 16))

    assert start == "20240615"
    assert end == "20260615"


def test_load_kline_data_resolves_stock_name(temp_data_dir):
    from astock.visualization.kline import load_kline_data

    store = _store_with_kline_data(temp_data_dir)

    identity, frame = load_kline_data(store, "平安银行", start="20240103")

    assert identity.ts_code == "000001.SZ"
    assert identity.name == "平安银行"
    assert frame["trade_date"].tolist() == ["20240103", "20240104"]
    assert frame["high"].max() == pytest.approx(11.2)


def test_render_kline_html_contains_interactive_controls(temp_data_dir):
    from astock.visualization.kline import load_kline_data, render_kline_html

    store = _store_with_kline_data(temp_data_dir)
    identity, frame = load_kline_data(store, "000001")

    html = render_kline_html(identity, frame)

    assert "平安银行 (000001.SZ)" in html
    assert "canvas" in html
    assert "visibleHigh" in html
    assert "dragging" in html
    assert "drawExtremaAnnotations" in html
    assert "visibleHighPoint" in html
    assert "visibleLowPoint" in html
    assert '"trade_date":"20240104"' in html
