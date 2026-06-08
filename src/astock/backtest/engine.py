from dataclasses import dataclass
from math import floor
from typing import Mapping

import pandas as pd

from astock.backtest.config import BacktestConfig
from astock.backtest.metrics import calculate_metrics
from astock.strategy.base import Strategy
from astock.strategy.factors import adjusted_prices


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: pd.DataFrame
    trades: pd.DataFrame
    metrics: dict[str, float | int]


class BacktestEngine:
    def __init__(self, config: BacktestConfig):
        self.config = config

    def run(self, strategy: Strategy, market: Mapping[str, pd.DataFrame]) -> BacktestResult:
        trade_dates = self._trade_dates(market)
        if not trade_dates:
            raise ValueError("回测区间内没有交易日")

        daily = self._daily_with_adjusted_prices(market)
        price_rows = {}
        price_rows_by_date: dict[str, list[object]] = {}
        for row in daily.itertuples(index=False):
            if self.config.start_date <= row.trade_date <= self.config.end_date:
                price_rows[(row.ts_code, row.trade_date)] = row
                price_rows_by_date.setdefault(row.trade_date, []).append(row)
        rebalance_dates = set(self._rebalance_dates(trade_dates))
        cash = float(self.config.initial_cash)
        positions: dict[str, float] = {}
        last_close_prices: dict[str, float] = {}
        scheduled: dict[str, tuple[str, pd.Series]] = {}
        equity_rows: list[dict[str, float | str]] = []
        trade_rows: list[dict[str, float | str]] = []

        for idx, date in enumerate(trade_dates):
            if date in scheduled:
                signal_date, target = scheduled.pop(date)
                cash = self._rebalance(
                    signal_date=signal_date,
                    trade_date=date,
                    target_weights=target,
                    price_rows=price_rows,
                    market=market,
                    cash=cash,
                    positions=positions,
                    fallback_prices=last_close_prices,
                    trade_rows=trade_rows,
                )

            for row in price_rows_by_date.get(date, []):
                last_close_prices[row.ts_code] = float(row.adj_close)

            positions_value = self._positions_value(
                date, positions, price_rows, "adj_close", last_close_prices
            )
            equity = cash + positions_value
            equity_rows.append({
                "trade_date": date,
                "cash": cash,
                "positions_value": positions_value,
                "equity": equity,
            })

            if date in rebalance_dates and idx + 1 < len(trade_dates):
                signal = strategy.generate(market, date)
                scheduled[trade_dates[idx + 1]] = (date, self._clean_weights(signal.weights))

        equity_curve = pd.DataFrame(equity_rows)
        trades = pd.DataFrame(trade_rows)
        if trades.empty:
            trades = pd.DataFrame(columns=[
                "signal_date", "trade_date", "ts_code", "side", "shares",
                "price", "gross_amount", "commission", "stamp_duty",
                "slippage", "cash_after",
            ])
        metrics = calculate_metrics(equity_curve, trades, self.config.initial_cash)
        return BacktestResult(equity_curve=equity_curve, trades=trades, metrics=metrics)

    def _trade_dates(self, market: Mapping[str, pd.DataFrame]) -> list[str]:
        trade_cal = market.get("trade_cal", pd.DataFrame())
        if not trade_cal.empty and {"cal_date", "is_open"}.issubset(trade_cal.columns):
            dates = trade_cal[
                (trade_cal["cal_date"] >= self.config.start_date)
                & (trade_cal["cal_date"] <= self.config.end_date)
                & (trade_cal["is_open"].astype(str) == "1")
            ]["cal_date"]
        else:
            daily = market.get("daily", pd.DataFrame())
            if daily.empty or "trade_date" not in daily.columns:
                return []
            dates = daily[
                (daily["trade_date"] >= self.config.start_date)
                & (daily["trade_date"] <= self.config.end_date)
            ]["trade_date"]
        return sorted(pd.Series(dates).drop_duplicates().astype(str).tolist())

    def _rebalance_dates(self, trade_dates: list[str]) -> list[str]:
        candidates = trade_dates[:-1]
        if self.config.rebalance_frequency == "daily":
            return candidates
        grouped: dict[str, str] = {}
        for date in candidates:
            if self.config.rebalance_frequency == "weekly":
                key = pd.to_datetime(date).strftime("%G%V")
            else:
                key = date[:6]
            grouped[key] = date
        return list(grouped.values())

    def _daily_with_adjusted_prices(self, market: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
        daily = market.get("daily", pd.DataFrame())
        if daily.empty:
            raise ValueError("market 缺少 daily 数据")
        if {"adj_open", "adj_close"}.issubset(daily.columns):
            return daily.copy()
        adj_factor = market.get("adj_factor", pd.DataFrame())
        if adj_factor.empty:
            raise ValueError("market 缺少 adj_factor 数据，无法计算复权价格")
        return adjusted_prices(daily, adj_factor)

    def _rebalance(
        self,
        signal_date: str,
        trade_date: str,
        target_weights: pd.Series,
        price_rows: dict[tuple[str, str], object],
        market: Mapping[str, pd.DataFrame],
        cash: float,
        positions: dict[str, float],
        fallback_prices: dict[str, float],
        trade_rows: list[dict[str, float | str]],
    ) -> float:
        portfolio_value = cash + self._positions_value(
            trade_date, positions, price_rows, "adj_open", fallback_prices
        )
        current_values = {}
        for code, shares in positions.items():
            price = self._price_or_fallback(code, trade_date, price_rows, "adj_open", fallback_prices)
            if price is not None:
                current_values[code] = shares * price
        target_values = {
            code: float(weight) * portfolio_value
            for code, weight in target_weights.items()
            if weight > 0
        }
        sell_codes = sorted(set(current_values) - set(target_values)) + sorted(
            code for code in set(current_values) & set(target_values)
            if target_values[code] < current_values[code]
        )
        buy_codes = sorted(
            code for code in target_values
            if target_values[code] > current_values.get(code, 0.0)
        )

        for code in sell_codes:
            cash = self._sell(
                code, signal_date, trade_date, target_values.get(code, 0.0),
                price_rows, market, cash, positions, trade_rows,
            )
        for code in buy_codes:
            cash = self._buy(
                code, signal_date, trade_date, target_values[code],
                price_rows, market, cash, positions, trade_rows,
            )
        for code in [code for code, shares in positions.items() if shares <= 0]:
            del positions[code]
        return cash

    def _buy(
        self,
        code: str,
        signal_date: str,
        trade_date: str,
        target_value: float,
        price_rows: dict[tuple[str, str], object],
        market: Mapping[str, pd.DataFrame],
        cash: float,
        positions: dict[str, float],
        trade_rows: list[dict[str, float | str]],
    ) -> float:
        if not self._can_trade(code, trade_date, "buy", price_rows, market):
            return cash
        price = self._price(code, trade_date, price_rows, "adj_open")
        current_value = positions.get(code, 0.0) * price
        delta_value = max(target_value - current_value, 0.0)
        exec_price = price * (1.0 + self.config.execution.slippage_rate)
        shares = self._round_lot(delta_value / exec_price)
        while shares > 0:
            gross = shares * exec_price
            commission = self._commission(gross)
            if gross + commission <= cash + 1e-9:
                break
            shares -= self.config.execution.lot_size
        if shares <= 0:
            return cash
        gross = shares * exec_price
        commission = self._commission(gross)
        cash -= gross + commission
        positions[code] = positions.get(code, 0.0) + shares
        trade_rows.append(self._trade_row(
            signal_date, trade_date, code, "buy", shares, exec_price,
            gross, commission, 0.0, gross - shares * price, cash,
        ))
        return cash

    def _sell(
        self,
        code: str,
        signal_date: str,
        trade_date: str,
        target_value: float,
        price_rows: dict[tuple[str, str], object],
        market: Mapping[str, pd.DataFrame],
        cash: float,
        positions: dict[str, float],
        trade_rows: list[dict[str, float | str]],
    ) -> float:
        shares_held = positions.get(code, 0.0)
        if shares_held <= 0 or not self._can_trade(code, trade_date, "sell", price_rows, market):
            return cash
        price = self._price(code, trade_date, price_rows, "adj_open")
        target_shares = target_value / price if price > 0 else 0.0
        if target_shares <= 0:
            shares = shares_held
        else:
            shares = min(shares_held, self._round_lot(shares_held - target_shares))
        if shares <= 0:
            return cash
        exec_price = price * (1.0 - self.config.execution.slippage_rate)
        gross = shares * exec_price
        commission = self._commission(gross)
        stamp_duty = gross * self.config.execution.stamp_duty_rate
        cash += gross - commission - stamp_duty
        positions[code] = shares_held - shares
        trade_rows.append(self._trade_row(
            signal_date, trade_date, code, "sell", shares, exec_price,
            gross, commission, stamp_duty, shares * price - gross, cash,
        ))
        return cash

    def _can_trade(
        self,
        code: str,
        trade_date: str,
        side: str,
        price_rows: dict[tuple[str, str], object],
        market: Mapping[str, pd.DataFrame],
    ) -> bool:
        if not self._has_price(code, trade_date, price_rows):
            return False
        if self.config.execution.enforce_suspend and self._is_suspended(code, trade_date, market):
            return False
        if self.config.execution.enforce_limit and self._is_limited(code, trade_date, side, price_rows):
            return False
        return True

    def _is_suspended(self, code: str, trade_date: str, market: Mapping[str, pd.DataFrame]) -> bool:
        suspend = market.get("suspend_d", pd.DataFrame())
        if suspend.empty or not {"ts_code", "trade_date", "suspend_type"}.issubset(suspend.columns):
            return False
        rows = suspend[
            (suspend["ts_code"] == code)
            & (suspend["trade_date"] == trade_date)
            & (suspend["suspend_type"] == "S")
        ]
        return not rows.empty

    def _is_limited(
        self,
        code: str,
        trade_date: str,
        side: str,
        price_rows: dict[tuple[str, str], object],
    ) -> bool:
        row = price_rows[(code, trade_date)]
        pct_chg = self._open_pct_chg(row)
        if pct_chg is None:
            pct_chg = getattr(row, "pct_chg", None)
        if pct_chg is None or pd.isna(pct_chg):
            return False
        threshold = 20.0 if code.startswith(("30", "68")) else 10.0
        buffer = self.config.execution.limit_buffer_pct
        if side == "buy":
            return float(pct_chg) >= threshold - buffer
        return float(pct_chg) <= -threshold + buffer

    def _positions_value(
        self,
        trade_date: str,
        positions: dict[str, float],
        price_rows: dict[tuple[str, str], object],
        price_col: str,
        fallback_prices: dict[str, float] | None = None,
    ) -> float:
        value = 0.0
        for code, shares in positions.items():
            price = self._price_or_fallback(code, trade_date, price_rows, price_col, fallback_prices)
            if price is not None:
                value += shares * price
        return float(value)

    def _price_or_fallback(
        self,
        code: str,
        trade_date: str,
        price_rows: dict[tuple[str, str], object],
        price_col: str,
        fallback_prices: dict[str, float] | None = None,
    ) -> float | None:
        if self._has_price(code, trade_date, price_rows):
            return self._price(code, trade_date, price_rows, price_col)
        if fallback_prices and code in fallback_prices:
            return float(fallback_prices[code])
        return None

    def _price(
        self,
        code: str,
        trade_date: str,
        price_rows: dict[tuple[str, str], object],
        price_col: str,
    ) -> float:
        return float(getattr(price_rows[(code, trade_date)], price_col))

    def _has_price(
        self,
        code: str,
        trade_date: str,
        price_rows: dict[tuple[str, str], object],
    ) -> bool:
        return (code, trade_date) in price_rows

    def _open_pct_chg(self, row: object) -> float | None:
        open_price = getattr(row, "open", None)
        pre_close = getattr(row, "pre_close", None)
        if open_price is None or pre_close is None or pd.isna(open_price) or pd.isna(pre_close):
            return None
        pre_close = float(pre_close)
        if pre_close <= 0:
            return None
        return (float(open_price) / pre_close - 1.0) * 100.0

    def _round_lot(self, shares: float) -> int:
        return floor(max(shares, 0.0) / self.config.execution.lot_size) * self.config.execution.lot_size

    def _commission(self, gross_amount: float) -> float:
        if gross_amount <= 0:
            return 0.0
        commission = gross_amount * self.config.execution.commission_rate
        if self.config.execution.min_commission > 0:
            commission = max(commission, self.config.execution.min_commission)
        return float(commission)

    def _clean_weights(self, weights: pd.Series) -> pd.Series:
        if weights.empty:
            return pd.Series(dtype=float, name="weight")
        clean = weights.astype(float).clip(lower=0.0)
        total = clean.sum()
        if total > 1.0:
            clean = clean / total
        clean.name = "weight"
        return clean[clean > 0]

    def _trade_row(
        self,
        signal_date: str,
        trade_date: str,
        code: str,
        side: str,
        shares: float,
        price: float,
        gross_amount: float,
        commission: float,
        stamp_duty: float,
        slippage: float,
        cash_after: float,
    ) -> dict[str, float | str]:
        return {
            "signal_date": signal_date,
            "trade_date": trade_date,
            "ts_code": code,
            "side": side,
            "shares": shares,
            "price": price,
            "gross_amount": gross_amount,
            "commission": commission,
            "stamp_duty": stamp_duty,
            "slippage": slippage,
            "cash_after": cash_after,
        }
