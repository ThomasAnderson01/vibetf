# esim Tutorial

这份文档讲 7 件事：

1. 从哪里开始读代码
2. 怎么运行最小示例
3. 会得到什么结果
4. 如何替换成真实 ETF 数据
5. 如何用步骤化 pipeline 自定义流程
6. 如何跑多因子实验并落盘
7. 如何跑 tests

---

## 1. 先从哪里开始

如果你第一次接触 `research\esim`，建议按这个顺序看：

1. `research\esim\example_run.py`
2. `research\esim\pipeline.py`
3. `research\esim\factors.py`
4. `research\esim\portfolio.py`
5. `research\esim\composite.py`
6. `research\esim\LEAKAGE_CHECKLIST.md`

原因很简单：

- `example_run.py` 告诉你最小可运行入口是什么
- `pipeline.py` 告诉你整条研究流水线怎么串起来——现在是**可组合步骤**设计，每步是独立的 `Step` 函数
- `factors.py` 告诉你因子是怎么定义和注册的
- `portfolio.py` 告诉你交易评估和选券策略是怎么做的
- `composite.py` 告诉你多因子合成方法是怎么注册和切换的

如果只想抓主线，不想一次看太多代码，**先盯住 `run_factor_study(...)` 或 `StudyPipeline`** 就够了。

---

## 2. 最小示例怎么运行

在仓库根目录执行：

```powershell
python -m research.esim
```

这个命令会进入：

- `research\esim\__main__.py`
- 然后调用 `research\esim\example_run.py`

示例内部做了这些事：

1. 用 `make_sample_stock_etf_daily_data()` 生成一份合成股票 ETF 日线样本
2. 配置一组因子，例如 `momentum`、`fdr`、`vcr`、`rstd1m`、`tvr1m`、`liquidity_quality`
3. 调用 `run_factor_study(...)`
4. 打印一个示例因子的评估结果

当前示例默认设置：

- `horizons=(1, 2, 5, 20)`
- `quantiles=5`
- `min_history=60`
- `return_column="fwd_ret_5d"`
- `rebalance_freq_days=5`

也就是说：

- 预测能力默认看 **1/2/5/20 日**
- 组合回测默认看 **5 日持有 / 5 日调仓**

---

## 3. `run_factor_study(...)` 做了什么

`run_factor_study(...)` 是整个框架最核心的快捷入口，内部用 `StudyPipeline` 按默认步骤顺序执行。

调用形式大致是：

```python
results = run_factor_study(
    daily_bars=sample_bars,
    factor_specs=[
        FactorSpec(name="fdr"),
        FactorSpec(name="vcr"),
        FactorSpec(name="rstd1m"),
        FactorSpec(name="tvr1m"),
    ],
    research_config=ResearchConfig(
        horizons=(1, 2, 5, 20),
        quantiles=5,
        min_history=60,
        min_avg_amount_100m=1.0,
    ),
    portfolio_config=PortfolioConfig(
        top_n=10,
        cost_bps=5.0,
        return_column="fwd_ret_5d",
        rebalance_freq_days=5,
    ),
)
```

它内部等价于：

```python
pipeline = StudyPipeline([
    load_data(sample_bars),
    *DEFAULT_STUDY_STEPS,
])
result = pipeline.run(StudyContext(factor_specs=[...], research_config=..., portfolio_config=...))
```

其中 `DEFAULT_STUDY_STEPS` 依次包含 6 个步骤：

1. **prepare_bars** — 标准化 `trade_date`、去重、排序、过滤股票 ETF、计算 `daily_return` 和流动性门槛
2. **compute_factors** — 计算原始因子值
3. **add_labels** — 计算 future return（默认 `t+1 open -> t+1+h open`）
4. **filter_eligible** — 只保留可交易样本
5. **normalize_factors** — 截面 winsorize + z-score
6. **evaluate_factors** — IC / 分位 / 自相关 / 组合评价

---

## 4. 运行后会得到什么结果

`run_factor_study(...)` 返回的是一个 `StudyResult`。

你可以这样取某个因子的结果：

```python
factor = results.get_factor("fdr")
```

这个 `factor` 是一个 `FactorResult`，里面主要有几类结果。

### 4.1 预测能力结果

```python
factor.ic_summary[1]
factor.ic_summary[5]
```

表示某个因子对未来 1 日、5 日收益的 IC 摘要，常看：

- `mean`
- `ir`
- `positive_ratio`
- `t_stat`
- `nw_t_stat`

### 4.2 分层收益结果

```python
factor.quantile_summary[5]
```

常看：

- 各 quantile 的平均收益
- `top_minus_bottom`

如果高分组显著高于低分组，通常说明排序方向更合理。

### 4.3 因子稳定性结果

```python
factor.autocorrelation_summary
```

常看：

- `mean`
- `median`

它反映信号衰减速度。越高通常表示信号越稳，但也可能意味着它更慢、更像风格暴露。

### 4.4 交易评估结果

```python
factor.portfolio_summary
```

当前常见字段包括：

- `annualized_return`
- `annualized_volatility`
- `sharpe`
- `max_drawdown`
- `avg_turnover`
- `benchmark_annualized_return`
- `annualized_excess_return`
- `tracking_error`
- `information_ratio`
- `beta`

这部分对应的是“如果真的按因子做 Top-N 组合，会表现成什么样”。

---

## 5. 怎么理解这两层评估

可以把框架分成两层：

### 第一层：预测能力

看的是因子有没有横截面区分能力：

- IC
- quantile spread
- autocorrelation

这层回答的问题是：

> 这个因子能不能把未来更强的 ETF 排在前面？

### 第二层：交易表现

看的是如果把因子变成组合，表现如何：

- return
- sharpe
- max drawdown
- turnover
- excess return

这层回答的问题是：

> 这个因子能不能转成一个值得继续研究的策略？

一般来说：

- **先看 IC / spread**
- **再看组合表现**

因为有些因子统计上有效，但换手过高、成本后不赚钱。

---

## 6. 如何替换成真实 ETF 数据

你不一定要用 `sample_data.py`。

只要你的真实数据满足最小字段要求，就可以直接喂给 `run_factor_study(...)`。

### 6.1 最低必需字段

你的数据至少需要这些列：

| 字段 | 含义 |
| --- | --- |
| `trade_date` | 交易日 |
| `ts_code` | ETF 代码 |
| `open` | 开盘价 |
| `high` | 最高价 |
| `low` | 最低价 |
| `close` | 收盘价 |
| `vol` | 成交量 |
| `amount` | 成交额 |

可选列：

- `asset_type`
- `stock_subtype`
- `extname`
- `mgr_name`
- `index_name`

### 6.2 直接传 DataFrame

```python
import pandas as pd

from research.esim.config import FactorSpec, PortfolioConfig, ResearchConfig
from research.esim.pipeline import run_factor_study

bars = pd.read_csv("your_stock_etf_daily.csv")

results = run_factor_study(
    daily_bars=bars,
    factor_specs=[
        FactorSpec(name="fdr"),
        FactorSpec(name="vcr"),
        FactorSpec(name="rstd1m"),
    ],
    research_config=ResearchConfig(
        horizons=(1, 2, 5, 20),
        quantiles=5,
        min_history=60,
        min_avg_amount_100m=1.0,
    ),
    portfolio_config=PortfolioConfig(
        top_n=10,
        cost_bps=5.0,
        return_column="fwd_ret_5d",
        rebalance_freq_days=5,
    ),
)
```

### 6.3 直接传文件路径

也可以直接传 CSV / Parquet 路径：

```python
from pathlib import Path

results = run_factor_study(
    daily_bars=Path("your_stock_etf_daily.csv"),
    factor_specs=[FactorSpec(name="fdr")],
)
```

---

## 7. 如何跑多因子实验并落盘

如果你想像 `alphaflow` 一样直接跑实验并把结果写到目录，入口是：

```powershell
python research\esim\run_research.py --start-date 20260101 --end-date 20260514
```

默认会读取：

- `data\raw\dmgr\tushare\fund_daily`
- `research\outputs\etf_liquidity_snapshot_20260514.csv`

默认会做：

1. 加载真实 ETF 日频数据
2. 运行单因子研究
3. 运行多因子合成
4. 把结果统一写到 `research\esim\output\...`

### 7.1 多因子合成怎么配

当前已经支持两种：

- `equal`
- `rolling_ic`

其中 `rolling_ic` 的权重只会使用**已经完全实现**的 IC 历史，不会把尚未走完持有期的 future return 提前用进来。

这里的关键点是：`CompositeConfig.method` 现在对应的是一个**合成方法注册键**，不是写死在 `run_experiment(...)` 里的分支逻辑。也就是说，后续新增 `orthogonalized_equal`、`bucket_neutralized` 之类的方法时，应该直接扩展 `composite.py`，而不是继续把逻辑塞回 experiment 层。

例如：

```powershell
python research\esim\run_research.py ^
  --factors fdr,vcr,rstd1m ^
  --composite-method rolling_ic ^
  --ic-horizon 5 ^
  --ic-lookback 20
```

如果你要把 `tvr1m` 跑在真实 ETF 数据上，数据里需要有点时规模。当前 `data.load_real_etf_dataset()` 会自动尝试从 `fund_share` 分区目录合并 `fd_share`，并在因子内部用 `fd_share * close` 推导 `cap_100m`；如果你自己已经准备了 `cap_100m` 列，也可以直接用。

### 7.2 会输出什么

输出目录里最值得先看的文件通常是：

- `factor_ic_summary.csv`
- `factor_correlation.csv`
- `composite_factor_weights.csv`
- `composite\portfolio_summary.csv`
- `factors\{factor_name}\portfolio_summary.csv`

如果你想比较单因子和多因子效果，这套目录已经够直接了。

### 7.3 组合选券策略怎么配

`PortfolioConfig.weighting` 现在对应的是 `portfolio.py` 里的**选券策略注册键**。当前内置只有：

- `equal`

也就是先按因子值选 Top-N，再等权持有。

这一步已经被抽成策略对象，所以后续要加：

- 按分数加权
- 分层等权
- 类别约束后的权重分配

都可以不改回测主循环，只扩展注册表。

一个最小示意是：

```python
from research.esim.portfolio import register_selection_strategy


class MySelection:
    def select(self, group, factor_column, instrument_column, config):
        selected = group.nlargest(config.top_n, factor_column)
        ...
        return {"510300.SH": 0.5, "512100.SH": 0.5}


register_selection_strategy("my_selection", MySelection())
```

然后：

```python
portfolio_config = PortfolioConfig(
    weighting="my_selection",
    top_n=10,
    return_column="fwd_ret_5d",
    rebalance_freq_days=5,
)
```

这样就能把你的策略接到现有评估框架里。

---

## 8. 如何新增一个因子

新增因子的最短路径在 `research\esim\factors.py`。

你需要做两步：

1. 写一个因子函数
2. 注册到 `FACTOR_REGISTRY`

示意：

```python
def factor_my_alpha(df, params, data_config):
    ...
    return series


FACTOR_REGISTRY["my_alpha"] = FactorDefinition(
    "my_alpha",
    direction=1,
    category="price",
    transform=factor_my_alpha,
)
```

然后就可以这样调用：

```python
FactorSpec(name="my_alpha")
```

---

## 9. 如何扩展研究框架

如果你现在想扩展的不只是因子，而是研究框架本身，优先沿着这 3 个 seam 走：

1. **pipeline seam**：在 `pipeline.py` 里新增或替换 `Step`
2. **portfolio seam**：在 `portfolio.py` 里注册新的 selection strategy
3. **composite seam**：在 `composite.py` 里注册新的 composite method

一句话说：

- 想改“研究步骤顺序” -> 改 pipeline
- 想改“单因子怎么变成组合” -> 改 portfolio strategy
- 想改“多个因子怎么合成一个信号” -> 改 composite method

这样扩展会更稳，也更符合这次重构后的职责边界。

---

## 10. 如何跑 tests

在仓库根目录执行：

```powershell
python -m unittest discover research\esim\tests
```

当前 tests 重点覆盖：

1. 等权多因子合成
2. rolling-IC 多因子合成
3. 分区真实数据加载与输出落盘

---

## 11. 最小工作流建议

如果你要开始一个新因子，建议按这个顺序：

1. 先在 `factors.py` 加入因子
2. 用 `python -m research.esim` 跑示例，确认接口没坏
3. 再替换成真实 ETF 数据
4. 先看 `ic_summary`
5. 再看 `quantile_summary`
6. 最后看 `portfolio_summary`

一个实用经验是：

- **IC 好但组合差**：通常是换手、方向、分层不稳定
- **组合好但 IC 一般**：可能更像慢变量或风格暴露
- **autocorrelation 极高**：要警惕它是不是“稳”，还是“慢”

---

## 12. 一句话记住怎么用

如果只记一个操作流程，就记这个：

```python
results = run_factor_study(...)
factor = results.get_factor("fdr")
print(factor.ic_summary[1])
print(factor.quantile_summary[5])
print(factor.portfolio_summary)
```

这就是 `esim` 的主入口。
