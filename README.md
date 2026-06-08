# A-Stock 量化交易系统

A 股本地数据同步、选股策略和回测系统。从 [Tushare Pro](https://tushare.pro) 拉取股票数据，以 Parquet + DuckDB 本地存储，通过 CLI 执行数据管理、策略信号和中低频回测。

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

# 列出内置策略
astock strategy list

# 查看策略参数
astock strategy explain dividend-low-vol
astock strategy explain momentum-reversal
astock strategy explain value-low-vol
astock strategy explain volume-price-breakout

# 生成某日策略目标权重
astock strategy signals --strategy dividend-low-vol --date 20240131 --top-n 20 --lookback-days 60
astock strategy signals --strategy momentum-reversal --date 20240131 --momentum-window 60 --reversal-window 5
astock strategy signals --strategy volume-price-breakout --date 20240131 --breakout-window 20 --volume-multiplier 2.0

# 运行 T+1 回测
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

# 查看配置
astock config show
```

## 数据表


| 表名             | 内容                                | 进度   |
| -------------- | --------------------------------- | ---- |
| stock_basic    | 股票基础信息                            | Done |
| trade_cal      | 交易日历                              | Done |
| daily          | 日线行情（未复权）                         | Done |
| adj_factor     | 复权因子                              | Done |
| daily_basic    | 每日指标（PE/PB等）                      | Done |
| suspend_d      | 停复牌记录                             | Done |
| tech_indicator | 技术指标（前复权 MACD/KDJ/RSI/MA/布林带/ATR） | Done |


## 策略与回测

### 策略列表


| 策略    | 名称                    | 核心口径                |
| ----- | --------------------- | ------------------- |
| 红利低波  | dividend-low-vol      | 高股息、低波动、成交额过滤       |
| 价值低波  | value-low-vol         | 低 PB、低 PE、低波动、成交额过滤 |
| 动量/反转 | momentum-reversal     | 中期趋势、短期回调、成交额过滤     |
| 量价突破  | volume-price-breakout | 价格突破前高、成交量放大、涨幅确认   |


`astock strategy explain <策略名>` 会输出每个策略参数的默认值和中文解释。
策略参数也可以在 `astock strategy signals` 和 `astock backtest run` 中通过同名 CLI 选项传入。CLI 会根据当前 `--strategy` 自动筛选该策略支持的参数；没有显式传入的可选权重参数使用策略类中的默认值。

### 通用策略参数

这些参数在多个策略中复用：


| CLI 参数                   | 中文名称    | 默认值   | 说明                    |
| ------------------------ | ------- | ----- | --------------------- |
| `--top-n`                | 持仓股票数量  | `20`  | 按综合得分从高到低选取前 N 只股票。   |
| `--min-amount`           | 成交额过滤下限 | `0.0` | 低于该成交额的股票不参与打分。       |
| `--max-weight-per-stock` | 单票权重上限  | 空     | 限制单只股票最大目标权重；为空表示不限制。 |


### 红利低波策略参数

策略名：`dividend-low-vol`


| CLI 参数                   | 中文名称     | 默认值   | 说明              |
| ------------------------ | -------- | ----- | --------------- |
| `--top-n`                | 持仓股票数量   | `20`  | 按综合得分从高到低选取。    |
| `--lookback-days`        | 波动率回看窗口  | `60`  | 使用前复权收盘价计算收益波动。 |
| `--min-amount`           | 成交额过滤下限  | `0.0` | 过滤流动性不足的股票。     |
| `--dividend-weight`      | 股息率因子权重  | `0.6` | 越高越偏好高股息股票。     |
| `--volatility-weight`    | 波动率惩罚权重  | `0.4` | 越高越严格惩罚高波动股票。   |
| `--value-weight`         | 估值辅助因子权重 | `0.0` | 使用 PB 低估值排名。    |
| `--max-weight-per-stock` | 单票权重上限   | 空     | 为空表示不限制。        |


示例：

```bash
astock backtest run \
  --strategy dividend-low-vol \
  --start 20200101 \
  --end 20231231 \
  --top-n 20 \
  --lookback-days 60 \
  --dividend-weight 0.6 \
  --volatility-weight 0.4
```

### 价值低波策略参数

策略名：`value-low-vol`


| CLI 参数                   | 中文名称      | 默认值    | 说明                        |
| ------------------------ | --------- | ------ | ------------------------- |
| `--top-n`                | 持仓股票数量    | `20`   | 按综合得分从高到低选取。              |
| `--lookback-days`        | 波动率回看窗口   | `60`   | 使用前复权收盘价计算收益波动。           |
| `--min-amount`           | 成交额过滤下限   | `0.0`  | 过滤流动性不足的股票。               |
| `--pb-weight`            | 低 PB 因子权重 | `0.45` | 越高越偏好 PB 更低的股票。           |
| `--pe-weight`            | 低 PE 因子权重 | `0.35` | 优先使用 `pe_ttm`，缺失时使用 `pe`。 |
| `--volatility-weight`    | 波动率惩罚权重   | `0.2`  | 越高越严格惩罚高波动股票。             |
| `--market-cap-weight`    | 小市值倾斜权重   | `0.0`  | 使用 `total_mv` 低市值排名。      |
| `--max-weight-per-stock` | 单票权重上限    | 空      | 为空表示不限制。                  |


示例：

```bash
astock backtest run \
  --strategy value-low-vol \
  --start 20200101 \
  --end 20231231 \
  --pb-weight 0.45 \
  --pe-weight 0.35 \
  --volatility-weight 0.2
```

### 动量/反转策略参数

策略名：`momentum-reversal`


| CLI 参数                   | 中文名称    | 默认值   | 说明                            |
| ------------------------ | ------- | ----- | ----------------------------- |
| `--top-n`                | 持仓股票数量  | `20`  | 按综合得分从高到低选取。                  |
| `--momentum-window`      | 中期动量窗口  | `60`  | 计算短期反转窗口之前的前复权收益。             |
| `--reversal-window`      | 短期反转窗口  | `5`   | 近期跌幅越大，反转得分越高。                |
| `--skip-days`            | 跳过交易日数量 | `0`   | 动量窗口与当前日期之间跳过的交易日数量，用于降低短期噪声。 |
| `--min-amount`           | 成交额过滤下限 | `0.0` | 过滤流动性不足的股票。                   |
| `--momentum-weight`      | 中期动量权重  | `0.7` | 越高越偏好过去中期走势更强的股票。             |
| `--reversal-weight`      | 短期反转权重  | `0.3` | 越高越偏好近期回撤后的修复机会。              |
| `--volatility-weight`    | 波动率惩罚权重 | `0.0` | 越高越严格惩罚高波动股票。                 |
| `--max-weight-per-stock` | 单票权重上限  | 空     | 为空表示不限制。                      |


示例：

```bash
astock backtest run \
  --strategy momentum-reversal \
  --start 20200101 \
  --end 20231231 \
  --momentum-window 60 \
  --reversal-window 5 \
  --momentum-weight 0.7 \
  --reversal-weight 0.3
```

### 量价突破策略参数

策略名：`volume-price-breakout`


| CLI 参数                     | 中文名称      | 默认值   | 说明                |
| -------------------------- | --------- | ----- | ----------------- |
| `--top-n`                  | 持仓股票数量    | `20`  | 按综合得分从高到低选取。      |
| `--breakout-window`        | 价格突破窗口    | `20`  | 当前前复权收盘价需突破窗口内前高。 |
| `--volume-window`          | 成交量均值窗口   | `5`   | 用于计算当前成交量放大倍数。    |
| `--volume-multiplier`      | 成交量放大阈值   | `2.0` | 当前成交量需达到过去均量的倍数。  |
| `--min-pct-chg`            | 当日最小涨跌幅   | `0.0` | 过滤无价格确认的放量。       |
| `--min-amount`             | 成交额过滤下限   | `0.0` | 过滤流动性不足的股票。       |
| `--price-breakout-weight`  | 价格突破强度权重  | `0.6` | 越高越偏好突破幅度更大的股票。   |
| `--volume-breakout-weight` | 成交量放大强度权重 | `0.4` | 越高越偏好量能确认更强的股票。   |
| `--max-weight-per-stock`   | 单票权重上限    | 空     | 为空表示不限制。          |


示例：

```bash
astock backtest run \
  --strategy volume-price-breakout \
  --start 20200101 \
  --end 20231231 \
  --breakout-window 20 \
  --volume-window 5 \
  --volume-multiplier 2.0 \
  --price-breakout-weight 0.6 \
  --volume-breakout-weight 0.4
```

### 回测参数

回测口径：

- T 日收盘后生成信号，T+1 交易日开盘执行。
- 使用前复权价格估值；持仓股票在交易日缺少当日行情时，按上一可用前复权收盘价结转估值，不把持仓市值临时计为 0。
- 交易成本通过参数传入：`commission_rate`、`stamp_duty_rate`、`slippage_rate`、`min_commission`、`lot_size`。
- 默认阻止停牌交易，并按 T+1 开盘价相对昨收价近似阻止涨停买入、跌停卖出。
- 策略只生成目标权重，回测引擎负责成本、可交易性和绩效指标。
- `--initial-cash` 是回测账户初始资金，也是 `total_return` 的分母；在存在整手约束、最低佣金和现金不足约束时，初始资金不只是缩放参数，可能影响实际成交股数和最终收益。

回测命令的基本结构：

```bash
astock backtest run \
  --strategy <策略名> \
  --start <开始日期> \
  --end <结束日期> \
  [策略参数] \
  [回测参数]
```

回测通用参数：


| CLI 参数                                       | 中文名称     | 默认值                | 说明                             |
| -------------------------------------------- | -------- | ------------------ | ------------------------------ |
| `--strategy` / `-s`                          | 策略名称     | `dividend-low-vol` | 指定要回测的策略；一次命令回测一个策略。           |
| `--start`                                    | 开始日期     | 必填                 | 回测开始日期，格式 `YYYYMMDD`。          |
| `--end`                                      | 结束日期     | 必填                 | 回测结束日期，格式 `YYYYMMDD`。          |
| `--initial-cash`                             | 初始资金     | `1000000`          | 回测初始现金。                        |
| `--rebalance-frequency`                      | 换仓频率     | `monthly`          | 可选 `daily`、`weekly`、`monthly`。 |
| `--commission-rate`                          | 佣金费率     | `0.0003`           | 买入和卖出都计入。                      |
| `--stamp-duty-rate`                          | 卖出印花税率   | `0.0005`           | 仅卖出时计入。                        |
| `--slippage-rate`                            | 滑点率      | `0.0005`           | 买入按更高成交价、卖出按更低成交价估算。           |
| `--min-commission`                           | 最低佣金     | `5.0`              | 单笔交易最低佣金。                      |
| `--lot-size`                                 | 交易手数     | `100`              | 买入和卖出按手数取整。                    |
| `--enforce-suspend` / `--no-enforce-suspend` | 停牌约束     | 开启                 | 开启时阻止停牌股票成交。                   |
| `--enforce-limit` / `--no-enforce-limit`     | 涨跌停约束    | 开启                 | 开启时近似阻止涨停买入、跌停卖出。              |
| `--config` / `-c`                            | 配置文件路径   | `config.yaml`      | 读取本地数据存储配置。                    |
| `--output-equity`                            | 权益曲线导出路径 | 空                  | 传入后导出权益曲线 CSV。                 |
| `--output-trades`                            | 交易明细导出路径 | 空                  | 传入后导出交易明细 CSV。                 |


策略参数同名导入示例：

```bash
# 生成某天目标权重
astock strategy signals \
  --strategy volume-price-breakout \
  --date 20260601 \
  --breakout-window 20 \
  --volume-window 5 \
  --volume-multiplier 2.0

# 使用同一组策略参数做回测
astock backtest run \
  --strategy volume-price-breakout \
  --start 20200101 \
  --end 20231231 \
  --breakout-window 20 \
  --volume-window 5 \
  --volume-multiplier 2.0 \
  --rebalance-frequency weekly \
  --initial-cash 1000000
```

### 回测结果指标

回测完成后终端会输出以下 6 项绩效指标：

| 指标               | 英文名           | 公式                                                                                | 含义                                                                                                                               |
| ------------------ | ---------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 总收益率           | `total_return`   | $\frac{\text{Equity}_{end}}{\text{Cash}_{initial}} - 1$                             | 回测期间权益从初始资金到最终权益的总涨跌幅度。正数表示盈利，负数表示亏损。                                                          |
| 年化收益率         | `annual_return`  | $(1 + R_{total})^{\frac{252}{N}} - 1$                                               | 将总收益率按复利折算为年化口径，便于不同回测时长的横向比较。其中 $N$ 为回测区间内的交易日数，252 为年度交易日近似值。                |
| 最大回撤           | `max_drawdown`   | $\min\left(\frac{\text{Equity}_t}{\max_{s \le t} \text{Equity}_s} - 1\right)$       | 权益曲线从历史最高点到后续最低点的最大跌幅百分比。衡量策略在不利时期可能承受的最大亏损，是风控的核心指标。值越小（越接近 0）越好。    |
| 夏普比率           | `sharpe`         | $\frac{\bar{r}_{daily}}{\sigma_{daily}} \times \sqrt{252}$                          | 年化风险调整后收益。分子为日均收益率，分母为日收益率标准差，乘以 $\sqrt{252}$ 年化。衡量每承担一单位波动风险所获得的超额回报。     |
| 换手率             | `turnover`       | $\frac{\sum \vert \text{GrossAmount} \vert}{\text{mean(Equity)}}$                   | 回测期间所有交易的总成交金额（买入+卖出绝对值）除以平均权益。衡量资金周转频率：换手率越高表示调仓越频繁，交易成本影响越大。          |
| 交易笔数           | `trade_count`    | $\text{len(trades)}$                                                                | 回测期间实际执行的交易总笔数（每笔买入或卖出记为 1 笔）。                                                                           |

> **如何解读这些指标**：
> - 最直观看**总收益率**和**最大回撤**：收益率高但回撤也大，说明策略波动大、风险高。
> - **夏普比率**综合了收益和风险：> 1 较好，> 2 优秀，< 0.5 说明收益不足以覆盖波动。
> - **换手率**帮助判断交易频率是否合理：例如月频调仓策略换手率通常在个位数，如果显著偏高需要检查参数。
> - 所有指标应结合回测区间和市场环境综合判断，单看任何一个都有局限性。

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
│   │   └── indicator/       # 技术指标计算（前复权）
│   ├── strategy/            # 选股策略（红利低波/价值低波/动量反转/量价突破）
│   ├── backtest/            # T+1 回测引擎
│   └── cli/                 # CLI 命令入口
├── tests/                   # 测试文件
├── data/                    # 本地数据库（gitignore）
```

## 开发

```bash
# 运行测试
pytest -v

# 测试覆盖率
pytest --cov=astock --cov-report=term-missing
```

## 免责声明

策略和回测模块用于研究与工程验证，不构成任何投资建议。真实使用前需要独立验证数据完整性、成本假设、股票池口径、停牌/涨跌停约束和参数稳健性。

## 许可证

MIT
