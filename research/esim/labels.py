from __future__ import annotations

import pandas as pd

from .config import DataConfig


def add_forward_returns(
    daily_bars: pd.DataFrame,
    horizons: tuple[int, ...],
    data_config: DataConfig,
    entry_price_column: str | None = None,
    exit_price_column: str | None = None,
    signal_lag_days: int = 1,
) -> pd.DataFrame:
    if signal_lag_days < 1:
        raise ValueError("signal_lag_days 必须大于等于 1")

    df = daily_bars.copy()
    instrument_column = data_config.instrument_column
    entry_column = entry_price_column or data_config.open_column
    exit_column = exit_price_column or data_config.open_column
    grouped = df.groupby(instrument_column)

    entry_price = grouped[entry_column].shift(-signal_lag_days)
    for horizon in horizons:
        if horizon < 1:
            raise ValueError(f"horizon 必须大于等于 1: {horizon}")
        exit_price = grouped[exit_column].shift(-(signal_lag_days + horizon))
        df[f"fwd_ret_{horizon}d"] = exit_price / entry_price - 1.0
    return df
