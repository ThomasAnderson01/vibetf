# esim Leakage Checklist

这份清单用于系统性审视 `research\esim` 是否存在 **look-ahead leakage / label leakage / execution-time leakage**。

目标不是“凭感觉觉得没问题”，而是把每个高风险 seam 都落成：

1. **明确的 timing 假设**
2. **可复现的反事实检查**
3. **能长期保留的 regression test**

---

## 1. 先固定系统的时间语义

在审查任何 leakage 之前，先明确本系统当前的默认 timing：

1. 因子在 **`t` 日收盘后** 形成
2. label 默认定义为 **`t+1 open -> t+1+h open`**
3. IC 是拿 `factor(t)` 去对比 `fwd_ret_h(t)`
4. 组合默认在调仓日用 `factor(t)` 形成目标持仓，并用对应的 `fwd_ret_h(t)` 记账
5. `rolling_ic` 合成时，只能使用**已经完全实现**的历史 IC

如果代码改动让这 5 条里任何一条失效，就必须重新审一遍整个 checklist。

---

## 2. 数据层 checklist

### 2.1 `trade_date` 解析

- [ ] `trade_date` 的 `YYYYMMDD` 整数 / 字符串能被正确解析成交易日
- [ ] 不会被 `pd.to_datetime(int)` 误解成 Unix 纳秒
- [ ] 不会因为日期解析错误把多天数据塌成同一天

**为什么危险**

如果多天被塌成一天：

- rolling 因子会失真
- label shift 会失真
- 回测去重会吞掉大量历史

**当前状态**

- 已修复
- 关键位置：`research\esim\schema.py`

### 2.2 去重和排序

- [ ] 日线数据在进入因子计算前已按 `instrument, trade_date` 排序
- [ ] 同一标的同一交易日只保留一条记录
- [ ] 去重逻辑不会把未来版本的数据错误保留下来

**当前位置**

- `research\esim\data.py::prepare_daily_bars`

### 2.3 元数据 merge

- [ ] `asset_type` / `stock_subtype` / `extname` 等元数据不会因为 merge 重名列导致覆盖错误
- [ ] 元数据缺失只影响分组，不应改变历史 OHLCV
- [ ] 元数据填补（例如 `asset_type = 其他`）不应引入未来信息

**当前状态**

- 已修补重名列合并逻辑
- 关键位置：`research\esim\data.py::merge_metadata`

---

## 3. 因子层 checklist

### 3.1 原始因子不能依赖未来价格

对每个因子都要问：

- [ ] 只改 `t+1` 之后的数据，`factor(t)` 是否保持不变
- [ ] rolling window 只使用历史和当日，不会越过 `t`
- [ ] 如果使用 VWAP、波动率、成交额等派生量，也只依赖当日及以前数据

**当前已验证**

- `fdr`
- `vcr`
- `rstd1m`

这三个因子在反事实检查里没有表现出“未来价格改动导致过去因子变动”的问题。

### 3.2 截面标准化不能被未来样本池污染

- [ ] 因子标准化只在当日可交易样本上进行
- [ ] 不会把未来新增标的或非 eligible 标的带入今天的 z-score
- [ ] 不会在先标准化、后过滤的顺序里引入 look-through bias

**当前状态**

- 已修复
- 当前逻辑：先算 raw factor / forward return，再在 eligible 池上做标准化
- 关键位置：`research\esim\pipeline.py`

### 3.3 因子方向翻转不应改变 timing

- [ ] `direction` 只改变解释方向，不改变时间语义
- [ ] composite 中的方向修正只是符号乘法，不应重新引入未来信息

---

## 4. Label 层 checklist

### 4.1 label 必须现场计算，不能直接用外部现成涨跌幅字段

- [ ] label 使用 `entry / exit` 价格现场计算
- [ ] 不直接依赖 Tushare `pct_chg`
- [ ] `daily_return` 也用本地 `close.pct_change()` 计算，而不是复用外部日收益字段

**当前状态**

- 已满足
- 关键位置：`research\esim\labels.py`
- 默认 label：`t+1 open -> t+1+h open`

### 4.2 forward return 的持有期必须完整实现后才算“可知”

- [ ] `fwd_ret_5d(t)` 不能在 `t+1` 或 `t+2` 就被用于 rolling 权重学习
- [ ] 所有依赖 IC / future return 历史的模块都要遵守“已完全实现”原则

这条是本轮审查发现的关键风险点。

---

## 5. IC / analytics 层 checklist

### 5.1 IC 计算本身是否会提前使用未来标签

- [ ] `ic_series[t]` 的定义必须被视为“在 `fwd_ret_h(t)` 完全实现后才知道”
- [ ] 如果某处消费 `ic_series` 去调权或调仓，必须显式加滞后

### 5.2 quantile / spread 是否只是评估用途

- [ ] quantile 分组只用于 ex-post 分析，不应反向进入交易逻辑
- [ ] 如果未来引入“按 quantile 动态调参”，必须重新审 timing

---

## 6. Composite 层 checklist

这是本系统当前最容易出 leakage 的地方。

### 6.1 等权 composite

- [ ] 等权 composite 只依赖当日各因子值
- [ ] 不依赖历史 future return 或历史 IC

**当前风险**

- 低

### 6.2 rolling-IC composite

- [ ] rolling-IC 权重只能使用**已经完全实现**的 IC 历史
- [ ] 权重滞后不能只写成 `shift(1)`，而要考虑 `horizon`
- [ ] 如果 `ic_horizon = h`，则权重至少需要滞后到 label fully realized 之后
- [ ] future data 的扰动不应改变 cutoff 之前的 composite weights

**当前状态**

- 本轮发现过真实 leakage
- 已修复：`rolling_ic` 权重现在滞后 `horizon + 1`
- 关键位置：`research\esim\composite.py`
- 已有回归测试：`test_rolling_ic_weights_do_not_use_unrealized_future_ic`

### 6.3 未来如果补正交化 / 中性化

一旦引入：

- 行业中性
- 风格中性
- 回归残差
- rolling PCA

要逐项检查：

- [ ] 中性化截面是否只使用当日暴露
- [ ] rolling 回归是否只使用历史窗口
- [ ] 回归目标是否意外用了 future return

---

## 7. Portfolio / 回测层 checklist

### 7.1 调仓日的信号是否只使用当日已知信息

- [ ] `trade_date = t` 的持仓只使用 `factor(t)`
- [ ] 不使用 `fwd_ret_h(t)` 形成当天持仓
- [ ] 调仓频率与 `return_column` 持有期一致

**当前状态**

- 已有限制：`rebalance_freq_days` 必须与 `return_column` 对应的 horizon 一致
- 关键位置：`research\esim\portfolio.py`

### 7.2 回测收益被未来数据改变不一定是 leakage

要区分两件事：

1. **权重提前变化**：这是 leakage
2. **固定历史持仓对应的未来 realized return 变化**：这是正常的

例如：

- 如果只改 cutoff 之后的价格，cutoff 之前已经持有的仓位，其未来持有期收益会变
- 这会改变历史净值曲线后段
- 但只要 cutoff 之前的权重没有变，就不是 look-ahead leakage

### 7.3 benchmark 是否偷看未来

- [ ] benchmark return 只取当日横截面 `fwd_ret_h(t)` 的平均
- [ ] benchmark 不应参与当日持仓形成

---

## 8. 反事实检查模板

每次做 timing 审查时，优先用下面这个反事实方法：

### 模板

1. 选定一个截点 `t`
2. 运行 baseline
3. 只修改 `t` 之后的数据
4. 重新运行
5. 比较：
   - `factor(s <= t)` 是否变化
   - `weights(s <= t)` 是否变化
   - `holdings(s <= t)` 是否变化

### 解释规则

- **过去因子变了** → 因子层泄露
- **过去权重变了** → composite / portfolio timing 泄露
- **过去净值变了但过去权重没变** → 先别判泄露，检查是不是未来 realized return 改变导致

---

## 9. 推荐保留的 regression tests

当前建议长期保留以下测试类型：

### A. 因子层

- [ ] 改未来价格，历史 raw factor 不变
- [ ] 改未来成交量，历史 VWAP 类因子不变

### B. Composite 层

- [x] 改未来价格，cutoff 前 `rolling_ic` 权重不变
- [ ] 改未来价格，cutoff 前 `equal` composite signal 不变

### C. 数据层

- [ ] `trade_date=20260105` 解析为真实交易日，而不是 Unix 纳秒
- [ ] 分区数据加载不会丢日或串月

### D. Portfolio 层

- [ ] `rebalance_freq_days != return_column horizon` 时明确报错
- [ ] 改未来价格不应改变 cutoff 前持仓选择

---

## 10. 当前审查结论

截至这轮审查：

### 已确认没有明确 leakage 的部分

- 单因子 raw signal（`fdr` / `vcr` / `rstd1m`）
- label 现场计算逻辑本身
- 等权 composite

### 已确认存在且已修复的 leakage

- `rolling_ic` composite 原先只 `shift(1)`，会提前使用尚未完全实现的 IC
- 现已修正为只使用 fully realized 的 IC 历史

### 仍需持续关注的高风险 seam

- 未来加入的正交化 / 中性化
- 未来加入的类别约束组合构建
- 未来如果引入用历史绩效动态调参的逻辑

---

## 11. 每次改动前后的最小流程

如果后面继续改 `esim`，建议每次都走这 5 步：

1. 明确本次改动涉及哪个 seam  
   - factor / label / composite / portfolio / output
2. 明确这个 seam 的“当日可知信息”边界  
3. 写一个反事实扰动脚本  
4. 比较 cutoff 前的 factor / weight / holding 是否变化  
5. 把结果固化成 test

如果做不到第 3 步或第 5 步，说明这个 seam 还不够深，后面很容易再把 leakage 引回去。
