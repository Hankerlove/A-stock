from pathlib import Path

import duckdb
import pandas as pd

from tools.verify_data import verify


def _write_table(tmp_path: Path, table: str, frame: pd.DataFrame) -> None:
    table_dir = tmp_path / "data" / table
    table_dir.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(table_dir / "part.parquet", index=False)


def _base_tables(tmp_path: Path, daily: pd.DataFrame, tech_indicator: pd.DataFrame | None = None) -> None:
    dates = sorted(daily["trade_date"].unique().tolist())
    codes = sorted(daily["ts_code"].unique().tolist())

    _write_table(
        tmp_path,
        "stock_basic",
        pd.DataFrame(
            {
                "ts_code": codes,
                "symbol": [c.split(".")[0] for c in codes],
                "name": codes,
                "list_status": ["L"] * len(codes),
                "list_date": ["19900101"] * len(codes),
                "delist_date": [None] * len(codes),
            }
        ),
    )
    _write_table(
        tmp_path,
        "trade_cal",
        pd.DataFrame(
            {
                "exchange": ["SSE"] * len(dates),
                "cal_date": dates,
                "is_open": [1] * len(dates),
                "pretrade_date": [None] * len(dates),
            }
        ),
    )
    _write_table(
        tmp_path,
        "daily",
        daily,
    )
    _write_table(
        tmp_path,
        "adj_factor",
        pd.DataFrame(
            [
                {"ts_code": code, "trade_date": date, "adj_factor": 1.0}
                for date in dates
                for code in codes
            ]
        ),
    )
    _write_table(
        tmp_path,
        "daily_basic",
        pd.DataFrame(
            [
                {"ts_code": code, "trade_date": date, "turnover_rate": 1.0, "pb": 1.0, "pe_ttm": 10.0}
                for date in dates
                for code in codes
            ]
        ),
    )
    _write_table(
        tmp_path,
        "suspend_d",
        pd.DataFrame(
            {
                "ts_code": [codes[0]],
                "trade_date": [dates[-1]],
                "suspend_type": ["S"],
                "suspend_timing": [None],
            }
        ),
    )
    if tech_indicator is None:
        tech_indicator = pd.DataFrame(
            [
                {
                    "ts_code": code,
                    "trade_date": date,
                    "dif": 0.1,
                    "dea": 0.1,
                    "macd_hist": 0.0,
                    "k": 50.0,
                    "d": 50.0,
                    "j": 50.0,
                    "rsi6": 50.0,
                    "rsi14": 50.0,
                    "rsi24": 50.0,
                    "ma5": 10.0,
                    "ma10": 10.0,
                    "ma20": 10.0,
                    "ma60": 10.0,
                    "boll_upper": 11.0,
                    "boll_mid": 10.0,
                    "boll_lower": 9.0,
                    "atr14": 1.0,
                }
                for date in dates
                for code in codes
            ]
        )
    _write_table(tmp_path, "tech_indicator", tech_indicator)


def test_verify_ignores_pre_2000_price_quality_and_reports_usable_date(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    daily = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "19991230",
                "open": 10.0,
                "high": 9.0,
                "low": 8.0,
                "close": 8.5,
                "pre_close": 10.0,
                "change": -1.5,
                "pct_chg": -15.0,
                "vol": 100.0,
                "amount": None,
            },
            {
                "ts_code": "000001.SZ",
                "trade_date": "20240102",
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "pre_close": 10.0,
                "change": 0.2,
                "pct_chg": 2.0,
                "vol": 100.0,
                "amount": 1000.0,
            },
        ]
    )
    _base_tables(tmp_path, daily)

    assert verify(duckdb.connect(":memory:")) is True
    output = capsys.readouterr().out
    assert "完整可用日期: 20240102" in output
    assert "ERROR: 0" in output
    assert "daily 核心字段空值" not in output
    assert "daily OHLC 异常" not in output


def test_verify_flags_post_2000_core_quality_errors(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    daily = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20240102",
                "open": 10.0,
                "high": 9.5,
                "low": 9.0,
                "close": 9.2,
                "pre_close": 10.0,
                "change": -0.8,
                "pct_chg": -8.0,
                "vol": 100.0,
                "amount": None,
            }
        ]
    )
    _base_tables(tmp_path, daily)

    assert verify(duckdb.connect(":memory:")) is False
    output = capsys.readouterr().out
    assert "ERROR" in output
    assert "daily 核心字段空值" in output
    assert "daily OHLC 异常" in output


def test_verify_reports_key_level_tech_gaps_and_pct_anomalies_as_warnings(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    daily = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20240102",
                "open": 10.0,
                "high": 25.0,
                "low": 9.8,
                "close": 24.0,
                "pre_close": 10.0,
                "change": 14.0,
                "pct_chg": 140.0,
                "vol": 100.0,
                "amount": 1000.0,
            },
            {
                "ts_code": "000002.SZ",
                "trade_date": "20240102",
                "open": 10.0,
                "high": 10.5,
                "low": 9.8,
                "close": 10.2,
                "pre_close": 10.0,
                "change": 0.2,
                "pct_chg": 2.0,
                "vol": 100.0,
                "amount": 1000.0,
            },
        ]
    )
    tech_indicator = pd.DataFrame(
        [
            {
                "ts_code": "000001.SZ",
                "trade_date": "20240102",
                "dif": None,
                "dea": None,
                "macd_hist": None,
                "k": None,
                "d": None,
                "j": None,
                "rsi6": None,
                "rsi14": None,
                "rsi24": None,
                "ma5": None,
                "ma10": None,
                "ma20": None,
                "ma60": None,
                "boll_upper": None,
                "boll_mid": None,
                "boll_lower": None,
                "atr14": None,
            }
        ]
    )
    _base_tables(tmp_path, daily, tech_indicator=tech_indicator)

    assert verify(duckdb.connect(":memory:")) is True
    output = capsys.readouterr().out
    assert "WARN" in output
    assert "daily -> tech_indicator 缺失键" in output
    assert "tech_indicator 核心指标全空" in output
    assert "异常涨跌幅" in output
