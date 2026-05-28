# A-Stock Project Context

## 项目概述

A 股量化交易系统。第一阶段：本地数据同步系统。

## 技术栈

- Python >= 3.11
- Conda 环境管理
- Tushare Pro (2000 积分) 数据源
- DuckDB + Parquet 本地存储
- Typer CLI
- pytest 测试

## 关键文件

- `config.yaml` — 配置文件（含 Tushare token，通过环境变量注入）
- `src/astock/core/` — 共享基础设施（Config, 异常体系, 日志）
- `src/astock/data/source/` — Tushare API 客户端（含指数退避重试）
- `src/astock/data/sync/` — 同步管理器（6 表级联依赖，日期原子化保存）
- `src/astock/data/store/` — DuckDB + Parquet 存储层（含去重）
- `src/astock/cli/` — Typer 命令入口（config/data/cal/strategy/backtest 五组子命令）
- `tools/verify_data.py` — 数据完整性校验脚本（5 项检查）
- `tools/deduplicate.py` — 按主键去重脚本（用户自维护）
- `docs/superpowers/specs/` — 设计文档
- `docs/superpowers/plans/` — 实施计划

## 当前阶段

Phase 1: 数据同步系统（进行中）
- 6 张核心表：stock_basic, trade_cal, daily, adj_factor, daily_basic, suspend_d
- 级联依赖检查：单表同步自动更新依赖表
- 边界处理：停牌/退市/新股/除权除息

## 未来阶段

- Phase 2: 选股策略（ML/DL/LLM）
- Phase 3: 回测引擎

## 协作规范

- 使用中文回答
- 修改文件后，简要说明修改内容和目的

## 运行方式

1. `conda activate astock`
2. `export TUSHARE_TOKEN="xxx"`
3. `astock data sync` — 同步数据
4. `astock data status` — 查看状态

## 测试与校验

```bash
# 运行测试
pytest -v
pytest --cov=astock --cov-report=term-missing

# 数据完整性校验
python tools/verify_data.py

# 去重
python tools/deduplicate.py
```

## Tushare API 已知问题

- **daily 接口 ts_code 上限 1000**（非文档声明的 5000），代码已在 `_sync_daily` 中硬截断 `min(batch_size, 1000)`
- **频率限制 200次/分钟/接口**，代码中所有 API 调用后有 `time.sleep(0.4)`（约 150次/分钟）
- **`is_open` 字段返回 BIGINT (1/0)**，不是 VARCHAR，比较时需处理两种类型 `in (1, "1")`
- **`read_parquet` 需加 `union_by_name=true`**，否则不同 parquet 文件间列类型不一致时 DuckDB 报类型转换错误
