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
- `src/astock/core/` — 共享基础设施
- `src/astock/data/source/` — Tushare API 客户端
- `src/astock/data/sync/` — 同步管理器（含级联依赖）
- `src/astock/data/store/` — DuckDB + Parquet 存储层
- `src/astock/cli/` — Typer 命令入口
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

## 运行方式

1. `conda activate astock`
2. `export TUSHARE_TOKEN="xxx"`
3. `astock data sync` — 同步数据
4. `astock data status` — 查看状态
