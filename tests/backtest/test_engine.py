import pandas as pd

from astock.backtest import BacktestConfig, BacktestEngine, ExecutionConfig
from astock.strategy.base import StrategySignal


class StaticStrategy:
    name = "static"
    description = "test strategy"

    def __init__(self, weights_by_date: dict[str, dict[str, float]]):
        self.weights_by_date = weights_by_date

    def generate(self, market, trade_date: str) -> StrategySignal:
        weights = pd.Series(self.weights_by_date.get(trade_date, {}), dtype=float, name="weight")
        return StrategySignal(trade_date=trade_date, weights=weights, scores=pd.DataFrame())


def _market(pct_chg: float = 0.0, suspend_trade_date: str | None = None) -> dict[str, pd.DataFrame]:
    dates = ["20240102", "20240103", "20240104", "20240105"]
    daily_rows = []
    for date in dates:
        daily_rows.append({
            "ts_code": "000001.SZ",
            "trade_date": date,
            "open": 10.0,
            "high": 10.5,
            "low": 9.8,
            "close": 10.0,
            "pre_close": 10.0,
            "pct_chg": pct_chg if date == "20240103" else 0.0,
            "vol": 10000.0,
            "amount": 100000.0,
        })
    suspend_rows = []
    if suspend_trade_date:
        suspend_rows.append({
            "ts_code": "000001.SZ",
            "trade_date": suspend_trade_date,
            "suspend_type": "S",
        })
    return {
        "trade_cal": pd.DataFrame({
            "exchange": ["SSE"] * len(dates),
            "cal_date": dates,
            "is_open": [1] * len(dates),
        }),
        "daily": pd.DataFrame(daily_rows),
        "adj_factor": pd.DataFrame({
            "ts_code": ["000001.SZ"] * len(dates),
            "trade_date": dates,
            "adj_factor": [1.0] * len(dates),
        }),
        "suspend_d": pd.DataFrame(suspend_rows),
    }


def _config(**kwargs) -> BacktestConfig:
    execution = kwargs.pop("execution", ExecutionConfig(
        commission_rate=0.0,
        stamp_duty_rate=0.0,
        slippage_rate=0.0,
        min_commission=0.0,
        lot_size=1,
        enforce_suspend=True,
        enforce_limit=True,
    ))
    return BacktestConfig(
        start_date="20240102",
        end_date="20240105",
        initial_cash=10000.0,
        rebalance_frequency="daily",
        execution=execution,
        **kwargs,
    )


def test_backtest_executes_signal_on_next_trade_day():
    strategy = StaticStrategy({"20240102": {"000001.SZ": 1.0}})
    engine = BacktestEngine(_config())

    result = engine.run(strategy, _market())

    first_trade = result.trades.iloc[0]
    assert first_trade["signal_date"] == "20240102"
    assert first_trade["trade_date"] == "20240103"
    assert first_trade["side"] == "buy"
    assert first_trade["shares"] == 1000


def test_transaction_cost_parameters_change_final_equity():
    strategy = StaticStrategy({"20240102": {"000001.SZ": 1.0}})
    low_cost = BacktestEngine(_config()).run(strategy, _market())
    high_cost = BacktestEngine(_config(execution=ExecutionConfig(
        commission_rate=0.01,
        stamp_duty_rate=0.0,
        slippage_rate=0.01,
        min_commission=0.0,
        lot_size=1,
        enforce_suspend=True,
        enforce_limit=True,
    ))).run(strategy, _market())

    assert high_cost.equity_curve.iloc[-1]["equity"] < low_cost.equity_curve.iloc[-1]["equity"]
    assert high_cost.metrics["total_return"] < low_cost.metrics["total_return"]


def test_suspend_blocks_buy_order_when_enabled():
    strategy = StaticStrategy({"20240102": {"000001.SZ": 1.0}})
    engine = BacktestEngine(_config())

    result = engine.run(strategy, _market(suspend_trade_date="20240103"))

    assert result.trades.empty
    assert result.equity_curve.iloc[-1]["cash"] == 10000.0


def test_limit_up_blocks_buy_order_when_enabled():
    strategy = StaticStrategy({"20240102": {"000001.SZ": 1.0}})
    engine = BacktestEngine(_config())

    result = engine.run(strategy, _market(pct_chg=10.0))

    assert result.trades.empty
    assert result.equity_curve.iloc[-1]["cash"] == 10000.0


def test_strategy_empty_signal_keeps_cash():
    strategy = StaticStrategy({})
    engine = BacktestEngine(_config())

    result = engine.run(strategy, _market())

    assert result.trades.empty
    assert result.equity_curve.iloc[-1]["equity"] == 10000.0
