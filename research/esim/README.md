# 日频股票 ETF 因子研究框架

## 1. 目标

这个框架面向 **A 股日频股票 ETF** 的因子研究，目标是提供一套轻量、可本地运行、易扩展的研究底座，用于支持：

1. 股票 ETF 基础因子挖掘  
2. 行业 / 主题 / 风格 ETF 的横截面排序研究  
3. 基于因子的日频组合构建与简化回测  

框架参考了：
- **Alphalens**：因子评价口径，尤其是 IC、分层收益、Top/Bottom 组合
- **Qlib**：数据集 / 因子 / 标签 / 任务流水线拆分
- **vn.py / CTA 风格**：参数化运行、研究与执行解耦

但这里刻意保持更轻量，只做 **日频研究层**，不引入复杂数据库、事件总线或实时撮合系统。

---

## 2. 研究假设

本框架默认采用以下交易假设：

1. **研究对象是股票 ETF**
   - 不做货币、债券、商品、跨境的主策略框架
   - 可用 `asset_type == 股票` 过滤

2. **只做日频**
   - 不使用分钟线、tick 或盘口数据
   - 不做日内 alpha、不做高频撮合

3. **遵守 A 股 ETF 的日频现实约束**
   - 默认信号在 `t` 日收盘后形成
   - 默认使用 `t+1` 开盘进场
   - 默认持有到 `t+1+h` 开盘，计算 `h` 日 forward return

4. **研究层先于执行层**
   - 先验证因子是否有横截面区分能力
   - 再讨论真实交易、申赎、做市、冲击成本等执行细节

---

## 3. 框架结构

```text
research/esim/
├── README.md          # 设计文档与使用说明
├── TUTORIAL.md        # 从示例到真实数据的上手文档
├── LEAKAGE_CHECKLIST.md  # 时间对齐与数据泄露检查清单
├── __init__.py
├── composite.py       # 多因子合成方法与注册表
├── config.py          # 研究配置、因子定义、组合参数
├── schema.py          # 数据契约与列名规范
├── data.py            # 本地文件读取、分区数据加载、真实 ETF 数据集加载、股票 ETF 过滤
├── experiment.py      # 纯实验编排（因子研究 + 合成 + 汇总）
├── factors.py         # 因子接口与内置因子库
├── labels.py          # 未来收益标签
├── analytics.py       # IC、分层收益、因子摘要
├── portfolio.py       # 组合选券策略与日频 Top-N 模拟
├── pipeline.py        # 可组合步骤流水线（StudyPipeline + 内置步骤）
├── report.py          # CSV 输出落盘
├── run_research.py    # 脚本入口
├── sample_data.py     # 合成样本数据
├── example_run.py     # 最小可运行示例
├── examples/          # 示例脚本
└── tests/             # 单元测试
```

---

## 4. 数据契约

### 4.1 必需日线字段

输入数据至少应包含：

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

### 4.2 可选元数据字段

如果存在，框架会自动保留并用于过滤或分组：

| 字段 | 含义 |
| --- | --- |
| `asset_type` | 大类资产，如股票 / 债券 / 商品 |
| `stock_subtype` | 股票 ETF 子类别，如宽基 / 行业 / 主题 / 风格 |
| `extname` | ETF 名称 |
| `mgr_name` | 管理人 |
| `index_name` | 跟踪指数名称 |

### 4.3 推荐输入格式

- CSV
- Parquet

推荐使用长表结构：一行代表一个 ETF 在一个交易日的一条日线记录。

---

## 5. 因子研究流水线

框架采用**可组合步骤**设计，流水线由独立的 `Step` 函数串联而成，每步接收并返回 `StudyContext`，调用方可自由组装、插入或替换步骤。

### 5.1 内置步骤

| 步骤 | 作用 |
| --- | --- |
| `load_data(bars)` | 加载 CSV/Parquet 或 copy DataFrame |
| `prepare_bars()` | 日期标准化、去重、过滤、计算衍生列 |
| `compute_factors()` | 计算原始因子 |
| `add_labels()` | 计算 forward return |
| `filter_eligible()` | 过滤可交易池 |
| `normalize_factors()` | 截面 winsorize + z-score |
| `evaluate_factors()` | IC / 分位 / 自相关 / 组合评价 |

`DEFAULT_STUDY_STEPS` 包含除 `load_data` 外的全部 6 个步骤，按标准顺序排列。

### 5.2 标准流程

默认流程等价于：

```python
pipeline = StudyPipeline([
    load_data(daily_bars),
    *DEFAULT_STUDY_STEPS,  # prepare_bars → compute_factors → add_labels → filter_eligible → normalize_factors → evaluate_factors
])
result = pipeline.run(StudyContext(factor_specs=[...], research_config=...))
```

快捷入口 `run_factor_study(...)` 内部即如此运行。

### 5.3 自定义流水线

你可以自由组合步骤——插入、跳过、替换：

```python
pipeline = StudyPipeline([
    load_data(my_bars),
    prepare_bars(),
    compute_factors(),
    add_labels(),
    filter_eligible(),
    my_neutralization_step(),   # 自定义步骤
    normalize_factors(),
    evaluate_factors(),
])
result = pipeline.run(ctx)
```

自定义步骤只需满足 `Step` 签名 `Callable[[StudyContext], StudyContext]`：

```python
def my_neutralization_step(ctx: StudyContext) -> StudyContext:
    ctx.df["momentum"] = ctx.df["momentum"] - ctx.df["momentum"].groupby(ctx.df["stock_subtype"]).transform("mean")
    return ctx
```

### 5.4 experiment 编排层

`experiment.py` 现在只负责把几个研究阶段串起来：

1. 调用 `run_factor_study(...)` 跑单因子研究
2. 计算因子相关性汇总
3. 按 `CompositeConfig` 生成多因子合成信号
4. 对合成信号复用同一套 `evaluate_factor_results(...)`
5. 汇总为 `ExperimentResult`

这样 `experiment` 本身不再依赖某个具体数据源；真实 ETF 数据加载、默认路径选择等都放在 `data.py`。

### 5.5 多因子合成策略化

`composite.py` 已经改成“方法对象 + 注册表”的扩展方式：

- 内置注册表：`COMPOSITE_REGISTRY`
- 内置方法：`equal`、`rolling_ic`
- 扩展入口：`register_composite_method(...)`
- `rolling_ic` 只使用已经完全实现的历史 IC，不使用未走完持有期的标签

也就是说，后续补正交化、风险约束加权、分类桶内合成时，不需要改 `run_experiment(...)` 主流程，只需要新增一个合成方法。

### 5.6 组合选券策略化

`portfolio.py` 也已改成“选券策略 + 注册表”：

- 内置注册表：`SELECTION_REGISTRY`
- 内置策略：`equal`
- 扩展入口：`register_selection_strategy(...)`

`PortfolioConfig.weighting` 现在不只是一个字符串开关，而是选用哪种选券/权重策略的键。当前默认还是等权 Top-N；后续如果要补分层等权、按因子分数加权、行业约束权重，都可以沿着这个 seam 扩展。

例如自定义一个简单的分数加权策略：

```python
import pandas as pd

from research.esim.portfolio import SelectionStrategy, register_selection_strategy


class ScoreWeightTopN:
    def select(self, group, factor_column, instrument_column, config):
        selected = group.nlargest(config.top_n, factor_column).copy()
        if selected.empty:
            return {}
        scores = selected[factor_column].clip(lower=0.0)
        if scores.sum() <= 0:
            weight = 1.0 / len(selected)
            return dict(zip(selected[instrument_column], [weight] * len(selected), strict=False))
        weights = scores / scores.sum()
        return dict(zip(selected[instrument_column], weights, strict=False))


register_selection_strategy("score_weight", ScoreWeightTopN())
```

再把 `PortfolioConfig(weighting="score_weight", ...)` 传给研究入口即可。

---

## 6. 内置基础因子

当前内置了几类适合 ETF 日频研究的基础因子；每个因子都附带 `direction` 和 `category` 元数据，便于后续做多因子合成和报告：

| 因子 | 含义 |
| --- | --- |
| `momentum` | N 日价格动量 |
| `reversal` | N 日反转 |
| `volatility` | N 日收益波动率 |
| `liquidity` | N 日平均成交额（对数） |
| `volume_trend` | 当前成交额相对历史均值的偏离 |
| `fdr` | 5 日线性衰减反转，`-ts_linear_decay(returns, days=5)` |
| `vcr` | 短周期 VWAP 反转，`ts_linear_decay(vwap / close, days=5)` |
| `rstd1m` | 月度已实现波动率代理，`TsSum(Power(returns, 2), days=20)` |
| `tvr1m` | 1 个月换手值反转，`-log(ts_sum(volume * vwap / cap, days=21))` |
| `liquidity_quality` | 长窗 Amihud 流动性与短窗成交额强度的截面乘子 |

> `tvr1m` 需要点时规模输入。框架会优先使用 `cap_100m`；若不存在，则会尝试用 `fd_share * close` 推导。`data.load_real_etf_dataset(...)` 会自动从 `fund_share` 分区目录合并 `fd_share`。

这些因子只是研究起点。后续可以扩展：
- 行业 / 主题相对强弱
- ETF 份额变化因子
- 宽基 vs 行业扩散度因子
- 风格轮动因子
- 政策 / 景气代理变量

---

## 7. 评价输出

对每个因子，框架会输出四类核心结果：

1. **IC 摘要**
    - 均值
    - 标准差
    - IC IR
    - 胜率
    - t-stat / Newey-West t-stat

2. **分层收益**
    - 每个 quantile 的平均 forward return
    - Top - Bottom spread

3. **自相关**
   - 因子 rank autocorrelation
   - 观察信号衰减与调仓频率是否匹配

4. **组合回测**
     - Top-N 日收益
     - 换手
     - 成本后收益
     - 基准收益 / 超额收益 / IR / beta
     - 年化收益 / 波动 / Sharpe / 最大回撤

组合回测这层已经与选券策略解耦：同样的因子面板，可以切换不同 `weighting` 策略复用同一套回测与报表输出。

---

## 8. 适合继续扩展的方向

在这个基础框架上，建议继续补：

1. **股票 ETF 标签体系**
   - 宽基 / 行业 / 主题 / 风格 / 市值 / 成长 / 红利

2. **可交易池过滤器**
   - 近 20 日均成交额
   - 规模门槛
   - 成立时长

3. **因子正交化 / 中性化**
   - 对宽基 / 行业 / 主题类别中性
   - 对规模 / 流动性暴露中性

4. **更细的组合构建**
   - 按类别分层选券
   - 行业上限
   - 风险预算

5. **研究结果持久化**
   - 保存为 CSV / Parquet / Markdown 报告

---

## 9. 最小示例

直接运行：

```powershell
python -m research.esim.example_run
```

它会：
- 生成一份合成股票 ETF 日线样本
- 运行内置基础因子
- 输出一个示例因子的 IC 摘要、自相关、分层收益和组合回测结果

多因子示例：

```powershell
python research\esim\examples\example_multifactor.py
```

真实 ETF 数据实验：

```powershell
python research\esim\run_research.py --start-date 20260101 --end-date 20260514
```

它会默认读取：

- `data\raw\dmgr\tushare\fund_daily`
- `research\outputs\etf_liquidity_snapshot_20260514.csv`

并把结果写到：

- `research\esim\output\...`

如果你已经有真实数据，也可以在代码里直接调用：

```python
from pathlib import Path

from research.esim.config import FactorSpec, PortfolioConfig, ResearchConfig
from research.esim.pipeline import run_factor_study

results = run_factor_study(
    daily_bars=Path("your_stock_etf_daily.csv"),
    factor_specs=[
        FactorSpec(name="momentum", params={"window": 20}),
        FactorSpec(name="liquidity", params={"window": 20}),
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

momentum = results.get_factor("momentum")
print(momentum.ic_summary[1])
print(momentum.autocorrelation_summary)
print(momentum.portfolio_summary)
```

或者用步骤化 pipeline 自定义流程：

```python
from research.esim.pipeline import StudyPipeline, StudyContext, load_data, DEFAULT_STUDY_STEPS

pipeline = StudyPipeline([
    load_data(Path("your_stock_etf_daily.csv")),
    *DEFAULT_STUDY_STEPS,
])
result = pipeline.run(StudyContext(
    factor_specs=[FactorSpec(name="fdr"), FactorSpec(name="vcr")],
    research_config=ResearchConfig(horizons=(1, 5)),
))
```

如果你要直接跑“策略化组合 + 多因子合成”的完整实验，入口则是：

```python
from research.esim.config import CompositeConfig, PortfolioConfig
from research.esim.experiment import run_experiment

result = run_experiment(
    daily_bars=Path("your_stock_etf_daily.csv"),
    factor_specs=[FactorSpec(name="fdr"), FactorSpec(name="vcr"), FactorSpec(name="rstd1m")],
    portfolio_config=PortfolioConfig(
        weighting="equal",
        top_n=10,
        return_column="fwd_ret_5d",
        rebalance_freq_days=5,
    ),
    composite_config=CompositeConfig(
        method="rolling_ic",
        factor_names=("fdr", "vcr", "rstd1m"),
        ic_horizon=5,
        ic_lookback=20,
        name="rolling_ic_composite",
    ),
)
```

---

## 10. 输出目录

批量实验的输出目录结构参考了 `alphaflow`，当前会统一落盘：

```text
output/
├── factor_ic_summary.csv
├── factor_correlation.csv
├── composite_factor_weights.csv
├── rolling_ic_history.csv        # rolling_ic 时存在
├── run_metadata.json
├── factors/
│   └── {factor_name}/
│       ├── ic_summary_1d.csv
│       ├── ic_daily_1d.csv
│       ├── quantile_summary_5d.csv
│       ├── portfolio_curve.csv
│       └── portfolio_summary.csv
└── composite/
    ├── ic_summary_1d.csv
    ├── quantile_summary_5d.csv
    ├── portfolio_curve.csv
    └── portfolio_summary.csv
```

---

## 11. 测试

运行：

```powershell
python -m unittest discover research\esim\tests
```

当前 tests 覆盖：

- 多因子等权合成
- rolling-IC 合成
- 真实分区数据加载 + 输出落盘

---

## 12. 这份框架的定位

这不是一个完整的交易系统，而是一套 **ETF 因子研究底座**。

它最适合做的事情是：
- 快速验证股票 ETF 因子有没有横截面效果
- 比较不同因子在不同持有期上的表现
- 为行业 / 主题轮动策略提供可复用研究模块

如果后续要继续深入，最自然的下一步是：
- 增加 ETF 分类标签和池子过滤器
- 增加研究报告输出
- 增加更贴近实盘的调仓与成交假设
