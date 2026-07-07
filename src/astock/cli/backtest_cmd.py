from datetime import datetime, timedelta
from pathlib import Path

import typer

from dataclasses import fields, is_dataclass

from astock.backtest import BacktestConfig, BacktestDataLoader, BacktestEngine, ExecutionConfig
from astock.strategy import get_strategy

app = typer.Typer(help="回测命令")


@app.command("run")
def run_backtest(
    strategy_name: str = typer.Option("dividend-low-vol", "--strategy", "-s", help="策略名称"),
    start: str = typer.Option(..., "--start", help="开始日期，格式 YYYYMMDD"),
    end: str = typer.Option(..., "--end", help="结束日期，格式 YYYYMMDD"),
    top_n: int | None = typer.Option(None, "--top-n", help="持仓股票数量；未传入时使用策略默认值"),
    lookback_days: int | None = typer.Option(None, "--lookback-days", help="因子回看交易日数量；未传入时使用策略默认值"),
    min_amount: float | None = typer.Option(None, "--min-amount", help="成交额过滤下限；未传入时使用策略默认值"),
    max_weight_per_stock: float | None = typer.Option(None, "--max-weight-per-stock", help="单票权重上限"),
    dividend_weight: float | None = typer.Option(None, "--dividend-weight", help="红利低波策略的股息率权重"),
    volatility_weight: float | None = typer.Option(None, "--volatility-weight", help="低波或动量策略的波动率惩罚权重"),
    value_weight: float | None = typer.Option(None, "--value-weight", help="红利低波策略的估值辅助权重"),
    pb_weight: float | None = typer.Option(None, "--pb-weight", help="价值低波策略的低 PB 权重"),
    pe_weight: float | None = typer.Option(None, "--pe-weight", help="价值低波策略的低 PE 权重"),
    market_cap_weight: float | None = typer.Option(None, "--market-cap-weight", help="价值低波策略的小市值倾斜权重"),
    momentum_window: int | None = typer.Option(None, "--momentum-window", help="动量/反转策略的中期动量窗口；未传入时使用策略默认值"),
    reversal_window: int | None = typer.Option(None, "--reversal-window", help="动量/反转策略的短期反转窗口；未传入时使用策略默认值"),
    skip_days: int | None = typer.Option(None, "--skip-days", help="动量/反转策略的跳过交易日数量；未传入时使用策略默认值"),
    momentum_weight: float | None = typer.Option(None, "--momentum-weight", help="动量/反转策略的中期动量权重"),
    reversal_weight: float | None = typer.Option(None, "--reversal-weight", help="动量/反转策略的短期反转权重"),
    breakout_window: int | None = typer.Option(None, "--breakout-window", help="量价突破策略的价格突破窗口；未传入时使用策略默认值"),
    volume_window: int | None = typer.Option(None, "--volume-window", help="量价突破策略的成交量均值窗口；未传入时使用策略默认值"),
    volume_multiplier: float | None = typer.Option(None, "--volume-multiplier", help="量价突破策略的成交量放大阈值；未传入时使用策略默认值"),
    min_pct_chg: float | None = typer.Option(None, "--min-pct-chg", help="量价突破策略的最小当日涨跌幅；未传入时使用策略默认值"),
    price_breakout_weight: float | None = typer.Option(None, "--price-breakout-weight", help="量价突破策略的价格突破强度权重"),
    volume_breakout_weight: float | None = typer.Option(None, "--volume-breakout-weight", help="量价突破策略的成交量放大强度权重"),
    initial_cash: float = typer.Option(1_000_000.0, "--initial-cash", help="初始资金"),
    rebalance_frequency: str = typer.Option("monthly", "--rebalance-frequency", help="换仓频率: daily | weekly | monthly"),
    commission_rate: float = typer.Option(0.0003, "--commission-rate", help="佣金费率"),
    stamp_duty_rate: float = typer.Option(0.0005, "--stamp-duty-rate", help="卖出印花税率"),
    slippage_rate: float = typer.Option(0.0005, "--slippage-rate", help="滑点率"),
    min_commission: float = typer.Option(5.0, "--min-commission", help="最低佣金"),
    lot_size: int = typer.Option(100, "--lot-size", help="交易手数"),
    enforce_suspend: bool = typer.Option(True, "--enforce-suspend/--no-enforce-suspend", help="是否阻止停牌交易"),
    enforce_limit: bool = typer.Option(True, "--enforce-limit/--no-enforce-limit", help="是否阻止涨跌停交易"),
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="配置文件路径"),
    output_equity: Path | None = typer.Option(None, "--output-equity", help="导出权益曲线 CSV"),
    output_trades: Path | None = typer.Option(None, "--output-trades", help="导出交易明细 CSV"),
):
    """运行回测"""
    from astock.core.config import Config
    from astock.data.store.db import DataStore

    try:
        cfg = Config.from_yaml(str(config))
        store = DataStore(db_path=cfg.storage.db_path, data_dir=cfg.storage.data_dir)
        strategy = _build_strategy(
            strategy_name=strategy_name,
            top_n=top_n,
            lookback_days=lookback_days,
            min_amount=min_amount,
            max_weight_per_stock=max_weight_per_stock,
            dividend_weight=dividend_weight,
            volatility_weight=volatility_weight,
            value_weight=value_weight,
            pb_weight=pb_weight,
            pe_weight=pe_weight,
            market_cap_weight=market_cap_weight,
            momentum_window=momentum_window,
            reversal_window=reversal_window,
            skip_days=skip_days,
            momentum_weight=momentum_weight,
            reversal_weight=reversal_weight,
            breakout_window=breakout_window,
            volume_window=volume_window,
            volume_multiplier=volume_multiplier,
            min_pct_chg=min_pct_chg,
            price_breakout_weight=price_breakout_weight,
            volume_breakout_weight=volume_breakout_weight,
        )
        history_window = _strategy_history_window(strategy)
        load_start = _history_start(start, history_window)
        market = BacktestDataLoader(store).load(load_start, end)
        execution = ExecutionConfig(
            commission_rate=commission_rate,
            stamp_duty_rate=stamp_duty_rate,
            slippage_rate=slippage_rate,
            min_commission=min_commission,
            lot_size=lot_size,
            enforce_suspend=enforce_suspend,
            enforce_limit=enforce_limit,
        )
        backtest_config = BacktestConfig(
            start_date=start,
            end_date=end,
            initial_cash=initial_cash,
            rebalance_frequency=rebalance_frequency,
            execution=execution,
        )
        result = BacktestEngine(backtest_config).run(strategy, market)
    except Exception as exc:
        typer.echo(f"回测失败: {exc}")
        raise typer.Exit(1) from exc

    typer.echo(f"策略: {strategy_name}")
    typer.echo(f"区间: {start} ~ {end}")
    typer.echo("-" * 34)
    for key, value in result.metrics.items():
        if isinstance(value, float):
            typer.echo(f"{key:<16} {value:>14.6f}")
        else:
            typer.echo(f"{key:<16} {value:>14}")

    if output_equity:
        result.equity_curve.to_csv(output_equity, index=False)
        typer.echo(f"权益曲线已导出: {output_equity}")
    if output_trades:
        result.trades.to_csv(output_trades, index=False)
        typer.echo(f"交易明细已导出: {output_trades}")


def _history_start(date: str, lookback_days: int) -> str:
    dt = datetime.strptime(date, "%Y%m%d")
    calendar_days = max(lookback_days * 3, lookback_days + 30)
    return (dt - timedelta(days=calendar_days)).strftime("%Y%m%d")


def _strategy_history_window(strategy) -> int:
    lookback = getattr(strategy, "lookback_days", 0) or 0
    momentum = getattr(strategy, "momentum_window", 0) or 0
    reversal = getattr(strategy, "reversal_window", 0) or 0
    skip = getattr(strategy, "skip_days", 0) or 0
    breakout = getattr(strategy, "breakout_window", 0) or 0
    volume = getattr(strategy, "volume_window", 0) or 0
    return max(lookback, momentum + reversal + skip, breakout, volume)


def _build_strategy(strategy_name: str, **params):
    strategy = get_strategy(strategy_name)
    if not is_dataclass(strategy):
        return get_strategy(strategy_name, **params)
    accepted = {
        item.name
        for item in fields(strategy)
        if item.name not in {"name", "description"}
    }
    filtered = {key: value for key, value in params.items() if key in accepted and value is not None}
    return get_strategy(strategy_name, **filtered)


if __name__ == "__main__":
    app()
