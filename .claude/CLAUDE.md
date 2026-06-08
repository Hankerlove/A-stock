# A-Stock Project Context

## 项目概述

A 股量化交易系统。Phase 1 数据同步 + Phase 2 策略回测已完成。

## 技术栈

- Python >= 3.11
- Conda 环境管理
- Tushare Pro (2000 积分) 数据源
- DuckDB + Parquet 本地存储
- Typer CLI
- pytest 测试
- pandas + numpy（因子计算与回测）

## 关键文件

- `config.yaml` — 配置文件（含 Tushare token，通过环境变量注入）
- `src/astock/core/` — 共享基础设施（Config, 异常体系, 日志）
- `src/astock/data/source/` — Tushare API 客户端（含指数退避重试）
- `src/astock/data/sync/` — 同步管理器（7 表级联依赖，日期原子化保存，安全截止日期探测）
- `src/astock/data/store/` — DuckDB + Parquet 存储层（含去重，union_by_name）
- `src/astock/data/indicator/` — 技术指标计算（纯 numpy，前复权，7 类指标）
- `src/astock/strategy/` — 选股策略模块（注册表、因子库、4 个内置策略）
- `src/astock/backtest/` — 回测引擎（T+1 调仓、成本模拟、绩效指标）
- `src/astock/cli/` — Typer 命令入口（config/data/strategy/backtest 四组子命令）
- `tools/verify_data.py` — 数据完整性校验脚本（5 项检查，双向日期对齐）
- `tools/deduplicate.py` — 按主键去重脚本（7 表全覆盖）
- `tools/queries/volume_breakout.py` — 成交量倍量查询脚本
- `docs/superpowers/specs/` — 设计文档
- `docs/superpowers/plans/` — 实施计划

## 当前阶段

Phase 1 (数据同步) + Phase 2 (策略回测) 已完成。

### 数据表（7 张）
stock_basic, trade_cal, daily, adj_factor, daily_basic, suspend_d, tech_indicator

### 同步关键设计
- **安全截止日期**: `_get_safe_today()` 通过探测 Tushare daily API（000001.SZ）确定所有表统一的同步截止日，避免 trade_cal/suspend_d 超前 daily
- **增量同步**: `_get_trade_days_since()` 对 trade_cal 的 SSE/SZSE 重复日期去重，防止每日期同步两次
- **级联依赖**: 单表同步自动检查并更新依赖表

### 内置策略（4 个）
- `dividend-low-vol` — 红利低波：高股息率 + 低波动率
- `value-low-vol` — 价值低波：低 PB + 低 PE + 低波动
- `momentum-reversal` — 动量反转：中期趋势 + 短期回调
- `volume-price-breakout` — 量价突破：价格突破前高 + 成交量放大

### 回测引擎
- T+1 开盘价执行（T 日收盘后生成信号）
- 佣金（双边 0.03%）、印花税（卖出 0.05%）、滑点（0.05%）
- 停牌/涨跌停不可交易过滤
- 整数手（100 股）约束
- 日/周/月调仓频率
- 输出：权益曲线、交易明细、总收益/年化收益/最大回撤/夏普比率/换手率

## 未来阶段

- Phase 3: 更多策略（技术指标策略、多因子合成、ML/DL/LLM）
- 策略参数优化
- 实盘模拟

## 协作规范

- 使用中文回答
- 修改文件后，简要说明修改内容和目的
- 遇到功能更新或者变更，需要及时更新README.md文件

## 运行方式

1. `conda activate astock`
2. `export TUSHARE_TOKEN="xxx"`
3. `astock data sync` — 同步数据
4. `astock data status` — 查看状态
5. `astock strategy list` — 列出策略
6. `astock strategy signals --date 20240131` — 生成信号
7. `astock backtest run --start 20200101 --end 20231231` — 回测

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
