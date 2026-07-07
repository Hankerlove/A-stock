from dataclasses import dataclass, field

import pandas as pd

from astock.strategy.base import MarketData, StrategySignal, empty_signal
from astock.strategy.factors import (
    active_universe,
    adjusted_prices,
    has_adjusted_prices,
    latest_on_or_before,
    minmax_scale,
    percentile_rank,
    require_columns,
    target_weights,
    trailing_volatility,
)
from astock.strategy.registry import register_strategy


@dataclass(frozen=True)
class DividendLowVolStrategy:
    top_n: int = field(default=5, metadata={"help": "持仓股票数量，按综合得分从高到低选取。"})
    lookback_days: int = field(default=120, metadata={"help": "波动率回看窗口，使用前复权收盘价计算收益波动。"})
    min_amount: float = field(default=50_000.0, metadata={"help": "成交额过滤下限，低于该成交额的股票不参与打分。"})
    dividend_weight: float = field(default=0.6, metadata={"help": "股息率因子权重，越高越偏好高股息股票。"})
    volatility_weight: float = field(default=0.3, metadata={"help": "波动率惩罚权重，越高越严格惩罚高波动股票。"})
    value_weight: float = field(default=0.1, metadata={"help": "估值辅助因子权重，使用 PB 低估值排名。"})
    max_weight_per_stock: float | None = field(default=None, metadata={"help": "单票最大权重上限；为空表示不限制。"})

    name: str = "dividend-low-vol"
    description: str = "红利低波策略：偏好高股息、低波动，并支持成交额过滤。"

    def generate(self, market: MarketData, trade_date: str) -> StrategySignal:
        ranked = _base_frame(market, trade_date, self.lookback_days, self.min_amount)
        if ranked.empty:
            return empty_signal(trade_date)

        dividend_col = "dv_ttm" if "dv_ttm" in ranked.columns else "dv_ratio"
        require_columns(ranked, [dividend_col], "daily_basic")
        ranked["dividend_rank"] = percentile_rank(ranked[dividend_col], high_is_good=True)
        ranked["volatility_penalty"] = minmax_scale(ranked["volatility"])
        if "pb" in ranked.columns:
            ranked["value_rank"] = percentile_rank(ranked["pb"], high_is_good=False)
        else:
            ranked["value_rank"] = 0.0
        ranked["score"] = (
            self.dividend_weight * ranked["dividend_rank"]
            - self.volatility_weight * ranked["volatility_penalty"]
            + self.value_weight * ranked["value_rank"]
        )
        ranked = ranked.sort_values(["score", "ts_code"], ascending=[False, True]).reset_index(drop=True)
        weights = target_weights(ranked, "score", self.top_n, self.max_weight_per_stock)
        return StrategySignal(trade_date=trade_date, weights=weights, scores=ranked)


@dataclass(frozen=True)
class ValueLowVolStrategy:
    top_n: int = field(default=20, metadata={"help": "持仓股票数量，按综合得分从高到低选取。"})
    lookback_days: int = field(default=60, metadata={"help": "波动率回看窗口，使用前复权收盘价计算收益波动。"})
    min_amount: float = field(default=0.0, metadata={"help": "成交额过滤下限，低于该成交额的股票不参与打分。"})
    pb_weight: float = field(default=0.45, metadata={"help": "低 PB 因子权重，越高越偏好 PB 更低的股票。"})
    pe_weight: float = field(default=0.35, metadata={"help": "低 PE 因子权重，优先使用 pe_ttm，缺失时使用 pe。"})
    volatility_weight: float = field(default=0.2, metadata={"help": "波动率惩罚权重，越高越严格惩罚高波动股票。"})
    market_cap_weight: float = field(default=0.0, metadata={"help": "小市值倾斜权重，使用 total_mv 低市值排名。"})
    max_weight_per_stock: float | None = field(default=None, metadata={"help": "单票最大权重上限；为空表示不限制。"})

    name: str = "value-low-vol"
    description: str = "价值低波策略：偏好低 PB、低 PE、低波动，可选小市值倾斜。"

    def generate(self, market: MarketData, trade_date: str) -> StrategySignal:
        ranked = _base_frame(market, trade_date, self.lookback_days, self.min_amount)
        if ranked.empty:
            return empty_signal(trade_date)

        pe_col = "pe_ttm" if "pe_ttm" in ranked.columns else "pe"
        require_columns(ranked, ["pb", pe_col], "daily_basic")
        ranked["pb_rank"] = percentile_rank(ranked["pb"], high_is_good=False)
        ranked["pe_rank"] = percentile_rank(ranked[pe_col], high_is_good=False)
        ranked["volatility_penalty"] = minmax_scale(ranked["volatility"])
        if "total_mv" in ranked.columns:
            ranked["market_cap_rank"] = percentile_rank(ranked["total_mv"], high_is_good=False)
        else:
            ranked["market_cap_rank"] = 0.0
        ranked["score"] = (
            self.pb_weight * ranked["pb_rank"]
            + self.pe_weight * ranked["pe_rank"]
            - self.volatility_weight * ranked["volatility_penalty"]
            + self.market_cap_weight * ranked["market_cap_rank"]
        )
        ranked = ranked.sort_values(["score", "ts_code"], ascending=[False, True]).reset_index(drop=True)
        weights = target_weights(ranked, "score", self.top_n, self.max_weight_per_stock)
        return StrategySignal(trade_date=trade_date, weights=weights, scores=ranked)


@dataclass(frozen=True)
class MomentumReversalStrategy:
    top_n: int = field(default=20, metadata={"help": "持仓股票数量，按综合得分从高到低选取。"})
    momentum_window: int = field(default=60, metadata={"help": "中期动量窗口，计算短期反转窗口之前的前复权收益。"})
    reversal_window: int = field(default=5, metadata={"help": "短期反转窗口，近期跌幅越大反转得分越高。"})
    skip_days: int = field(default=0, metadata={"help": "动量窗口与当前日期之间跳过的交易日数量，用于降低短期噪声。"})
    min_amount: float = field(default=0.0, metadata={"help": "成交额过滤下限，低于该成交额的股票不参与打分。"})
    momentum_weight: float = field(default=0.7, metadata={"help": "中期动量权重，越高越偏好过去中期走势更强的股票。"})
    reversal_weight: float = field(default=0.3, metadata={"help": "短期反转权重，越高越偏好近期回撤后的修复机会。"})
    volatility_weight: float = field(default=0.0, metadata={"help": "波动率惩罚权重，越高越严格惩罚高波动股票。"})
    max_weight_per_stock: float | None = field(default=None, metadata={"help": "单票最大权重上限；为空表示不限制。"})

    name: str = "momentum-reversal"
    description: str = "动量/反转策略：偏好中期趋势较强、短期出现回调且流动性达标的股票。"

    def generate(self, market: MarketData, trade_date: str) -> StrategySignal:
        today_daily, daily_adj = _price_base_frame(market, trade_date, self.min_amount)
        if today_daily.empty:
            return empty_signal(trade_date)

        features = _momentum_reversal_features(
            daily_adj=daily_adj,
            trade_date=trade_date,
            momentum_window=self.momentum_window,
            reversal_window=self.reversal_window,
            skip_days=self.skip_days,
        )
        ranked = pd.merge(today_daily[["ts_code", "trade_date", "amount"]], features, on="ts_code", how="inner")
        ranked = ranked.dropna(subset=["momentum_return", "reversal_return"])
        if ranked.empty:
            return empty_signal(trade_date)

        ranked["momentum_rank"] = percentile_rank(ranked["momentum_return"], high_is_good=True)
        ranked["reversal_rank"] = percentile_rank(-ranked["reversal_return"], high_is_good=True)
        ranked["volatility_penalty"] = minmax_scale(ranked["volatility"])
        ranked["score"] = (
            self.momentum_weight * ranked["momentum_rank"]
            + self.reversal_weight * ranked["reversal_rank"]
            - self.volatility_weight * ranked["volatility_penalty"]
        )
        ranked = ranked.sort_values(["score", "ts_code"], ascending=[False, True]).reset_index(drop=True)
        weights = target_weights(ranked, "score", self.top_n, self.max_weight_per_stock)
        return StrategySignal(trade_date=trade_date, weights=weights, scores=ranked)


@dataclass(frozen=True)
class VolumePriceBreakoutStrategy:
    top_n: int = field(default=20, metadata={"help": "持仓股票数量，按综合得分从高到低选取。"})
    breakout_window: int = field(default=20, metadata={"help": "价格突破窗口，当前前复权收盘价需突破窗口内前高。"})
    volume_window: int = field(default=5, metadata={"help": "成交量均值窗口，用于计算当前成交量放大倍数。"})
    volume_multiplier: float = field(default=2.0, metadata={"help": "成交量放大阈值，当前成交量需达到过去均量的倍数。"})
    min_pct_chg: float = field(default=0.0, metadata={"help": "当日最小涨跌幅要求，过滤无价格确认的放量。"})
    min_amount: float = field(default=0.0, metadata={"help": "成交额过滤下限，低于该成交额的股票不参与打分。"})
    price_breakout_weight: float = field(default=0.6, metadata={"help": "价格突破强度权重，越高越偏好突破幅度更大的股票。"})
    volume_breakout_weight: float = field(default=0.4, metadata={"help": "成交量放大强度权重，越高越偏好量能确认更强的股票。"})
    max_weight_per_stock: float | None = field(default=None, metadata={"help": "单票最大权重上限；为空表示不限制。"})

    name: str = "volume-price-breakout"
    description: str = "量价突破策略：筛选价格突破前高且成交量显著放大的股票。"

    def generate(self, market: MarketData, trade_date: str) -> StrategySignal:
        today_daily, daily_adj = _price_base_frame(market, trade_date, self.min_amount)
        if today_daily.empty:
            return empty_signal(trade_date)

        features = _volume_price_breakout_features(
            daily_adj=daily_adj,
            trade_date=trade_date,
            breakout_window=self.breakout_window,
            volume_window=self.volume_window,
        )
        ranked = pd.merge(
            today_daily[["ts_code", "trade_date", "amount", "pct_chg"]],
            features,
            on="ts_code",
            how="inner",
        )
        ranked = ranked[
            (ranked["price_breakout"] > 0)
            & (ranked["volume_ratio"] >= self.volume_multiplier)
            & (ranked["pct_chg"].astype(float) >= self.min_pct_chg)
        ].copy()
        if ranked.empty:
            return empty_signal(trade_date)

        ranked["price_breakout_rank"] = percentile_rank(ranked["price_breakout"], high_is_good=True)
        ranked["volume_ratio_rank"] = percentile_rank(ranked["volume_ratio"], high_is_good=True)
        ranked["score"] = (
            self.price_breakout_weight * ranked["price_breakout_rank"]
            + self.volume_breakout_weight * ranked["volume_ratio_rank"]
        )
        ranked = ranked.sort_values(["score", "ts_code"], ascending=[False, True]).reset_index(drop=True)
        weights = target_weights(ranked, "score", self.top_n, self.max_weight_per_stock)
        return StrategySignal(trade_date=trade_date, weights=weights, scores=ranked)


def _base_frame(
    market: MarketData,
    trade_date: str,
    lookback_days: int,
    min_amount: float,
) -> pd.DataFrame:
    daily = market.get("daily", pd.DataFrame())
    daily_basic = market.get("daily_basic", pd.DataFrame())
    adj_factor = market.get("adj_factor", pd.DataFrame())
    stock_basic = market.get("stock_basic", pd.DataFrame())
    if daily.empty or daily_basic.empty or (adj_factor.empty and not has_adjusted_prices(daily)):
        return pd.DataFrame()

    daily_adj = adjusted_prices(daily, adj_factor)
    today_daily = daily_adj[daily_adj["trade_date"] == trade_date].copy()
    today_basic = latest_on_or_before(daily_basic, "trade_date", trade_date)
    if today_daily.empty or today_basic.empty:
        return pd.DataFrame()

    universe = active_universe(stock_basic, trade_date) if not stock_basic.empty else set(today_daily["ts_code"])
    today_daily = today_daily[today_daily["ts_code"].isin(universe)]
    today_basic = today_basic[today_basic["ts_code"].isin(universe)]
    if min_amount > 0:
        today_daily = today_daily[today_daily["amount"].astype(float) >= min_amount]
    vol = trailing_volatility(daily_adj, trade_date, lookback_days)
    frame = pd.merge(today_basic, today_daily[["ts_code", "trade_date", "amount"]], on="ts_code", how="inner")
    frame = frame.join(vol, on="ts_code")
    frame = frame.dropna(subset=["volatility"])
    return frame.reset_index(drop=True)


def _price_base_frame(
    market: MarketData,
    trade_date: str,
    min_amount: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    daily = market.get("daily", pd.DataFrame())
    adj_factor = market.get("adj_factor", pd.DataFrame())
    stock_basic = market.get("stock_basic", pd.DataFrame())
    if daily.empty or (adj_factor.empty and not has_adjusted_prices(daily)):
        return pd.DataFrame(), pd.DataFrame()

    daily_adj = adjusted_prices(daily, adj_factor)
    today_daily = daily_adj[daily_adj["trade_date"] == trade_date].copy()
    if today_daily.empty:
        return pd.DataFrame(), daily_adj

    universe = active_universe(stock_basic, trade_date) if not stock_basic.empty else set(today_daily["ts_code"])
    today_daily = today_daily[today_daily["ts_code"].isin(universe)]
    if min_amount > 0:
        today_daily = today_daily[today_daily["amount"].astype(float) >= min_amount]
    return today_daily.reset_index(drop=True), daily_adj


def _momentum_reversal_features(
    daily_adj: pd.DataFrame,
    trade_date: str,
    momentum_window: int,
    reversal_window: int,
    skip_days: int,
) -> pd.DataFrame:
    rows = []
    for ts_code, group in daily_adj[daily_adj["trade_date"] <= trade_date].sort_values(
        ["ts_code", "trade_date"]
    ).groupby("ts_code"):
        closes = group["adj_close"].astype(float).reset_index(drop=True)
        current_idx = len(closes) - 1
        reversal_start_idx = current_idx - reversal_window
        momentum_end_idx = current_idx - reversal_window - skip_days
        momentum_start_idx = momentum_end_idx - momentum_window
        if momentum_start_idx < 0 or reversal_start_idx < 0:
            continue
        momentum_base = closes.iloc[momentum_start_idx]
        reversal_base = closes.iloc[reversal_start_idx]
        if momentum_base <= 0 or reversal_base <= 0:
            continue
        returns = closes.pct_change().dropna()
        rows.append({
            "ts_code": ts_code,
            "momentum_return": closes.iloc[momentum_end_idx] / momentum_base - 1.0,
            "reversal_return": closes.iloc[current_idx] / reversal_base - 1.0,
            "volatility": float(returns.tail(momentum_window + reversal_window).std(ddof=0)),
        })
    return pd.DataFrame(rows)


def _volume_price_breakout_features(
    daily_adj: pd.DataFrame,
    trade_date: str,
    breakout_window: int,
    volume_window: int,
) -> pd.DataFrame:
    rows = []
    min_history = max(breakout_window, volume_window)
    for ts_code, group in daily_adj[daily_adj["trade_date"] <= trade_date].sort_values(
        ["ts_code", "trade_date"]
    ).groupby("ts_code"):
        if len(group) <= min_history:
            continue
        closes = group["adj_close"].astype(float).reset_index(drop=True)
        volumes = group["vol"].astype(float).reset_index(drop=True)
        current_close = closes.iloc[-1]
        previous_high = closes.iloc[-breakout_window - 1:-1].max()
        previous_volume = volumes.iloc[-volume_window - 1:-1].mean()
        if previous_high <= 0 or previous_volume <= 0:
            continue
        rows.append({
            "ts_code": ts_code,
            "price_breakout": current_close / previous_high - 1.0,
            "volume_ratio": volumes.iloc[-1] / previous_volume,
        })
    return pd.DataFrame(rows)


def register_builtin_strategies() -> None:
    for cls in [
        DividendLowVolStrategy,
        ValueLowVolStrategy,
        MomentumReversalStrategy,
        VolumePriceBreakoutStrategy,
    ]:
        try:
            register_strategy(cls.name, cls)
        except ValueError:
            pass
