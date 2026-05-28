# A-Stock 量化交易数据系统

A 股本地数据同步系统。从 [Tushare Pro](https://tushare.pro) 拉取股票数据，以 Parquet + DuckDB 本地存储，CLI 交互。

## 环境准备

```bash
# 1. 安装 conda 环境
conda env create -f environment.yml
conda activate astock

# 2. 安装 astock 包
pip install -e .

# 3. 设置 Tushare Token（需在 https://tushare.pro 注册获取）
export TUSHARE_TOKEN="your_token_here"

# 4. 验证
astock --help
```

## 快速开始

```bash
# 一键全量同步（首次运行）
astock data sync

# 查看数据状态
astock data status

# 查询股票列表
astock data query stock_basic --limit 20

# 查看交易日历
astock cal show 20240102

# 查看配置
astock config show
```

## 数据表

| 表名 | 内容 | 进度 |
|------|------|----------|
| stock_basic | 股票基础信息 | Done |
| trade_cal | 交易日历 | Done |
| daily | 日线行情（未复权） | Done |
| adj_factor | 复权因子 | Done |
| daily_basic | 每日指标（PE/PB等） | Done |
| suspend_d | 停复牌记录 | Done |

## 项目结构

```
A_stock/
├── config.yaml              # 配置文件
├── environment.yml          # Conda 环境
├── pyproject.toml           # 包配置
├── src/astock/
│   ├── core/                # 基础设施（配置/异常/日志）
│   ├── data/
│   │   ├── source/          # Tushare API 封装
│   │   ├── sync/            # 同步策略（全量/增量+级联）
│   │   └── store/           # DuckDB + Parquet 存储
│   ├── strategy/            # 选股策略（未来）
│   ├── backtest/            # 回测引擎（未来）
│   └── cli/                 # CLI 命令入口
├── tests/                   # 测试
├── data/                    # 本地数据库（gitignore）
└── docs/                    # 设计文档
```

## 开发

```bash
# 运行测试
pytest -v

# 测试覆盖率
pytest --cov=astock --cov-report=term-missing
```

## 许可证

MIT
