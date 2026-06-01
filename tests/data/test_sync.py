from unittest.mock import MagicMock, patch
import pandas as pd
import pytest
from astock.data.sync.manager import SyncManager, SyncResult, DEPENDENCIES


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.fetch_stock_basic.return_value = pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "symbol": ["000001"],
        "name": ["平安银行"],
        "list_status": ["L"],
        "list_date": ["19910403"],
        "delist_date": [None],
    })
    client.fetch_trade_cal.return_value = pd.DataFrame({
        "exchange": ["SSE"],
        "cal_date": ["20240102"],
        "is_open": ["1"],
        "pretrade_date": ["20240101"],
    })
    client.fetch_daily.return_value = pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "trade_date": ["20240102"],
        "open": [10.0], "high": [10.5], "low": [9.9],
        "close": [10.3], "pre_close": [10.1],
        "change": [0.2], "pct_chg": [1.98],
        "vol": [100000.0], "amount": [103000.0],
    })
    client.fetch_adj_factor.return_value = pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "trade_date": ["20240102"],
        "adj_factor": [1.0],
    })
    client.fetch_daily_basic.return_value = pd.DataFrame({
        "ts_code": ["000001.SZ"],
        "trade_date": ["20240102"],
        "pe": [5.5],
    })
    client.fetch_suspend_d.return_value = pd.DataFrame()
    return client


@pytest.fixture
def sync_manager(mock_client, temp_data_dir):
    from astock.data.store.db import DataStore
    from astock.core.config import SyncConfig
    import os

    db_path = os.path.join(temp_data_dir, "test.duckdb")
    store = DataStore(db_path=db_path, data_dir=temp_data_dir)
    return SyncManager(
        client=mock_client,
        store=store,
        config=SyncConfig(batch_size=5000, retry=3, retry_delay=1),
    )


class TestSyncManager:
    def test_sync_stock_basic(self, sync_manager):
        result = sync_manager._sync_stock_basic("full")
        assert result.status == "success"
        assert result.table == "stock_basic"
        assert result.rows == 1

    def test_sync_trade_cal_full(self, sync_manager):
        result = sync_manager._sync_trade_cal("full")
        assert result.status == "success"

    def test_sync_trade_cal_inc_no_existing(self, sync_manager):
        result = sync_manager._sync_trade_cal("inc")
        assert result.status == "success"

    def test_sync_daily(self, sync_manager):
        sync_manager._sync_stock_basic("full")
        sync_manager._sync_trade_cal("full")
        result = sync_manager._sync_daily("full")
        assert result.status == "success"

    def test_sync_adj_factor(self, sync_manager):
        sync_manager._sync_stock_basic("full")
        sync_manager._sync_trade_cal("full")
        sync_manager._sync_daily("full")
        result = sync_manager._sync_adj_factor("full")
        assert result.status == "success"

    def test_sync_daily_basic(self, sync_manager):
        sync_manager._sync_stock_basic("full")
        sync_manager._sync_trade_cal("full")
        sync_manager._sync_daily("full")
        result = sync_manager._sync_daily_basic("full")
        assert result.status == "success"

    def test_sync_suspend_d(self, sync_manager):
        sync_manager._sync_stock_basic("full")
        result = sync_manager._sync_suspend_d("full")
        assert result.status == "success"

    def test_sync_all_respects_order(self, sync_manager):
        results = sync_manager.sync_all()
        assert len(results) == 7
        tables = [r.table for r in results]
        assert tables == [
            "stock_basic", "trade_cal", "daily",
            "adj_factor", "daily_basic", "suspend_d",
            "tech_indicator",
        ]

    def test_sync_table_with_dependency(self, sync_manager):
        """Syncing daily should cascade to check stock_basic and trade_cal."""
        result = sync_manager.sync_table("daily", mode="full")
        assert result.status == "success"

    def test_failed_sync_returns_error_result(self, sync_manager):
        sync_manager.client.fetch_stock_basic.side_effect = Exception("boom")
        result = sync_manager._sync_stock_basic("full")
        assert result.status == "failed"
        assert "boom" in result.error

    def test_dependency_graph(self):
        assert DEPENDENCIES["stock_basic"] == []
        assert DEPENDENCIES["trade_cal"] == []
        assert DEPENDENCIES["daily"] == ["stock_basic", "trade_cal"]
        assert DEPENDENCIES["adj_factor"] == ["daily"]
        assert DEPENDENCIES["daily_basic"] == ["daily"]
        assert DEPENDENCIES["suspend_d"] == ["stock_basic"]

    def test_resolve_dependencies_returns_stale_deps(self, sync_manager):
        sync_manager._sync_stock_basic("full")
        sync_manager._sync_trade_cal("full")
        deps = sync_manager._resolve_dependencies("daily")
        assert isinstance(deps, list)

    def test_sync_result_dataclass(self):
        result = SyncResult(table="daily", mode="inc", rows=100, status="success")
        assert result.table == "daily"
        assert result.rows == 100

        result2 = SyncResult(table="daily", mode="full", rows=0, status="failed", error="timeout")
        assert result2.error == "timeout"
