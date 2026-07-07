from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta
from pathlib import Path

import typer

from astock.strategy import get_strategy, list_strategies as registry_list_strategies

app = typer.Typer(help="选股策略命令")


@app.command("list")
def list_strategies():
    """列出可用策略"""
    for name in list_strategies_fn():
        strategy = get_strategy(name)
        typer.echo(f"{name:<18} {strategy.description}")


def list_strategies_fn() -> list[str]:
    return registry_list_strategies()


@app.command("explain")
def explain(
    name: str = typer.Argument(..., help="策略名称"),
):
    """查看策略说明与参数"""
    try:
        strategy = get_strategy(name)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc

    typer.echo(f"策略: {strategy.name}")
    typer.echo(f"说明: {strategy.description}")
    typer.echo("参数:")
    if is_dataclass(strategy):
        for item in fields(strategy):
            if item.name in {"name", "description"}:
                continue
            help_text = item.metadata.get("help", "")
            suffix = f"  # {help_text}" if help_text else ""
            typer.echo(f"  {item.name}: {getattr(strategy, item.name)}{suffix}")


@app.command("signals")
def signals(
    strategy_name: str = typer.Option("dividend-low-vol", "--strategy", "-s", help="策略名称"),
    date: str = typer.Option(..., "--date", "-d", help="信号日期，格式 YYYYMMDD"),
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
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="配置文件路径"),
):
    """生成指定日期的策略目标权重"""
    from astock.backtest.data import BacktestDataLoader
    from astock.core.config import Config
    from astock.data.store.db import DataStore

    try:
        cfg = Config.from_yaml(str(config))
        store = DataStore(db_path=cfg.storage.db_path, data_dir=cfg.storage.data_dir)
        strategy = _build_strategy(
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
            strategy_name=strategy_name,
        )
        history_window = _strategy_history_window(strategy)
        load_start = _history_start(date, history_window)
        market = BacktestDataLoader(store).load(load_start, date)
        signal = strategy.generate(market, date)
        stock_names = _load_stock_names(store)
    except Exception as exc:
        typer.echo(f"生成信号失败: {exc}")
        raise typer.Exit(1) from exc

    if signal.weights.empty:
        typer.echo("无入选股票。")
        return
    typer.echo(f"策略: {strategy_name}  日期: {date}")
    typer.echo(f"{'代码':<12} {'名称':<16} {'权重':>10}")
    typer.echo("-" * 42)
    for ts_code, weight in signal.weights.items():
        name = stock_names.get(str(ts_code), "-")
        typer.echo(f"{ts_code:<12} {name:<16} {weight:>10.4f}")


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


def _load_stock_names(store) -> dict[str, str]:
    if not store.table_exists("stock_basic"):
        return {}
    stocks = store.load("stock_basic")
    if stocks.empty or not {"ts_code", "name"}.issubset(stocks.columns):
        return {}
    names = stocks[["ts_code", "name"]].dropna(subset=["ts_code"]).copy()
    names["ts_code"] = names["ts_code"].astype(str)
    names["name"] = names["name"].fillna("").astype(str).str.strip()
    names = names.drop_duplicates(subset=["ts_code"], keep="last")
    return {row.ts_code: row.name for row in names.itertuples(index=False) if row.name}


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
