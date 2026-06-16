import os

import pandas as pd
from typer.testing import CliRunner

from astock.cli.main import app
from astock.data.store.db import DataStore


runner = CliRunner()


def test_chart_kline_writes_html_for_stock_code(tmp_path):
    data_dir = tmp_path / "data"
    store = DataStore(db_path=str(data_dir / "astock.duckdb"), data_dir=str(data_dir))
    store.save(
        "stock_basic",
        pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "symbol": ["000001"],
                "name": ["平安银行"],
            }
        ),
        mode="append",
    )
    store.save(
        "daily",
        pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ"],
                "trade_date": ["20240102", "20240103"],
                "open": [10.0, 10.3],
                "high": [10.5, 10.8],
                "low": [9.9, 10.1],
                "close": [10.3, 10.6],
                "vol": [100000.0, 120000.0],
                "amount": [103000.0, 127200.0],
            }
        ),
        mode="append",
    )
    output = tmp_path / "charts" / "pingan.html"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
tushare:
  token: "dummy"
storage:
  data_dir: "{data_dir}"
  db_path: "{data_dir / "astock.duckdb"}"
sync:
  batch_size: 5000
  retry: 3
  retry_delay: 5
log:
  level: "INFO"
  file: "{tmp_path / "astock.log"}"
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        [
            "chart",
            "kline",
            "000001",
            "--config",
            str(config_path),
            "--start",
            "20240102",
            "--end",
            "20240103",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert output.exists()
    assert "已生成 K 线图" in result.output
    assert "000001.SZ" in output.read_text(encoding="utf-8")


def test_chart_kline_defaults_to_recent_two_year_window(tmp_path, monkeypatch):
    import astock.cli.chart_cmd as chart_cmd

    data_dir = tmp_path / "data"
    store = DataStore(db_path=str(data_dir / "astock.duckdb"), data_dir=str(data_dir))
    store.save(
        "stock_basic",
        pd.DataFrame(
            {
                "ts_code": ["000001.SZ"],
                "symbol": ["000001"],
                "name": ["平安银行"],
            }
        ),
        mode="append",
    )
    store.save(
        "daily",
        pd.DataFrame(
            {
                "ts_code": ["000001.SZ", "000001.SZ", "000001.SZ"],
                "trade_date": ["20240102", "20240103", "20240104"],
                "open": [10.0, 10.3, 10.5],
                "high": [10.5, 10.8, 11.2],
                "low": [9.9, 10.1, 10.2],
                "close": [10.3, 10.6, 11.0],
                "vol": [100000.0, 120000.0, 130000.0],
            }
        ),
        mode="append",
    )
    output = tmp_path / "charts" / "default-window.html"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
tushare:
  token: "dummy"
storage:
  data_dir: "{data_dir}"
  db_path: "{data_dir / "astock.duckdb"}"
sync:
  batch_size: 5000
  retry: 3
  retry_delay: 5
log:
  level: "INFO"
  file: "{tmp_path / "astock.log"}"
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        chart_cmd,
        "default_kline_date_range",
        lambda store: ("20240103", "20240104"),
        raising=False,
    )

    result = runner.invoke(
        app,
        [
            "chart",
            "kline",
            "000001",
            "--config",
            str(config_path),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    assert "数据: 20240103 - 20240104，共 2 条" in result.output
    assert '"trade_date":"20240102"' not in output.read_text(encoding="utf-8")
