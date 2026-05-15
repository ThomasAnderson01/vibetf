# esim 框架设计审查

> 基于第一性原理与主流开源框架（Alphalens / Qlib / vn.py）对比，2026-05-15

## 总体评价

esim 的定位清晰——**轻量级 A 股 ETF 日频因子研究底座**，模块拆分合理，核心流水线 data → factor → label → analytics → portfolio 逻辑通畅。但在几个关键维度上存在设计缺陷，会在真实研究中引入偏差或限制扩展性。

---

## 一、关键问题（会影响研究结论正确性）

### 1. 因子标准化包含了非可交易标的（look-through bias）

`pipeline.py:39-42`：

```python
dataset = compute_factor_frame(dataset, factor_specs, research_config)  # 全量计算
dataset = add_forward_returns(dataset, research_config.horizons)
dataset = dataset[dataset["is_eligible"]].copy()  # 事后过滤
```

`_winsorize_and_zscore` 在全量数据（含非 eligible ETF）上做截面标准化，之后才过滤 eligible。这意味着：
- 横截面排名和 z-score 被不可交易的 ETF 稀释
- 不同时间段 eligible 池子大小不同，标准化尺度不一致

**应改为**：先过滤 eligible，再标准化因子。或者在标准化时只使用 eligible 样本。

### 2. 因子计算硬编码列名，与 DataConfig 不一致

`factors.py:14-16`：

```python
def _grouped_close(df):
    return df.groupby("ts_code")["close"]
```

`DataConfig` 定义了 `instrument_column="ts_code"` 和 `price_columns`，但因子函数完全无视，硬编码了 `"ts_code"` 和 `"close"`。如果用户改了 `DataConfig`，因子会静默出错。

**应改为**：因子函数接收 DataConfig 或统一的列名映射，通过参数引用列名。

### 3. 组合模拟只支持 1 日调仓周期，与多持有期评价割裂

`portfolio.py` 每天都重新选 Top-N 并计算换手，但 `return_column` 默认是 `fwd_ret_1d`。如果研究 5 日持有期因子：
- 改 `return_column="fwd_ret_5d"` 后，每天仍会重算权重和换手，但 5 日 forward return 之间有时间重叠，换手计算语义错误
- 不支持 "每 5 天调仓一次" 的真实场景

**应改为**：`PortfolioConfig` 增加 `rebalance_freq` 参数，组合只在调仓日重算权重，非调仓日持有不动。

### 4. 无基准比较，无法区分 alpha 与 beta

`portfolio.py` 的回测只输出了绝对收益指标（年化收益、Sharpe、最大回撤），但：
- ETF 轮动策略的收益可能大部分来自市场 beta
- 没有等权基准、没有沪深 300 对比
- 没有 excess return / information ratio

**应改为**：增加 benchmark 收益列，计算超额收益、IR、beta。

---

## 二、设计缺陷（限制扩展性和研究深度）

### 5. 因子是裸函数，缺少元数据

当前 `FactorFunction = Callable[[pd.DataFrame, dict], pd.Series]`，因子只是一个函数。对比 Qlib 的 `Feature` / `Transformer` 设计，缺少：
- **方向声明**：momentum 是正方向（IC 正为好），volatility 可能是负方向
- **类别标签**：属于量价 / 基本面 / 另类
- **最小数据窗口声明**：window=20 意味着前 20 行为 NaN，但系统没有自动对齐
- **延迟声明**：因子用到的数据是否需要 shift(1) 避免未来信息

**建议**：引入 `FactorBase` 抽象类：

```python
class FactorBase(ABC):
    name: str
    direction: int  # 1 or -1
    category: str
    min_periods: int

    @abstractmethod
    def transform(self, df: pd.DataFrame, params: dict) -> pd.Series: ...
```

### 6. 无因子衰减/自相关分析

Alphalens 的核心输出之一是 **factor autocorrelation**（因子排名在相邻期间的秩相关），这直接决定了：
- 换手率的合理范围
- 信号衰减速度
- 调仓频率的选择

当前 analytics 只有 IC 和分层收益，缺少这个关键维度。

### 7. 无多因子组合能力

当前只能逐因子单变量评估，没有：
- 因子间相关矩阵
- 因子正交化 / 中性化
- 多因子打分合成（等权 / IC 加权 / 回归加权）
- 正则化回归（Ridge / Lasso）

这是从"因子研究"到"策略研究"的关键跃迁。

### 8. 结果是嵌套 dict，无类型安全

`results["momentum"]["ic_summary_1d"]` 这种访问方式：
- 拼错 key 静默返回 KeyError
- IDE 无法补全
- 不同因子的结果结构不一致时难以排查

**建议**：引入 `FactorResult` dataclass：

```python
@dataclass
class FactorResult:
    name: str
    panel: pd.DataFrame
    ic_series: dict[int, pd.Series]       # horizon -> series
    ic_summary: dict[int, pd.DataFrame]   # horizon -> summary
    quantile_returns: dict[int, pd.DataFrame]
    portfolio_curve: pd.DataFrame
    portfolio_summary: pd.DataFrame
```

### 9. 无交易日历抽象

A 股交易日历是非平凡的（春节、国庆等长假期）。当前依赖 `pd.bdate_range`（只排除周末），在实际数据中会有：
- 节假日缺失数据导致 `shift(-1)` 实际是 shift 了多天
- forward return 的"1 日"和"5 日"在节假日前后含义不一致

**建议**：引入交易日历模块，基于 tushare 的 `trade_cal` 接口，所有时间偏移基于交易日而非自然日。

### 10. 无统计显著性检验

IC 均值和 IR 不能直接判断因子是否显著：
- IC 序列有自相关，简单 t 检验过度拒绝
- 需要 **Newey-West 调整 t 统计量**
- 或 bootstrap 置信区间
- Alphalens 输出中包含 t-stat

---

## 三、可优化项（提升工程质量和研究效率）

### 11. 中间结果无缓存

`compute_factor_frame` 每次运行都从头计算所有因子。对大盘数据（200+ ETF × 5 年日线），重复计算代价大。Qlib 的 `DataHandler` 支持磁盘缓存。

**建议**：因子计算结果支持 parquet 缓存，通过 hash(factor_spec + data_range) 做缓存键。

### 12. 退市/停牌处理不明确

`add_forward_returns` 中如果 ETF 在 t+1 停牌，entry_price 为 NaN，forward return 静默变 NaN。但在 portfolio 模拟中，如果某 ETF 昨天在 Top-N 中但今天停牌：
- 不会被选入新持仓（因为 dropna 会排除）
- 但实际持仓无法卖出，成本计算失真

**建议**：显式处理停牌——停牌标的保持持仓不变直到复牌，或强制卖出并计入冲击成本。

### 13. 无报告输出

研究结果的持久化和可视化是刚需。当前只有 print 输出。

**建议**：增加 `report` 模块，输出 Markdown 摘要 + 关键图表（IC 时序、分层收益柱状图、净值曲线）。

### 14. 换手率计算缺少"持仓再平衡"维度

`_compute_turnover` 计算的是目标权重的变化，但：
- 没有考虑已持有标的的价格变动导致的权重漂移
- 连续持有的 ETF 理论上需要再平衡，产生隐含换手

---

## 四、与主流框架对比总结

| 维度 | Alphalens | Qlib | esim 现状 | 建议 |
|---|---|---|---|---|
| 因子元数据 | 有 category/direction | Feature 元数据系统 | 无 | 增加方向/类别/窗口声明 |
| 因子自相关 | 有 | 有 | 无 | 增加 factor autocorrelation |
| 中性化 | 支持 sector neutral | 支持 | 无 | 增加 Neutralizer 抽象 |
| 统计检验 | t-stat | 多种检验 | 无 | Newey-West t-stat |
| 交易日历 | 无（美股简单） | 有 | 无 | 基于 tushare trade_cal |
| 基准对比 | 支持 long-short | 支持 | 无 | 增加 benchmark |
| 多因子 | 不支持 | ML 模型集成 | 不支持 | 增加因子合成层 |
| 结果类型化 | dict | DataHandler | dict | dataclass |
| 缓存 | 无 | 磁盘缓存 | 无 | parquet 缓存 |
| 可视化 | matplotlib 内置 | 内置 | 无 | report 模块 |

---

## 五、推荐优先级

1. **P0（修复正确性）**：问题 1（标准化偏误）、问题 2（硬编码列名）、问题 3（调仓周期）、问题 9（交易日历）
2. **P1（补全核心能力）**：问题 4（基准对比）、问题 5（因子元数据）、问题 6（因子自相关）、问题 10（统计检验）
3. **P2（提升研究深度）**：问题 7（多因子合成）、问题 8（结果类型化）、问题 12（停牌处理）
4. **P3（工程质量）**：问题 11（缓存）、问题 13（报告输出）、问题 14（换手再平衡）
