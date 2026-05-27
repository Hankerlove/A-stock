import pytest
from astock.core.exceptions import (
    AStockError,
    ConfigError,
    APIError,
    StoreError,
    SyncError,
)


class TestExceptionHierarchy:
    def test_base_exception(self):
        with pytest.raises(AStockError):
            raise AStockError("base error")

    def test_config_error_is_astock_error(self):
        err = ConfigError("missing token")
        assert isinstance(err, AStockError)
        assert str(err) == "missing token"

    def test_api_error_includes_details(self):
        err = APIError("request failed", status_code=429, response="rate limit")
        assert err.status_code == 429
        assert err.response == "rate limit"
        assert isinstance(err, AStockError)

    def test_store_error_is_astock_error(self):
        err = StoreError("write failed")
        assert isinstance(err, AStockError)

    def test_sync_error_is_astock_error(self):
        err = SyncError("dependency broken")
        assert isinstance(err, AStockError)
