# research.dmgr

`research.dmgr` 是一个轻量的 ETF 原始数据落盘模块，用来把 Tushare 等数据源的 ETF 表按交易日保存到分层目录。

## 路径约定

默认写入：

```text
data/raw/dmgr/{source_name}/{table_name}/{YYYY}/{MM}/{table_name}.{YYYYMMDD}.csv
```

例如：

```text
data/raw/dmgr/tushare/fund_daily/2026/01/fund_daily.20260105.csv
```

## 当前内置表

- `etf_basic`
- `fund_daily`
- `fund_adj`
- `fund_share`

## 运行方式

```powershell
python -m research.dmgr --start-date 20260101 --end-date 20260515
```

如果只想跑某些表：

```powershell
python -m research.dmgr --tables fund_daily fund_share
```
