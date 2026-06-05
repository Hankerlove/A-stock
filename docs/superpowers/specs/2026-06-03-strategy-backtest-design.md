# A-Stock 策略与回测模块 — 设计文档

**日期**: 2026-06-03
**状态**: 第二版已实现，已覆盖红利低波、价值低波、动量/反转、量价突破四类策略

---

## 1. 目标

在不修改现有数据同步系统的前提下，基于本地 Parquet + DuckDB 数据层开发第一版策略模块和回测模块。

第一版目标是可维护、可回测、可解释，而不是追求复杂模型。策略参数、交易成本、换仓频率、股票数量、流动性过滤、涨跌停约束等都必须通过配置对象或 CLI 参数传入，不能散落在业务代码里。

## 2. 数据边界

本阶段只读取已同步的本地表：

| 表名 | 用途 |
|------|------|
| stock_basic | 股票名称、行业、上市/退市状态、上市日期过滤 |
| trade_cal | 交易日序列、换仓日与 T+1 执行日 |
| daily | OHLCV、涨跌幅、成交额、成交量、涨跌停近似判断 |
| adj_factor | 前复权价格计算 |
| daily_basic | PE/PB/股息率/市值/换手率/流动性因子 |
| suspend_d | 停牌股票过滤 |
| tech_indicator | 后续可用于技术策略；第一版不强依赖 |

约束：

- 只读取本地数据库和 Parquet 文件，不对 `data/` 目录做增删改。
- 不修改 `src/astock/data/source/`、`src/astock/data/sync/`、`src/astock/data/store/` 的既有实现。
- 回测和策略模块可以通过 `DataStore` 做只读查询。

## 3. 内置策略

### 3.1 红利低波策略

工程实现对应中证红利低波动指数的核心思想：高股息、低波动、流动性约束。中证指数官方方法论描述该指数选取股息率高且波动率低的证券，并使用股息率加权。

本项目第一版不复制指数的全部编制细节，因为现阶段没有完整分红历史和红利支付率表；先用 `daily_basic.dv_ratio` 或 `daily_basic.dv_ttm` 表示股息率，用前复权收益的滚动波动率表示低波，用 `daily.amount` 或 `daily_basic.turnover_rate` 做流动性过滤。

实现说明：

1. 用 `daily + adj_factor` 计算前复权价格。
2. 取 `trade_date` 当日行情，并取 `daily_basic` 中每只股票截至该日的最新指标。
3. 用 `stock_basic` 过滤未上市、已退市或非正常上市状态股票。
4. 用 `min_amount` 过滤成交额不足股票。
5. 计算 `lookback_days` 窗口内前复权收益波动率。
6. 综合打分：`dividend_weight * 股息率排名 - volatility_weight * 波动率惩罚 + value_weight * 低 PB 排名`。
7. 按分数选取前 `top_n`，再按分数归一化权重，并应用 `max_weight_per_stock`。

参数：

| 参数 | 中文说明 |
|------|----------|
| `top_n` | 持仓股票数量，按综合得分从高到低选取。 |
| `lookback_days` | 波动率回看窗口，使用前复权收盘价计算收益波动。 |
| `min_amount` | 成交额过滤下限，低于该成交额的股票不参与打分。 |
| `dividend_weight` | 股息率因子权重，越高越偏好高股息股票。 |
| `volatility_weight` | 波动率惩罚权重，越高越严格惩罚高波动股票。 |
| `value_weight` | 估值辅助因子权重，使用 PB 低估值排名。 |
| `max_weight_per_stock` | 单票最大权重上限；为空表示不限制。 |

### 3.2 价值低波策略

Fama-French 类型价值因子的工程近似：低 PB、低 PE、适度市值和低波动。现有 `daily_basic` 支持 `pb`、`pe`、`pe_ttm`、`total_mv`、`circ_mv`，足够做第一版价值低波。

实现说明：

1. 与红利低波相同，先计算前复权价格并做上市状态、成交额和日期过滤。
2. 优先使用 `pe_ttm`，缺失时退回 `pe`。
3. 计算 `lookback_days` 窗口内前复权收益波动率。
4. 综合打分：`pb_weight * 低 PB 排名 + pe_weight * 低 PE 排名 - volatility_weight * 波动率惩罚 + market_cap_weight * 小市值排名`。
5. 按分数选取前 `top_n`，归一化权重，并应用 `max_weight_per_stock`。

参数：

| 参数 | 中文说明 |
|------|----------|
| `top_n` | 持仓股票数量，按综合得分从高到低选取。 |
| `lookback_days` | 波动率回看窗口，使用前复权收盘价计算收益波动。 |
| `min_amount` | 成交额过滤下限，低于该成交额的股票不参与打分。 |
| `pb_weight` | 低 PB 因子权重，越高越偏好 PB 更低的股票。 |
| `pe_weight` | 低 PE 因子权重，优先使用 `pe_ttm`，缺失时使用 `pe`。 |
| `volatility_weight` | 波动率惩罚权重，越高越严格惩罚高波动股票。 |
| `market_cap_weight` | 小市值倾斜权重，使用 `total_mv` 低市值排名。 |
| `max_weight_per_stock` | 单票最大权重上限；为空表示不限制。 |

### 3.3 动量/反转策略

动量/反转策略对应“中期趋势 + 短期回调”的工程形态：中期走势越强越好，近期回撤越明显越偏向反转机会。该策略只依赖 `daily`、`adj_factor` 和可选 `stock_basic`，不要求 `daily_basic`。

实现说明：

1. 用 `daily + adj_factor` 计算前复权价格。
2. 用 `stock_basic` 过滤未上市、已退市或非正常上市状态股票；没有 `stock_basic` 时使用当日有行情的股票。
3. 用 `min_amount` 过滤成交额不足股票。
4. 对每只股票计算中期动量：在 `reversal_window + skip_days` 之前，取 `momentum_window` 窗口的前复权收益。
5. 对每只股票计算短期反转：当前前复权收盘价相对 `reversal_window` 之前的收益，收益越低反转排名越高。
6. 可选计算波动率惩罚。
7. 综合打分：`momentum_weight * 中期动量排名 + reversal_weight * 短期反转排名 - volatility_weight * 波动率惩罚`。
8. 按分数选取前 `top_n`，归一化权重，并应用 `max_weight_per_stock`。

参数：

| 参数 | 中文说明 |
|------|----------|
| `top_n` | 持仓股票数量，按综合得分从高到低选取。 |
| `momentum_window` | 中期动量窗口，计算短期反转窗口之前的前复权收益。 |
| `reversal_window` | 短期反转窗口，近期跌幅越大反转得分越高。 |
| `skip_days` | 动量窗口与当前日期之间跳过的交易日数量，用于降低短期噪声。 |
| `min_amount` | 成交额过滤下限，低于该成交额的股票不参与打分。 |
| `momentum_weight` | 中期动量权重，越高越偏好过去中期走势更强的股票。 |
| `reversal_weight` | 短期反转权重，越高越偏好近期回撤后的修复机会。 |
| `volatility_weight` | 波动率惩罚权重，越高越严格惩罚高波动股票。 |
| `max_weight_per_stock` | 单票最大权重上限；为空表示不限制。 |

### 3.4 量价突破策略

量价突破策略对应“价格突破前高 + 成交量确认”的工程形态：当前前复权收盘价突破过去窗口高点，同时成交量显著放大，并且当日涨跌幅满足确认阈值。该策略只依赖 `daily`、`adj_factor` 和可选 `stock_basic`，不要求 `daily_basic`。

实现说明：

1. 用 `daily + adj_factor` 计算前复权价格。
2. 用 `stock_basic` 过滤未上市、已退市或非正常上市状态股票；没有 `stock_basic` 时使用当日有行情的股票。
3. 用 `min_amount` 过滤成交额不足股票。
4. 计算 `breakout_window` 内不含当日的前复权收盘价最高值。
5. 计算 `volume_window` 内不含当日的平均成交量，并用当日成交量计算 `volume_ratio`。
6. 过滤条件：`price_breakout > 0`、`volume_ratio >= volume_multiplier`、`pct_chg >= min_pct_chg`。
7. 综合打分：`price_breakout_weight * 价格突破排名 + volume_breakout_weight * 成交量放大排名`。
8. 按分数选取前 `top_n`，归一化权重，并应用 `max_weight_per_stock`。

参数：

| 参数 | 中文说明 |
|------|----------|
| `top_n` | 持仓股票数量，按综合得分从高到低选取。 |
| `breakout_window` | 价格突破窗口，当前前复权收盘价需突破窗口内前高。 |
| `volume_window` | 成交量均值窗口，用于计算当前成交量放大倍数。 |
| `volume_multiplier` | 成交量放大阈值，当前成交量需达到过去均量的倍数。 |
| `min_pct_chg` | 当日最小涨跌幅要求，过滤无价格确认的放量。 |
| `min_amount` | 成交额过滤下限，低于该成交额的股票不参与打分。 |
| `price_breakout_weight` | 价格突破强度权重，越高越偏好突破幅度更大的股票。 |
| `volume_breakout_weight` | 成交量放大强度权重，越高越偏好量能确认更强的股票。 |
| `max_weight_per_stock` | 单票最大权重上限；为空表示不限制。 |

### 3.5 后续策略预留

后续可以增加：

- 技术指标策略：基于 `tech_indicator` 的 MA、MACD、RSI、ATR。

## 4. 回测口径

第一版回测采用中低频横截面持仓模型：

1. T 日收盘后计算信号和目标权重。
2. T+1 交易日开盘价执行调仓。
3. 每个交易日用前复权收盘价估值。
4. 买入时计入手续费和滑点。
5. 卖出时计入手续费、印花税和滑点。
6. 停牌股票不交易。
7. 涨停日不买入，跌停日不卖出；第一版用 `pct_chg` 按主板约 10%、创业板/科创板约 20% 近似判断。
8. 持仓权重由策略输出，执行层负责处理现金、成本、不可成交和整数手数。

所有交易规则通过 `BacktestConfig` / `ExecutionConfig` 传入：

- `initial_cash`
- `commission_rate`
- `stamp_duty_rate`
- `slippage_rate`
- `min_commission`
- `lot_size`
- `rebalance_frequency`
- `price_field`
- `enforce_suspend`
- `enforce_limit`

## 5. 模块结构

```
src/astock/
├── strategy/
│   ├── __init__.py
│   ├── base.py          # 策略协议、信号结果、参数基类
│   ├── factors.py       # 横截面排名、波动率、复权价格等因子工具
│   ├── registry.py      # 策略注册表
│   └── builtin.py       # 第一批内置策略
│
├── backtest/
│   ├── __init__.py
│   ├── config.py        # 回测和执行参数
│   ├── data.py          # 只读市场数据加载器
│   ├── engine.py        # T+1 调仓、成本、估值
│   └── metrics.py       # 收益、回撤、夏普、换手等指标
│
└── cli/
    ├── strategy_cmd.py  # list / explain / signals
    └── backtest_cmd.py  # run
```

## 6. CLI 设计

策略：

```bash
astock strategy list
astock strategy explain dividend-low-vol
astock strategy signals --strategy dividend-low-vol --date 20240131 --top-n 20 --lookback-days 60 --min-amount 50000
astock strategy explain momentum-reversal
astock strategy explain volume-price-breakout
astock strategy signals --strategy momentum-reversal --date 20240131 --momentum-window 60 --reversal-window 5
astock strategy signals --strategy volume-price-breakout --date 20240131 --breakout-window 20 --volume-multiplier 2.0
```

回测：

```bash
astock backtest run \
  --strategy dividend-low-vol \
  --start 20200101 \
  --end 20231231 \
  --top-n 20 \
  --initial-cash 1000000 \
  --commission-rate 0.0003 \
  --stamp-duty-rate 0.0005 \
  --slippage-rate 0.0005 \
  --rebalance-frequency monthly
```

## 7. 验证标准

- 单元测试覆盖策略打分、参数传入、空数据处理、T+1 执行、成本影响、停牌/涨跌停不可成交。
- CLI 测试至少覆盖 `strategy list` 和参数解析。
- 不访问 Tushare，不要求真实 token。
- 不写入本地真实数据。
- 全量测试命令：`conda run -n astock python -m pytest -q`。

## 8. 参考资料

- 中证指数有限公司: [中证红利低波动指数编制方案](https://oss-ch.csindex.com.cn/static/html/csindex/public/uploads/indices/detail/files/zh_CN/H30269_Index_Methodology_cn.pdf)
- Fama, E. F. and French, K. R. 1992: [The Cross-Section of Expected Stock Returns](https://doi.org/10.1111/j.1540-6261.1992.tb04398.x)
- Jegadeesh, N. and Titman, S. 1993: [Returns to Buying Winners and Selling Losers](https://www.nber.org/papers/w7159)
- Baker, N. L. and Haugen, R. A. 2012: [Low Risk Stocks Outperform within All Observable Markets of the World](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2055431)
