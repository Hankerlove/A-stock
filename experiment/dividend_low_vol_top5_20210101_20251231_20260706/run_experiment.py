import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from astock.backtest import BacktestConfig, BacktestDataLoader, BacktestEngine, BacktestResult, ExecutionConfig, calculate_metrics
from astock.core.config import Config
from astock.data.store.db import DataStore
from astock.strategy.base import MarketData, StrategySignal, empty_signal
from astock.strategy.factors import active_universe, latest_on_or_before, minmax_scale, percentile_rank, require_columns, target_weights

START_DATE = "20210101"
END_DATE = "20251231"
TOP_N = 5
INITIAL_CASH = 1_000_000.0
REBALANCE_FREQUENCY = "monthly"
OUTPUT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.yaml"
MAX_LOOKBACK_DAYS = 180

LOOKBACK_DAYS = [40, 60, 90, 120, 180]
MIN_AMOUNTS = [0.0, 10_000.0, 50_000.0]
WEIGHT_COMBOS = [
    {"dividend_weight": 0.5, "volatility_weight": 0.5, "value_weight": 0.0},
    {"dividend_weight": 0.6, "volatility_weight": 0.4, "value_weight": 0.0},
    {"dividend_weight": 0.7, "volatility_weight": 0.3, "value_weight": 0.0},
    {"dividend_weight": 0.8, "volatility_weight": 0.2, "value_weight": 0.0},
    {"dividend_weight": 0.5, "volatility_weight": 0.4, "value_weight": 0.1},
    {"dividend_weight": 0.6, "volatility_weight": 0.3, "value_weight": 0.1},
    {"dividend_weight": 0.7, "volatility_weight": 0.2, "value_weight": 0.1},
    {"dividend_weight": 0.5, "volatility_weight": 0.3, "value_weight": 0.2},
    {"dividend_weight": 0.6, "volatility_weight": 0.2, "value_weight": 0.2},
]
CAPS = [0.25, 0.30, 0.35]
SELECTION_RULE = [
    "status == 'ok'",
    "trade_count > 0",
    "sharpe desc",
    "annual_return desc",
    "max_drawdown desc",
    "turnover asc",
    "run_id asc",
]


def history_start(date: str, lookback_days: int) -> str:
    dt = datetime.strptime(date, "%Y%m%d")
    calendar_days = max(lookback_days * 3, lookback_days + 30)
    return (dt - timedelta(days=calendar_days)).strftime("%Y%m%d")


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except Exception:
        return None


class DividendLowVolFrameCache:
    """Precompute reusable frames for a serial dividend-low-vol parameter sweep."""

    def __init__(self, market: MarketData):
        self.daily = market.get("daily", pd.DataFrame()).sort_values(["ts_code", "trade_date"]).copy()
        self.daily_basic = market.get("daily_basic", pd.DataFrame()).sort_values(["ts_code", "trade_date"]).copy()
        self.stock_basic = market.get("stock_basic", pd.DataFrame()).copy()
        self._volatility: dict[int, pd.DataFrame] = {}
        self._base: dict[tuple[str, int, float], pd.DataFrame] = {}

    def base(self, trade_date: str, lookback_days: int, min_amount: float) -> pd.DataFrame:
        key = (trade_date, int(lookback_days), float(min_amount))
        if key in self._base:
            return self._base[key].copy()
        if self.daily.empty or self.daily_basic.empty:
            self._base[key] = pd.DataFrame()
            return pd.DataFrame()

        today_daily = self.daily[self.daily["trade_date"] == trade_date].copy()
        today_basic = latest_on_or_before(self.daily_basic, "trade_date", trade_date)
        if today_daily.empty or today_basic.empty:
            self._base[key] = pd.DataFrame()
            return pd.DataFrame()

        universe = active_universe(self.stock_basic, trade_date) if not self.stock_basic.empty else set(today_daily["ts_code"])
        today_daily = today_daily[today_daily["ts_code"].isin(universe)]
        today_basic = today_basic[today_basic["ts_code"].isin(universe)]
        if min_amount > 0:
            today_daily = today_daily[today_daily["amount"].astype(float) >= min_amount]

        vol_today = self._volatility_frame(lookback_days)
        vol_today = vol_today[vol_today["trade_date"] == trade_date].set_index("ts_code")["volatility"]
        frame = pd.merge(today_basic, today_daily[["ts_code", "trade_date", "amount"]], on="ts_code", how="inner")
        frame = frame.join(vol_today, on="ts_code")
        frame = frame.dropna(subset=["volatility"]).reset_index(drop=True)
        self._base[key] = frame
        return frame.copy()

    def _volatility_frame(self, lookback_days: int) -> pd.DataFrame:
        lookback_days = int(lookback_days)
        if lookback_days in self._volatility:
            return self._volatility[lookback_days]
        require_columns(self.daily, ["ts_code", "trade_date", "adj_close"], "daily")
        min_periods = max(1, min(lookback_days, 2))
        vol = self.daily[["ts_code", "trade_date", "adj_close"]].copy()
        vol["return"] = vol.groupby("ts_code")["adj_close"].pct_change()
        vol["volatility"] = (
            vol.groupby("ts_code")["return"]
            .rolling(window=lookback_days, min_periods=min_periods)
            .std(ddof=0)
            .reset_index(level=0, drop=True)
        )
        result = vol[["ts_code", "trade_date", "volatility"]]
        self._volatility[lookback_days] = result
        return result


@dataclass(frozen=True)
class CachedDividendLowVolStrategy:
    cache: DividendLowVolFrameCache
    top_n: int
    lookback_days: int
    min_amount: float
    dividend_weight: float
    volatility_weight: float
    value_weight: float
    max_weight_per_stock: float | None

    name: str = "dividend-low-vol"
    description: str = "红利低波策略：偏好高股息、低波动，并支持成交额过滤。"

    def generate(self, market: MarketData, trade_date: str) -> StrategySignal:
        ranked = self.cache.base(trade_date, self.lookback_days, self.min_amount)
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


class SerialBacktestRunner:
    def __init__(self, config: BacktestConfig, market: MarketData):
        self.config = config
        self.market = market
        self.engine = BacktestEngine(config)
        self.trade_dates = self.engine._trade_dates(market)
        if not self.trade_dates:
            raise ValueError("回测区间内没有交易日")

        daily = self.engine._daily_with_adjusted_prices(market)
        self.price_rows = {}
        self.price_rows_by_date: dict[str, list[object]] = {}
        for row in daily.itertuples(index=False):
            if self.config.start_date <= row.trade_date <= self.config.end_date:
                self.price_rows[(row.ts_code, row.trade_date)] = row
                self.price_rows_by_date.setdefault(row.trade_date, []).append(row)
        self.rebalance_dates = set(self.engine._rebalance_dates(self.trade_dates))

    def run(self, strategy) -> BacktestResult:
        cash = float(self.config.initial_cash)
        positions: dict[str, float] = {}
        last_close_prices: dict[str, float] = {}
        scheduled: dict[str, tuple[str, pd.Series]] = {}
        equity_rows: list[dict[str, float | str]] = []
        trade_rows: list[dict[str, float | str]] = []

        for idx, date in enumerate(self.trade_dates):
            if date in scheduled:
                signal_date, target = scheduled.pop(date)
                cash = self.engine._rebalance(
                    signal_date=signal_date,
                    trade_date=date,
                    target_weights=target,
                    price_rows=self.price_rows,
                    market=self.market,
                    cash=cash,
                    positions=positions,
                    fallback_prices=last_close_prices,
                    trade_rows=trade_rows,
                )

            for row in self.price_rows_by_date.get(date, []):
                last_close_prices[row.ts_code] = float(row.adj_close)

            positions_value = self.engine._positions_value(
                date, positions, self.price_rows, "adj_close", last_close_prices
            )
            equity = cash + positions_value
            equity_rows.append({
                "trade_date": date,
                "cash": cash,
                "positions_value": positions_value,
                "equity": equity,
            })

            if date in self.rebalance_dates and idx + 1 < len(self.trade_dates):
                signal = strategy.generate(self.market, date)
                scheduled[self.trade_dates[idx + 1]] = (date, self.engine._clean_weights(signal.weights))

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


def base_candidates() -> list[dict]:
    candidates = []
    run_id = 1
    for lookback_days in LOOKBACK_DAYS:
        for min_amount in MIN_AMOUNTS:
            for combo in WEIGHT_COMBOS:
                candidates.append({
                    "run_id": run_id,
                    "stage": "A",
                    "top_n": TOP_N,
                    "lookback_days": lookback_days,
                    "min_amount": min_amount,
                    "max_weight_per_stock": None,
                    **combo,
                })
                run_id += 1
    return candidates


def sort_results(df: pd.DataFrame) -> pd.DataFrame:
    valid = df[(df["status"] == "ok") & (df["trade_count"].astype(float) > 0)].copy()
    return valid.sort_values(
        ["sharpe", "annual_return", "max_drawdown", "turnover", "run_id"],
        ascending=[False, False, False, True, True],
        kind="mergesort",
    )


def run_one(candidate: dict, market: MarketData, cache: DividendLowVolFrameCache, runner: SerialBacktestRunner) -> tuple[dict, object | None]:
    started = time.perf_counter()
    row = dict(candidate)
    result = None
    try:
        strategy = CachedDividendLowVolStrategy(
            cache=cache,
            top_n=int(candidate["top_n"]),
            lookback_days=int(candidate["lookback_days"]),
            min_amount=float(candidate["min_amount"]),
            dividend_weight=float(candidate["dividend_weight"]),
            volatility_weight=float(candidate["volatility_weight"]),
            value_weight=float(candidate["value_weight"]),
            max_weight_per_stock=candidate["max_weight_per_stock"],
        )
        result = runner.run(strategy)
        row.update(result.metrics)
        row["status"] = "ok"
        row["error"] = ""
    except Exception as exc:
        row.update({
            "total_return": None,
            "annual_return": None,
            "max_drawdown": None,
            "sharpe": None,
            "turnover": None,
            "trade_count": 0,
            "status": "failed",
            "error": str(exc),
        })
    row["elapsed_sec"] = round(time.perf_counter() - started, 6)
    return row, result


def flush_metrics(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df.to_csv(OUTPUT_DIR / "metrics.csv", index=False)
    return df


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TUSHARE_TOKEN", "dummy")

    cfg = Config.from_yaml(str(CONFIG_PATH))
    store = DataStore(db_path=cfg.storage.db_path, data_dir=cfg.storage.data_dir)
    data_coverage = {
        "daily_latest": store.get_latest_date("daily"),
        "trade_cal_latest": store.get_latest_date("trade_cal", "cal_date"),
        "daily_basic_latest": store.get_latest_date("daily_basic"),
    }
    run_config = {
        "strategy": "dividend-low-vol",
        "start_date": START_DATE,
        "end_date": END_DATE,
        "top_n": TOP_N,
        "initial_cash": INITIAL_CASH,
        "rebalance_frequency": REBALANCE_FREQUENCY,
        "execution": {
            "commission_rate": 0.0003,
            "stamp_duty_rate": 0.0005,
            "slippage_rate": 0.0005,
            "min_commission": 5.0,
            "lot_size": 100,
            "enforce_suspend": True,
            "enforce_limit": True,
        },
        "grid": {
            "lookback_days": LOOKBACK_DAYS,
            "min_amount": MIN_AMOUNTS,
            "weight_combos": WEIGHT_COMBOS,
            "stage_b_caps": CAPS,
            "stage_b_from_top_n": 5,
        },
        "selection_rule": SELECTION_RULE,
        "data_coverage": data_coverage,
        "git_commit": git_commit(),
        "notes": "All candidates are executed serially in a plain for loop; no Tushare API calls are made. Reusable factor frames are cached in memory to avoid recomputing identical local data transforms.",
    }
    (OUTPUT_DIR / "run_config.json").write_text(json.dumps(run_config, ensure_ascii=False, indent=2))

    for table, latest in data_coverage.items():
        if latest is not None and latest < END_DATE:
            raise RuntimeError(f"{table} only covers {latest}, earlier than required {END_DATE}")

    load_start = history_start(START_DATE, MAX_LOOKBACK_DAYS)
    market = BacktestDataLoader(store).load(load_start, END_DATE)
    cache = DividendLowVolFrameCache(market)
    execution = ExecutionConfig()
    backtest_config = BacktestConfig(
        start_date=START_DATE,
        end_date=END_DATE,
        initial_cash=INITIAL_CASH,
        rebalance_frequency=REBALANCE_FREQUENCY,
        execution=execution,
    )
    runner = SerialBacktestRunner(backtest_config, market)

    candidates = base_candidates()
    pd.DataFrame(candidates).to_csv(OUTPUT_DIR / "grid_candidates.csv", index=False)

    rows = []
    results_by_run_id = {}
    for candidate in candidates:
        row, result = run_one(candidate, market, cache, runner)
        rows.append(row)
        if result is not None:
            results_by_run_id[row["run_id"]] = result
        flush_metrics(rows)
        print(f"finished run {row['run_id']:03d} stage {row['stage']} status={row['status']}", flush=True)

    stage_a = sort_results(pd.DataFrame(rows)).head(5)
    next_run_id = max(candidate["run_id"] for candidate in candidates) + 1
    stage_b_candidates = []
    for _, row in stage_a.iterrows():
        for cap in CAPS:
            stage_b_candidates.append({
                "run_id": next_run_id,
                "stage": "B",
                "top_n": TOP_N,
                "lookback_days": int(row["lookback_days"]),
                "min_amount": float(row["min_amount"]),
                "dividend_weight": float(row["dividend_weight"]),
                "volatility_weight": float(row["volatility_weight"]),
                "value_weight": float(row["value_weight"]),
                "max_weight_per_stock": cap,
            })
            next_run_id += 1

    all_candidates = candidates + stage_b_candidates
    pd.DataFrame(all_candidates).to_csv(OUTPUT_DIR / "grid_candidates.csv", index=False)

    for candidate in stage_b_candidates:
        row, result = run_one(candidate, market, cache, runner)
        rows.append(row)
        if result is not None:
            results_by_run_id[row["run_id"]] = result
        flush_metrics(rows)
        print(f"finished run {row['run_id']:03d} stage {row['stage']} status={row['status']}", flush=True)

    metrics = flush_metrics(rows)
    top10 = sort_results(metrics).head(10)
    top10.to_csv(OUTPUT_DIR / "top10.csv", index=False)
    if top10.empty:
        raise RuntimeError("No successful experiment result with trades.")

    best = top10.iloc[0].to_dict()
    best_run_id = int(best["run_id"])
    best_result = results_by_run_id[best_run_id]
    best_result.equity_curve.to_csv(OUTPUT_DIR / "best_equity.csv", index=False)
    best_result.trades.to_csv(OUTPUT_DIR / "best_trades.csv", index=False)

    best_params = {
        "selected_run_id": best_run_id,
        "selection_rule": SELECTION_RULE,
        "strategy": "dividend-low-vol",
        "backtest": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "initial_cash": INITIAL_CASH,
            "rebalance_frequency": REBALANCE_FREQUENCY,
        },
        "params": {
            "top_n": int(best["top_n"]),
            "lookback_days": int(best["lookback_days"]),
            "min_amount": float(best["min_amount"]),
            "dividend_weight": float(best["dividend_weight"]),
            "volatility_weight": float(best["volatility_weight"]),
            "value_weight": float(best["value_weight"]),
            "max_weight_per_stock": None if pd.isna(best["max_weight_per_stock"]) else float(best["max_weight_per_stock"]),
        },
        "metrics": {
            "total_return": float(best["total_return"]),
            "annual_return": float(best["annual_return"]),
            "max_drawdown": float(best["max_drawdown"]),
            "sharpe": float(best["sharpe"]),
            "turnover": float(best["turnover"]),
            "trade_count": int(best["trade_count"]),
        },
        "data_coverage": data_coverage,
        "overfit_note": "Best parameters are selected only on 2021-2025 backtest results.",
    }
    (OUTPUT_DIR / "best_params.json").write_text(json.dumps(best_params, ensure_ascii=False, indent=2))
    print(json.dumps(best_params, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
