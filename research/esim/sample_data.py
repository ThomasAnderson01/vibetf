from __future__ import annotations

import numpy as np
import pandas as pd


def make_sample_stock_etf_daily_data(
    seed: int = 7,
    instruments: int = 24,
    days: int = 260,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-01", periods=days)

    stock_subtypes = ["宽基指数ETF", "行业ETF", "主题ETF", "风格策略ETF"]
    rows: list[dict] = []
    for idx in range(instruments):
        ts_code = f"51{idx:04d}.SH"
        subtype = stock_subtypes[idx % len(stock_subtypes)]
        fd_share = 20.0 + 3.0 * (idx % 7) + float(rng.random() * 10.0)
        prices = [1.0 + 0.2 * rng.random()]

        for date in dates:
            drift = -0.0001 + 0.00008 * (idx % 5)
            shock = rng.normal(0, 0.015)
            next_close = max(0.3, prices[-1] * (1 + drift + shock))
            next_open = max(0.3, prices[-1] * (1 + rng.normal(0, 0.006)))
            high = max(next_open, next_close) * (1 + abs(rng.normal(0, 0.004)))
            low = min(next_open, next_close) * (1 - abs(rng.normal(0, 0.004)))
            vol = max(10_000, int(rng.lognormal(mean=12.0 + 0.08 * (idx % 6), sigma=0.45)))
            amount = vol * (next_open + next_close) / 2 * 100

            rows.append(
                {
                    "trade_date": date,
                    "ts_code": ts_code,
                    "open": next_open,
                    "high": high,
                    "low": low,
                    "close": next_close,
                    "vol": vol,
                    "amount": amount,
                    "fd_share": fd_share,
                    "cap_100m": fd_share * next_close,
                    "asset_type": "股票",
                    "stock_subtype": subtype,
                    "extname": f"{subtype}{idx:02d}",
                    "mgr_name": f"基金公司{idx % 8}",
                    "index_name": f"{subtype}指数{idx % 10}",
                }
            )
            prices.append(next_close)

    return pd.DataFrame(rows)
