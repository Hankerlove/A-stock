import numpy as np
import pandas as pd


ADJUSTED_PRICE_COLUMNS = {"adj_open", "adj_close"}


def require_columns(df: pd.DataFrame, columns: list[str], table: str) -> None:
    missing = [col for col in columns if col not in df.columns]
    if missing:
        raise ValueError(f"{table} 缺少必要字段: {', '.join(missing)}")


def has_adjusted_prices(daily: pd.DataFrame) -> bool:
    return ADJUSTED_PRICE_COLUMNS.issubset(daily.columns)


def adjusted_prices(daily: pd.DataFrame, adj_factor: pd.DataFrame) -> pd.DataFrame:
    if has_adjusted_prices(daily):
        return daily.copy()
    require_columns(
        daily,
        ["ts_code", "trade_date", "open", "high", "low", "close", "amount"],
        "daily",
    )
    require_columns(adj_factor, ["ts_code", "trade_date", "adj_factor"], "adj_factor")
    daily_base = daily.drop(columns=["adj_factor"], errors="ignore").copy()
    merged = pd.merge(
        daily_base,
        adj_factor[["ts_code", "trade_date", "adj_factor"]].copy(),
        on=["ts_code", "trade_date"],
        how="left",
    )
    merged["adj_factor"] = merged.groupby("ts_code")["adj_factor"].ffill().bfill()
    latest_factor = merged.groupby("ts_code")["adj_factor"].transform("last")
    ratio = merged["adj_factor"].astype(float) / latest_factor.replace(0, np.nan).astype(float)
    for col in ["open", "high", "low", "close"]:
        merged[f"adj_{col}"] = merged[col].astype(float) * ratio
    return merged


def latest_on_or_before(df: pd.DataFrame, date_col: str, trade_date: str) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    require_columns(df, ["ts_code", date_col], "market table")
    eligible = df[df[date_col] <= trade_date].copy()
    if eligible.empty:
        return eligible
    return (
        eligible.sort_values(["ts_code", date_col])
        .groupby("ts_code", as_index=False)
        .tail(1)
        .reset_index(drop=True)
    )


def active_universe(stock_basic: pd.DataFrame, trade_date: str) -> set[str]:
    if stock_basic.empty:
        return set()
    require_columns(stock_basic, ["ts_code", "list_status", "list_date"], "stock_basic")
    active = stock_basic[stock_basic["list_status"] == "L"].copy()
    list_date = _date_text(active["list_date"])
    active = active[(list_date.isna() | (list_date <= trade_date)).fillna(False)]
    if "delist_date" in active.columns:
        delist_date = _date_text(active["delist_date"])
        active = active[(delist_date.isna() | (delist_date >= trade_date)).fillna(False)]
    return set(active["ts_code"])


def _date_text(values: pd.Series) -> pd.Series:
    return values.astype("string").str.replace(r"\.0$", "", regex=True).str.zfill(8)


def trailing_volatility(
    daily_adj: pd.DataFrame,
    trade_date: str,
    lookback_days: int,
) -> pd.Series:
    if daily_adj.empty:
        return pd.Series(dtype=float, name="volatility")
    require_columns(daily_adj, ["ts_code", "trade_date", "adj_close"], "daily")
    window = daily_adj[daily_adj["trade_date"] <= trade_date].copy()
    window = window.sort_values(["ts_code", "trade_date"])
    pieces = []
    for ts_code, group in window.groupby("ts_code"):
        tail = group.tail(max(lookback_days + 1, 2))
        returns = tail["adj_close"].astype(float).pct_change().dropna()
        if len(returns) < max(1, min(lookback_days, 2)):
            continue
        pieces.append((ts_code, float(returns.std(ddof=0))))
    return pd.Series(dict(pieces), dtype=float, name="volatility")


def percentile_rank(values: pd.Series, high_is_good: bool) -> pd.Series:
    clean = values.astype(float).replace([np.inf, -np.inf], np.nan)
    if clean.notna().sum() == 0:
        return pd.Series(0.0, index=values.index)
    return clean.rank(pct=True, ascending=high_is_good).fillna(0.0)


def minmax_scale(values: pd.Series) -> pd.Series:
    clean = values.astype(float).replace([np.inf, -np.inf], np.nan)
    min_val = clean.min()
    max_val = clean.max()
    if pd.isna(min_val) or pd.isna(max_val) or max_val == min_val:
        return pd.Series(0.0, index=values.index)
    return ((clean - min_val) / (max_val - min_val)).fillna(0.0)


def target_weights(
    scores: pd.DataFrame,
    score_col: str,
    top_n: int,
    max_weight_per_stock: float | None = None,
) -> pd.Series:
    if scores.empty or top_n <= 0:
        return pd.Series(dtype=float, name="weight")
    selected = scores.sort_values([score_col, "ts_code"], ascending=[False, True]).head(top_n)
    raw = selected.set_index("ts_code")[score_col].clip(lower=0.0).astype(float)
    if raw.sum() <= 0:
        raw = pd.Series(1.0, index=raw.index)
    weights = raw / raw.sum()
    if max_weight_per_stock is not None and max_weight_per_stock > 0:
        weights = _apply_weight_cap(weights, max_weight_per_stock)
    weights.name = "weight"
    return weights


def _apply_weight_cap(weights: pd.Series, cap: float) -> pd.Series:
    if weights.empty:
        return weights
    capped = pd.Series(0.0, index=weights.index, dtype=float)
    remaining_weight = 1.0
    remaining = weights.copy()

    while not remaining.empty and remaining_weight > 0:
        allocation = remaining / remaining.sum() * remaining_weight
        over_cap = allocation > cap
        if not over_cap.any():
            capped.loc[allocation.index] = allocation
            return capped
        capped_names = allocation[over_cap].index
        capped.loc[capped_names] = cap
        remaining_weight -= cap * len(capped_names)
        remaining = remaining.drop(index=capped_names)

    return capped
