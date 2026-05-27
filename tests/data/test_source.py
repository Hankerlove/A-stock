from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from astock.data.source.client import TushareClient
from astock.core.exceptions import APIError


@pytest.fixture
def mock_pro():
    with patch("tushare.pro_api") as mock:
        yield mock


class TestTushareClient:
    def test_fetch_stock_basic(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.stock_basic.return_value = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "name": ["平安银行"],
        })

        client = TushareClient(token="test-token")
        df = client.fetch_stock_basic()

        assert len(df) == 1
        mock_instance.stock_basic.assert_called_once()

    def test_fetch_trade_cal(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.trade_cal.return_value = pd.DataFrame({
            "exchange": ["SSE"],
            "cal_date": ["20240101"],
            "is_open": ["0"],
        })

        client = TushareClient(token="test-token")
        df = client.fetch_trade_cal(exchange="SSE", start_date="20240101", end_date="20240105")

        assert len(df) == 1
        mock_instance.trade_cal.assert_called_once_with(
            exchange="SSE", start_date="20240101", end_date="20240105"
        )

    def test_fetch_daily(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.daily.return_value = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": ["20240102"],
            "close": [10.5],
        })

        client = TushareClient(token="test-token")
        df = client.fetch_daily(ts_code="000001.SZ", trade_date="20240102")

        assert len(df) == 1

    def test_fetch_adj_factor(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.adj_factor.return_value = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": ["20240102"],
            "adj_factor": [1.2],
        })

        client = TushareClient(token="test-token")
        df = client.fetch_adj_factor(trade_date="20240102")

        assert len(df) == 1

    def test_fetch_daily_basic(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.daily_basic.return_value = pd.DataFrame({
            "ts_code": ["000001.SZ"],
            "trade_date": ["20240102"],
            "pe": [5.5],
        })

        client = TushareClient(token="test-token")
        df = client.fetch_daily_basic(trade_date="20240102")

        assert len(df) == 1

    def test_fetch_suspend_d(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.suspend_d.return_value = pd.DataFrame({
            "ts_code": ["000003.SZ"],
            "trade_date": ["20240102"],
            "suspend_type": ["S"],
        })

        client = TushareClient(token="test-token")
        df = client.fetch_suspend_d(trade_date="20240102", suspend_type="S")

        assert len(df) == 1

    def test_retry_on_failure(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("connection error")
            return pd.DataFrame({"ts_code": ["000001.SZ"]})

        mock_instance.stock_basic.side_effect = side_effect

        client = TushareClient(token="test-token")
        df = client.fetch_stock_basic()

        assert len(df) == 1
        assert call_count[0] == 3

    def test_retry_exhausted_raises_api_error(self, mock_pro):
        mock_instance = MagicMock()
        mock_pro.return_value = mock_instance
        mock_instance.stock_basic.side_effect = Exception("connection error")

        client = TushareClient(token="test-token")
        with pytest.raises(APIError, match="3 retries"):
            client.fetch_stock_basic()
