# Strategy And Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于现有本地数据同步系统，新增可参数化的 A 股选股策略模块和 T+1 回测模块。

**Architecture:** 新增 `strategy` 和 `backtest` 两个包，策略只生成目标权重，回测引擎负责 T+1 执行、交易成本、停牌/涨跌停约束和绩效指标。数据层通过现有 `DataStore` 只读查询，不改动同步系统和真实数据。

**Tech Stack:** Python >= 3.11, Pandas, DuckDB, Typer, pytest

**Spec:** `docs/superpowers/specs/2026-06-03-strategy-backtest-design.md`

**Implementation Status:** 2026-06-03 已完成第一版实现。实际落地内容包括内置 `dividend-low-vol` / `value-low-vol` 策略、只读数据加载器、T+1 回测引擎、参数化成本模型、停牌/涨跌停交易约束、CLI 命令和 README 更新。最终验证使用 `conda run -n astock python -m pytest -q`。

**Extension Status:** 2026-06-05 扩展内置策略，新增 `momentum-reversal` 与 `volume-price-breakout`，并让 `astock strategy explain` 从 dataclass metadata 输出每个参数的中文解释。设计文档与 README 已同步补充四个策略的实现说明、参数说明和 CLI 示例。

---

### Task 1: Strategy Core

**Files:**
- Create: `tests/strategy/test_builtin.py`
- Create: `src/astock/strategy/base.py`
- Create: `src/astock/strategy/factors.py`
- Create: `src/astock/strategy/registry.py`
- Create: `src/astock/strategy/builtin.py`
- Modify: `src/astock/strategy/__init__.py`

- [ ] **Step 1: Write failing strategy tests**

Add tests that assert:

```python
from astock.strategy import get_strategy, list_strategies

def test_registry_lists_builtin_strategies():
    assert "dividend-low-vol" in list_strategies()
    assert "value-low-vol" in list_strategies()

def test_dividend_low_vol_selects_high_dividend_low_volatility(sample_market_data):
    strategy = get_strategy("dividend-low-vol", top_n=1, lookback_days=3, min_amount=1000)
    signals = strategy.generate(sample_market_data, "20240105")
    assert signals.weights.to_dict() == {"000001.SZ": 1.0}
```

Run: `conda run -n astock python -m pytest tests/strategy/test_builtin.py -q`
Expected: FAIL because `astock.strategy.get_strategy` is not implemented.

- [ ] **Step 2: Implement strategy base and factors**

Implement:

```python
@dataclass(frozen=True)
class StrategySignal:
    trade_date: str
    weights: pd.Series
    scores: pd.DataFrame

class Strategy(Protocol):
    name: str
    description: str
    def generate(self, market: Mapping[str, pd.DataFrame], trade_date: str) -> StrategySignal: ...
```

Factor helpers must include adjusted price creation, percentage ranking, rolling volatility, and normalized target weights.

- [ ] **Step 3: Implement builtin strategies and registry**

Implement `DividendLowVolStrategy` and `ValueLowVolStrategy` with dataclass parameters. Strategy code must read all thresholds and weights from constructor parameters.

- [ ] **Step 4: Verify strategy tests**

Run: `conda run -n astock python -m pytest tests/strategy/test_builtin.py -q`
Expected: PASS.

### Task 2: Backtest Engine

**Files:**
- Create: `tests/backtest/test_engine.py`
- Create: `src/astock/backtest/config.py`
- Create: `src/astock/backtest/metrics.py`
- Create: `src/astock/backtest/engine.py`
- Modify: `src/astock/backtest/__init__.py`

- [ ] **Step 1: Write failing backtest tests**

Add tests that assert:

```python
def test_backtest_executes_signal_on_next_trade_day():
    result = BacktestEngine(config).run(strategy, market)
    first_trade = result.trades.iloc[0]
    assert first_trade["signal_date"] == "20240102"
    assert first_trade["trade_date"] == "20240103"

def test_transaction_cost_parameters_change_cash():
    low_cost = BacktestEngine(low_cost_config).run(strategy, market)
    high_cost = BacktestEngine(high_cost_config).run(strategy, market)
    assert high_cost.equity_curve.iloc[-1]["equity"] < low_cost.equity_curve.iloc[-1]["equity"]
```

Run: `conda run -n astock python -m pytest tests/backtest/test_engine.py -q`
Expected: FAIL because `BacktestEngine` is not implemented.

- [ ] **Step 2: Implement config and metrics**

Implement frozen dataclasses:

```python
@dataclass(frozen=True)
class ExecutionConfig:
    commission_rate: float = 0.0003
    stamp_duty_rate: float = 0.0005
    slippage_rate: float = 0.0005
    min_commission: float = 5.0
    lot_size: int = 100
    enforce_suspend: bool = True
    enforce_limit: bool = True

@dataclass(frozen=True)
class BacktestConfig:
    start_date: str
    end_date: str
    initial_cash: float = 1_000_000.0
    rebalance_frequency: str = "monthly"
```

Metrics must calculate total return, annual return, max drawdown, Sharpe, turnover, and trade count.

- [ ] **Step 3: Implement T+1 engine**

Engine requirements:

- signals use date T
- trades execute on next available trade date
- buy/sell cost rules use `ExecutionConfig`
- suspend and limit filters can reject orders
- valuation uses adjusted close
- no mutation of market input frames

- [ ] **Step 4: Verify backtest tests**

Run: `conda run -n astock python -m pytest tests/backtest/test_engine.py -q`
Expected: PASS.

### Task 3: Read-Only Data Loader

**Files:**
- Create: `tests/backtest/test_data.py`
- Create: `src/astock/backtest/data.py`

- [ ] **Step 1: Write failing loader tests**

Add tests that save temporary Parquet files with `DataStore`, then assert loader returns only requested date ranges and computed `adj_open` / `adj_close`.

Run: `conda run -n astock python -m pytest tests/backtest/test_data.py -q`
Expected: FAIL because `BacktestDataLoader` is not implemented.

- [ ] **Step 2: Implement loader**

Implement `BacktestDataLoader.load(start_date, end_date)` using read-only DuckDB queries against existing table directories. It must use `union_by_name=true`, handle missing optional tables with empty DataFrames, and never call `store.save`.

- [ ] **Step 3: Verify loader tests**

Run: `conda run -n astock python -m pytest tests/backtest/test_data.py -q`
Expected: PASS.

### Task 4: CLI And Docs

**Files:**
- Create: `tests/cli/test_strategy_backtest_cmd.py`
- Modify: `src/astock/cli/strategy_cmd.py`
- Modify: `src/astock/cli/backtest_cmd.py`
- Modify: `README.md`

- [ ] **Step 1: Write failing CLI tests**

Add tests for:

```python
def test_strategy_list_command():
    result = runner.invoke(app, ["strategy", "list"])
    assert result.exit_code == 0
    assert "dividend-low-vol" in result.output

def test_backtest_run_requires_dates():
    result = runner.invoke(app, ["backtest", "run", "--strategy", "dividend-low-vol"])
    assert result.exit_code != 0
```

Run: `conda run -n astock python -m pytest tests/cli/test_strategy_backtest_cmd.py -q`
Expected: FAIL until CLI commands are implemented.

- [ ] **Step 2: Implement CLI**

`strategy list` prints registered strategies. `strategy explain` prints description and parameters. `strategy signals` loads local data through `BacktestDataLoader` and prints weights.

`backtest run` accepts strategy and execution parameters, loads data read-only, runs engine, prints metrics, and optionally exports equity/trades CSV files when the user explicitly passes output paths.

- [ ] **Step 3: Update README**

Document new strategy/backtest commands and the parameterized cost model.

- [ ] **Step 4: Verify all tests**

Run: `conda run -n astock python -m pytest -q`
Expected: all tests PASS.

### Task 5: Momentum/Reversal And Volume-Price Breakout Extension

**Files:**
- Modify: `tests/strategy/test_builtin.py`
- Modify: `tests/cli/test_strategy_backtest_cmd.py`
- Modify: `src/astock/strategy/builtin.py`
- Modify: `src/astock/strategy/__init__.py`
- Modify: `src/astock/cli/strategy_cmd.py`
- Modify: `src/astock/cli/backtest_cmd.py`
- Modify: `docs/superpowers/specs/2026-06-03-strategy-backtest-design.md`
- Modify: `README.md`

- [x] **Step 1: Write failing tests**

Added red tests for registry entries, `momentum-reversal`, `volume-price-breakout`, and Chinese parameter descriptions in `astock strategy explain`.

- [x] **Step 2: Implement strategies**

Implemented deterministic daily-data strategies:

- `MomentumReversalStrategy`: medium-term adjusted-price momentum plus short-term reversal.
- `VolumePriceBreakoutStrategy`: adjusted-price breakout plus volume confirmation.

- [x] **Step 3: Implement explain metadata**

All built-in strategy parameters now carry Chinese descriptions through dataclass field metadata, and `strategy explain` prints them.

- [x] **Step 4: Update docs**

Design doc and README now list all four strategies, each strategy implementation, and each parameter explanation.
