import os

import pandas as pd
from typer.testing import CliRunner

from astock.cli.main import app
from astock.data.store.db import DataStore


runner = CliRunner()


def test_strategy_list_command_shows_builtin_strategies():
    result = runner.invoke(app, ["strategy", "list"])

    assert result.exit_code == 0
    assert "dividend-low-vol" in result.output
    assert "value-low-vol" in result.output


def test_strategy_explain_command_shows_parameters():
    result = runner.invoke(app, ["strategy", "explain", "dividend-low-vol"])

    assert result.exit_code == 0
    assert "top_n" in result.output
    assert "lookback_days" in result.output
    assert "持仓股票数量" in result.output


def test_strategy_explain_command_shows_new_strategy_parameter_descriptions():
    result = runner.invoke(app, ["strategy", "explain", "momentum-reversal"])

    assert result.exit_code == 0
    assert "momentum_window" in result.output
    assert "中期动量窗口" in result.output
    assert "reversal_window" in result.output
    assert "短期反转窗口" in result.output


def test_strategy_signals_help_exposes_weight_parameters():
    result = runner.invoke(app, ["strategy", "signals", "--help"])

    assert result.exit_code == 0
    assert "--momentum-weight" in result.output
    assert "--price-breakout-weight" in result.output


def test_strategy_signals_outputs_stock_names(temp_data_dir, tmp_path):
    store = DataStore(
        db_path=os.path.join(temp_data_dir, "test.duckdb"),
        data_dir=temp_data_dir,
    )
    store.save("stock_basic", pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "symbol": ["000001"],
        "name": ["平安银行"],
        "list_status": ["L"],
        "list_date": ["19910403"],
        "delist_date": [None],
    }), mode="append")
    store.save("daily", pd.DataFrame({
        "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ"],
        "trade_date": ["20240102", "20240103", "20240104"],
        "open": [10.0, 10.2, 10.4],
        "high": [10.5, 10.6, 10.8],
        "low": [9.8, 10.0, 10.2],
        "close": [10.1, 10.3, 10.5],
        "pre_close": [10.0, 10.1, 10.3],
        "pct_chg": [1.0, 1.98, 1.94],
        "vol": [100000.0, 110000.0, 120000.0],
        "amount": [1000.0, 1100.0, 1200.0],
    }), mode="append")
    store.save("adj_factor", pd.DataFrame({
        "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ"],
        "trade_date": ["20240102", "20240103", "20240104"],
        "adj_factor": [1.0, 1.0, 1.0],
    }), mode="append")
    store.save("daily_basic", pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "trade_date": ["20240104"],
        "dv_ttm": [2.5],
        "dv_ratio": [2.0],
        "pb": [0.8],
        "pe": [8.0],
        "pe_ttm": [7.5],
        "total_mv": [1000000.0],
        "turnover_rate": [1.0],
    }), mode="append")
    store.save("trade_cal", pd.DataFrame({
        "exchange": ["SSE", "SSE", "SSE"],
        "cal_date": ["20240102", "20240103", "20240104"],
        "is_open": [1, 1, 1],
    }), mode="append")
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""
tushare:
  token: dummy
storage:
  data_dir: {temp_data_dir}
  db_path: {os.path.join(temp_data_dir, 'test.duckdb')}
sync: {{}}
log: {{}}
""".strip()
    )

    result = runner.invoke(app, [
        "strategy", "signals",
        "--strategy", "dividend-low-vol",
        "--date", "20240104",
        "--top-n", "1",
        "--lookback-days", "2",
        "--min-amount", "0",
        "--config", str(config),
    ])

    assert result.exit_code == 0
    assert "代码" in result.output
    assert "名称" in result.output
    assert "权重" in result.output
    assert "000001.SZ" in result.output
    assert "平安银行" in result.output


def test_backtest_run_requires_dates():
    result = runner.invoke(app, ["backtest", "run", "--strategy", "dividend-low-vol"])

    assert result.exit_code != 0
    assert "start" in result.output or "Missing" in result.output
