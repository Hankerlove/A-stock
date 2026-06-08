import math

import pandas as pd


def calculate_metrics(
    equity_curve: pd.DataFrame,
    trades: pd.DataFrame,
    initial_cash: float,
) -> dict[str, float | int]:
    if equity_curve.empty:
        return {
            "total_return": 0.0,
            "annual_return": 0.0,
            "max_drawdown": 0.0,
            "sharpe": 0.0,
            "turnover": 0.0,
            "trade_count": 0,
        }

    equity = equity_curve["equity"].astype(float)
    total_return = float(equity.iloc[-1] / initial_cash - 1.0)
    periods = max(len(equity) - 1, 1)
    annual_return = float((1.0 + total_return) ** (252.0 / periods) - 1.0) if total_return > -1 else -1.0
    peak = equity.cummax()
    drawdown = equity / peak - 1.0
    max_drawdown = float(drawdown.min())
    returns = equity.pct_change().dropna()
    if len(returns) > 1 and returns.std(ddof=0) > 0:
        sharpe = float(returns.mean() / returns.std(ddof=0) * math.sqrt(252.0))
    else:
        sharpe = 0.0
    if trades.empty:
        turnover = 0.0
    else:
        turnover = float(trades["gross_amount"].abs().sum() / equity.mean())
    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "turnover": turnover,
        "trade_count": int(len(trades)),
    }

