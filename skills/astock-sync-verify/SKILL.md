---
name: astock-sync-verify
description: Use this skill whenever the user wants to sync A-Stock data, run astock data sync safely table-by-table, verify local data with tools/verify_data.py, diagnose ERROR/WARN output, or asks whether A-Stock data is complete/usable. This is the preferred workflow for A-Stock data synchronization because full astock data sync can trigger Tushare API/IP errors; run tables one by one in dependency order, then produce a visual checklist report with causes and classifications.
---

# A-Stock 分表同步与数据校验

## 目标

帮助用户安全完成 A-Stock 数据同步与校验：

1. 按依赖顺序逐表运行 `astock data sync --table <table>`，避免一次性完整同步连续撞 Tushare API/IP 风控。
2. 运行 `tools/verify_data.py` 获取数据质量报告。
3. 解析校验输出中的 ERROR / WARN。
4. 用清晰的表格 checklist 输出：同步状态、校验状态、问题分类和可能原因。

## 适用场景

当用户表达以下意图时使用本 skill：

- “帮我同步数据并校验”
- “跑一下 A-stock 数据同步流程”
- “检查当前数据是否完整”
- “verify_data 有 WARN/ERROR 帮我分析”
- “同步又遇到 Tushare API error，帮我分表处理”
- “现在数据可以回测到哪天”

## 前置假设

- 当前工作目录是 A-Stock 项目根目录。
- Conda 环境为 `astock`，或者当前 shell 已经能执行 `astock`。
- 本项目使用：
  - `astock data sync --table <table>` 做同步；
  - `tools/verify_data.py` 做数据校验。
- 如果用户只要求分析已有校验输出，不要重新同步。

## 同步顺序

严格按以下顺序逐表同步：

| 顺序 | 表 | 命令 | 依赖 | 说明 |
|---:|---|---|---|---|
| 1 | `stock_basic` | `astock data sync --table stock_basic` | 无 | 股票基础信息；完整同步时内部通常是 full |
| 2 | `trade_cal` | `astock data sync --table trade_cal` | 无 | 交易日历 |
| 3 | `daily` | `astock data sync --table daily` | `stock_basic`, `trade_cal` | 日线行情；最容易触发批量 API 调用 |
| 4 | `adj_factor` | `astock data sync --table adj_factor` | `daily` | 复权因子；技术指标和回测依赖 |
| 5 | `daily_basic` | `astock data sync --table daily_basic` | `daily` | 每日基本面指标 |
| 6 | `suspend_d` | `astock data sync --table suspend_d` | `stock_basic` | 停复牌数据 |
| 7 | `tech_indicator` | `astock data sync --table tech_indicator` | `daily`, `adj_factor` | 本地技术指标计算 |

不要直接运行：

```bash
astock data sync
```

除非用户明确要求。原因：完整同步会连续调用多个 Tushare 接口，之前遇到过 `您的IP数量超限，最大数量为5个！` 等 API/IP 风控问题。逐表同步能降低连续调用强度，并且失败后更容易定位。

## 同步执行策略

### 基本流程

1. 先记录同步前状态：

```bash
astock data status
```

2. 逐表运行：

```bash
astock data sync --table stock_basic
astock data sync --table trade_cal
astock data sync --table daily
astock data sync --table adj_factor
astock data sync --table daily_basic
astock data sync --table suspend_d
astock data sync --table tech_indicator
```

3. 每个命令完成后，记录：
   - OK / FAIL；
   - 同步行数；
   - 是否显示“已是最新”；
   - 错误文本。

4. 如果某个表遇到 Tushare API/IP 错误：
   - 记录失败表、错误文本和发生阶段；
   - 将错误归类为 API/IP 风控或网络出口状态；
   - 如果 `daily` 或 `adj_factor` 失败，标记 `tech_indicator` 存在依赖不完整风险。


## 校验流程

同步完成后运行：

```bash
python tools/verify_data.py
```

如果环境里 `python` 不是 astock 环境，使用：

```bash
/home/hongao/miniconda3/envs/astock/bin/python tools/verify_data.py
```

记录：

- 退出码；
- ERROR 数量；
- WARN 数量；
- 完整可用日期；
- 各表日期范围；
- ERROR/WARN 明细。

## ERROR / WARN 分析规则

### ERROR 处理

ERROR 表示数据不可视为完全通过。常见分类：

| ERROR 文本特征 | 可能原因 | 影响归类 |
|---|---|---|
| `主键重复` | 重复落盘或中断后重跑 | 阻塞数据可信度 |
| `daily 缺失交易日` | daily 同步失败或 trade_cal 超前 | 阻塞日期完整性 |
| `adj_factor 缺失 daily 中的日期` | 复权因子未补齐 | 阻塞复权和技术指标 |
| `daily_basic 缺失` | daily_basic 未补齐 | 影响基本面策略 |
| `daily 核心字段空值` | 行情源字段缺失 | 影响行情计算和回测 |
| `daily OHLC 异常` | 行情价格结构异常 | 影响价格可信度 |
| `adj_factor 空值或非正` | 复权因子异常 | 影响复权价格 |
| `无法找到完整可用日期` | 关键表没有交集 | 阻塞完整策略/回测可用性 |

### WARN 处理

WARN 表示校验通过但需要关注。常见分类：

| WARN 文本特征 | 可能原因 | 影响归类 |
|---|---|---|
| `daily -> tech_indicator 缺失键` | 新股历史窗口不足；或 daily 有股票但 stock_basic 当前股票池没有覆盖（可能是退市股） | 技术指标覆盖缺口 |
| `tech_indicator 核心指标全空` | 新股上市初期，MA/RSI/ATR/MACD 历史窗口不足 | 指标暂不可用 |
| `异常涨跌幅样本` | 新股首日/上市初期、复牌、除权、ST、特殊交易或历史状态缺失 | 异常样本待分类 |
| `最新日期股票数略低` | 当天数据不完整、停牌/接口更新延迟 | 最新日覆盖偏低 |

## WARN 深度归因

当出现 `daily -> tech_indicator 缺失键` 或 `tech_indicator 核心指标全空`：

1. 查询这些股票的历史交易天数。
2. 如果历史天数小于 5 或小于 60，多数是新股窗口不足。
3. 如果历史天数大于 60 且仍缺技术指标，检查：
   - 是否在 `stock_basic` 当前股票池中；
   - 是否为退市/特殊状态股票；
   - `daily + adj_factor` 是否能 join。

当出现 `异常涨跌幅样本`：

1. 先判断是否是上市前 5 个交易日。
2. 再看是否为北交所、科创板、创业板等不同涨跌幅规则。
3. 老股票异常不能直接判错，可能需要除权除息、复牌、ST 状态等额外数据。

## 输出格式

最终回复必须包含以下部分。

### 1. 总结卡片

使用表格：

| 项目 | 结果 |
|---|---|
| 同步模式 | 逐表同步 |
| 同步结论 | 成功 / 部分失败 / 失败 |
| 校验结论 | 通过 / 通过但有 WARN / 未通过 |
| ERROR | 数量 |
| WARN | 数量 |
| 完整可用日期 | YYYYMMDD 或未知 |

### 2. 同步 checklist

| 顺序 | 表 | 状态 | 结果摘要 | 影响归类 |
|---:|---|---|---|---|
| 1 | stock_basic | ✅/⚠️/❌ | 同步行数或错误 | 无影响 / 依赖受阻 / API 风控 |

状态规则：

- ✅：成功或已是最新；
- ⚠️：失败但不阻塞当前目标，或 API 风控可重试；
- ❌：关键表失败，导致依赖链不可用。

### 3. 校验 checklist

| 检查项 | 状态 | 发现 | 原因归类 | 影响归类 |
|---|---|---|---|---|
| 主键重复 | ✅ | 0 | - | 无影响 |
| 日期对齐 | ✅/❌ | ... | 同步缺口 | 日期完整性 |
| 完整可用日期 | ✅ | YYYYMMDD | - | 策略/回测可用边界 |
| 技术指标可用性 | ⚠️ | ... | 新股窗口不足 | 技术指标覆盖 |

### 4. ERROR/WARN 解释表

如果存在 ERROR/WARN，必须附上：

| 级别 | 项 | 样例 | 可能原因 | 是否阻塞 | 影响归类 |
|---|---|---|---|---|---|

如果只有 WARN 且 ERROR=0，明确告诉用户：

```text
当前数据可用，但存在 WARN；WARN 的业务影响取决于策略是否依赖技术指标/异常涨跌幅样本。
```

## 注意事项

- 不要把 WARN 说成同步失败。
- 不要把异常涨跌幅直接判为错误；先考虑新股、复牌、除权、ST、北交所/科创板规则。
- 如果用户只想“检查数据”，不要自动同步。
- 如果用户想“同步并校验”，才执行逐表同步。
- 如果同步失败，不要隐瞒；报告失败表、错误文本和依赖影响。
- 遇到 Tushare IP/API 错误时，将其归类为 API/IP 风控或网络出口状态问题；不要把它描述为数据本身错误。
