# A-Stock 本地数据同步系统 — 设计文档

**日期**: 2026-05-27
**状态**: 待评审

---

## 1. 概述

构建 A 股量化交易系统的第一步：本地数据同步系统。从 Tushare Pro 拉取股票基础数据、行情数据、日历数据，以 Parquet 格式存储，DuckDB 作为查询引擎，CLI（Typer）作为交互入口。

Tushare 积分等级：2000 分。

## 2. 项目结构

```
A_stock/
├── pyproject.toml
├── config.yaml
├── environment.yml
├── README.md
├── .gitignore
├── .claude/
│   ├── CLAUDE.md
│   └── skills/
├── src/astock/
│   ├── __init__.py
│   │
│   ├── core/                # 共享基础设施
│   │   ├── config.py        # YAML -> dataclass
│   │   ├── exceptions.py    # 自定义异常树
│   │   └── logging.py       # 日志配置
│   │
│   ├── data/                # 数据子系统（当前阶段）
│   │   ├── source/          # 数据源层 — Tushare API 封装
│   │   ├── sync/            # 同步层 — 全量/增量 + 级联依赖
│   │   └── store/           # 存储层 — DuckDB + Parquet
│   │
│   ├── strategy/            # 选股策略（未来）
│   ├── backtest/            # 回测引擎（未来）
│   │
│   └── cli/                 # 交互层
│       ├── main.py          # CLI 入口
│       ├── data_cmd.py      # 数据命令
│       ├── config_cmd.py    # 配置命令
│       ├── cal_cmd.py       # 日历命令
│       ├── strategy_cmd.py  # 策略命令（未来占位）
│       └── backtest_cmd.py  # 回测命令（未来占位）
│
├── tests/
│   ├── data/
│   │   ├── test_source.py
│   │   ├── test_sync.py
│   │   └── test_store.py
│   └── conftest.py
│
└── data/                    # 本地数据（gitignore）
    ├── stock_basic/
    ├── trade_cal/
    ├── daily/
    ├── adj_factor/
    ├── daily_basic/
    └── suspend_d/
```

## 3. 数据层设计

### 3.1 数据表


| 表名          | 来源 API      | 积分要求 | 用途                     | 存储策略     |
| ----------- | ----------- | ---- | ---------------------- | -------- |
| stock_basic | stock_basic | 2000 | 股票基础信息（代码、名称、行业、上市日期等） | 全量替换     |
| trade_cal   | trade_cal   | 2000 | 交易日历                   | 按年增量追加   |
| daily       | daily       | 基础   | 日线行情（未复权 OHLCV）        | 按交易日增量追加 |
| adj_factor  | adj_factor  | 2000 | 复权因子                   | 按日期增量追加  |
| daily_basic | daily_basic | 2000 | 每日指标（PE/PB/市值/换手率等）    | 按交易日增量追加 |
| suspend_d   | suspend_d   | 待确认  | 停复牌记录                  | 按日期增量追加  |


### 3.2 同步流程（依赖顺序）

```
Step 1: sync stock_basic  -> 全量替换，获取最新股票列表（无依赖）
Step 2: sync trade_cal    -> 增量追加，确保交易日历完整（无依赖）
Step 3: sync daily        -> 按交易日增量，跳过停牌股（依赖 stock_basic, trade_cal）
Step 4: sync adj_factor   -> 按交易日增量，用于复权计算（依赖 daily）
Step 5: sync daily_basic  -> 按交易日增量，补充估值指标（依赖 daily）
Step 6: sync suspend_d    -> 按日期增量，记录停复牌（依赖 stock_basic）
```

### 3.3 级联同步检查

单表同步时自动检查依赖表的数据状态。如果依赖表滞后，自动先更新依赖表后再执行目标表同步。

示例：

- `data sync --table daily` -> 先检查 stock_basic 和 trade_cal 是否最新 -> 自动更新滞后的依赖表 -> 再同步 daily
- `data sync --table stock_basic` -> 无依赖，直接同步

CLI 输出展示实际同步了哪些表及原因。

### 3.4 边界场景处理


| 场景        | 处理策略                                          |
| --------- | --------------------------------------------- |
| 新股（IPO）   | 上市日期前无 daily 数据 -> 正常跳过，不告警                   |
| 退市股票      | 退市日期后无数据 -> 正常跳过，历史数据保留                       |
| 停牌股票      | 停牌期间无 daily/basic 数据 -> 通过 suspend_d 标记，不误报缺失 |
| 涨跌停/异常波动  | 通过 daily.pct_chg 检测（A股 ±10% / 创业板科创板 ±20%）    |
| 除权除息      | daily 为未复权，通过 adj_factor 计算前后复权价格             |
| 股票更名/代码变更 | 暂不处理（后续可通过 namechange API 补充）                 |
| API 超时/限流 | 自动重试 + 指数退避，记录失败供 sync 结束汇总                   |


## 4. CLI 命令设计

```
astock
├── config show              # 查看当前配置
├── config set <key> <val>   # 修改配置项
│
├── data sync                # 一键同步所有数据（按依赖顺序）
├── data sync --table <t>    # 指定单表同步（自动级联检查依赖）
│   └── --mode full|inc      # 同步模式（默认 inc）
├── data status              # 各表数据状态概览
├── data query <table>       # 查询数据 (--filter --limit --export)
├── data clean --table <t>   # 清理指定表（需确认）
│
└── cal show [date]          # 查看指定日期是否交易日
```

## 5. 配置设计

### config.yaml

```yaml
tushare:
  token: "${TUSHARE_TOKEN}"

storage:
  data_dir: "data/"
  db_path: "data/astock.duckdb"

sync:
  batch_size: 5000
  retry: 3
  retry_delay: 5

log:
  level: "INFO"
  file: "logs/astock.log"
```

- `${TUSHARE_TOKEN}` 从环境变量读取，敏感信息不进仓库
- 加载优先级：环境变量 > config.yaml > 默认值
- 通过 `Config` dataclass 单例加载

## 6. 异常体系

```
AStockError (base)
├── ConfigError      # 配置错误（缺少 token、路径无效）
├── APIError         # Tushare API 错误（含状态码和原始响应）
├── StoreError       # 存储层错误（IO 错误、数据损坏）
└── SyncError        # 同步逻辑错误（依赖断裂、数据不一致）
```

异常处理策略：

- source 层：API 超时/限流 -> 重试 + 指数退避，仍失败 -> 抛 APIError
- sync 层：捕获 APIError，记录失败项，继续处理后续，结束后输出汇总
- store 层：写入失败 -> 抛 StoreError，使用临时文件 + rename 保证原子性
- cli 层：捕获所有异常 -> 友好消息 + 非零退出码

## 7. 技术栈


| 用途         | 选型                                             |
| ---------- | ---------------------------------------------- |
| 语言         | Python >= 3.11                                 |
| 包管理        | conda (environment.yml) + pip (pyproject.toml) |
| CLI        | Typer                                          |
| 配置         | YAML (PyYAML)                                  |
| 数据源        | Tushare Pro SDK                                |
| 数据处理       | Pandas                                         |
| Parquet 读写 | PyArrow                                        |
| 数据库查询      | DuckDB                                         |
| 测试         | pytest + pytest-cov                            |
| 版本管理       | Git                                            |


## 8. 非目标（当前阶段不做）

- namechange（股票更名）API 集成 — 待下一版本
- 前后复权价格计算 — sync 层只存原始 adj_factor，计算逻辑放在 strategy 层
- 策略选股、回测引擎 — 架构预留，功能后续实现
- 实时行情、分钟线 — 需更高积分等级

