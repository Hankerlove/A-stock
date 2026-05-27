class AStockError(Exception):
    """Base exception for all A-Stock system errors."""
    pass


class ConfigError(AStockError):
    """Configuration error: missing keys, invalid paths, etc."""
    pass


class APIError(AStockError):
    """Tushare API error with status code and response body."""

    def __init__(self, message: str, status_code: int | None = None, response: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class StoreError(AStockError):
    """Storage layer error: IO failure, data corruption."""
    pass


class SyncError(AStockError):
    """Sync logic error: dependency breakage, data inconsistency."""
    pass
