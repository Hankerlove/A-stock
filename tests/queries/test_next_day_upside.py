from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def load_query_module():
    module_path = Path(__file__).resolve().parents[2] / "tools" / "queries" / "next_day_upside.py"
    spec = importlib.util.spec_from_file_location("next_day_upside", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write_table(data_dir: Path, table: str, rows: list[dict]) -> None:
    table_dir = data_dir / table
    table_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(table_dir / f"{table}.parquet", index=False)


def make_daily_rows(ts_code: str, start_close: float, weak_trend: bool = False) -> list[dict]:
    rows = []
    for i, date in enumerate(pd.bdate_range("2024-01-01", periods=60).strftime("%Y%m%d")):
        if weak_trend:
            close = start_close - i * 0.03
        elif i < 55:
            close = start_close + i * 0.07
        elif i == 55:
            close = 13.65
        elif i == 56:
            close = 13.20
        elif i == 57:
            close = 12.95
        elif i == 58:
            close = 12.90
        else:
            close = 13.25

        if ts_code == "000001.SZ" and i == 59:
            open_price = 12.92
            vol = 2000.0
        else:
            open_price = close - 0.05
            vol = 1200.0

        rows.append({
            "ts_code": ts_code,
            "trade_date": date,
            "open": open_price,
            "high": close + 0.20,
            "low": close - 0.20,
            "close": close,
            "pre_close": rows[-1]["close"] if rows else close - 0.05,
            "change": close - (rows[-1]["close"] if rows else close - 0.05),
            "pct_chg": 2.71 if ts_code == "000001.SZ" and i == 59 else 0.4,
            "vol": vol,
            "amount": vol * close,
        })
    return rows


def test_find_candidates_prefers_trend_pullback_rebound(tmp_path):
    data_dir = tmp_path
    dates = list(pd.bdate_range("2024-01-01", periods=60).strftime("%Y%m%d"))
    prev_date, latest_date = dates[-2], dates[-1]

    write_table(
        data_dir,
        "daily",
        make_daily_rows("000001.SZ", 10.0) + make_daily_rows("000002.SZ", 15.0, weak_trend=True),
    )
    write_table(
        data_dir,
        "stock_basic",
        [
            {"ts_code": "000001.SZ", "symbol": "000001", "name": "平安银行", "list_status": "L"},
            {"ts_code": "000002.SZ", "symbol": "000002", "name": "万科A", "list_status": "L"},
        ],
    )
    write_table(
        data_dir,
        "daily_basic",
        [
            {"ts_code": "000001.SZ", "trade_date": latest_date, "turnover_rate": 3.2, "volume_ratio": 1.35},
            {"ts_code": "000002.SZ", "trade_date": latest_date, "turnover_rate": 2.4, "volume_ratio": 0.85},
        ],
    )
    write_table(
        data_dir,
        "tech_indicator",
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": prev_date,
                "dif": 0.18,
                "dea": 0.12,
                "macd_hist": 0.02,
                "rsi6": 47.0,
                "rsi14": 51.0,
                "ma5": 13.00,
                "ma10": 13.10,
                "ma20": 12.82,
                "ma60": 11.90,
            },
            {
                "ts_code": "000001.SZ",
                "trade_date": latest_date,
                "dif": 0.24,
                "dea": 0.14,
                "macd_hist": 0.05,
                "rsi6": 58.0,
                "rsi14": 52.0,
                "ma5": 13.05,
                "ma10": 13.06,
                "ma20": 12.84,
                "ma60": 11.95,
            },
            {
                "ts_code": "000002.SZ",
                "trade_date": prev_date,
                "dif": -0.15,
                "dea": -0.05,
                "macd_hist": -0.10,
                "rsi6": 38.0,
                "rsi14": 42.0,
                "ma5": 13.30,
                "ma10": 13.50,
                "ma20": 13.80,
                "ma60": 14.20,
            },
            {
                "ts_code": "000002.SZ",
                "trade_date": latest_date,
                "dif": -0.18,
                "dea": -0.06,
                "macd_hist": -0.12,
                "rsi6": 35.0,
                "rsi14": 40.0,
                "ma5": 13.20,
                "ma10": 13.40,
                "ma20": 13.70,
                "ma60": 14.15,
            },
        ],
    )

    module = load_query_module()

    df = module.find_candidates(data_dir=data_dir, min_score=70, max_rows=10)

    assert df["ts_code"].tolist() == ["000001.SZ"]
    assert df.iloc[0]["signal_score"] >= 70
    assert df.iloc[0]["upside_room_pct"] > 0
