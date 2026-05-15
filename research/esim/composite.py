from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CompositeConfig, DataConfig
from .factors import get_factor_definition
from .results import FactorResult


def _equal_weight_frame(index: pd.Index, factor_names: list[str]) -> pd.DataFrame:
    if not factor_names:
        raise ValueError("至少需要一个因子用于合成")
    return pd.DataFrame(1.0 / len(factor_names), index=index, columns=factor_names)


def _rolling_ic_weights(
    index: pd.Index,
    factor_results: dict[str, FactorResult],
    factor_names: list[str],
    horizon: int,
    lookback: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    ic_history = pd.DataFrame(
        {
            factor_name: factor_results[factor_name].ic_series[horizon].reindex(index)
            for factor_name in factor_names
        }
    )
    realized_ic_lag = horizon + 1
    rolling_ic = ic_history.rolling(lookback, min_periods=max(5, lookback // 2)).mean().shift(realized_ic_lag)
    denom = rolling_ic.abs().sum(axis=1).replace(0, np.nan)
    weights = rolling_ic.div(denom, axis=0)
    fallback = _equal_weight_frame(index, factor_names)
    return weights.where(weights.notna(), fallback), ic_history


def build_composite_signal(
    prepared_bars: pd.DataFrame,
    factor_results: dict[str, FactorResult],
    composite_config: CompositeConfig,
    data_config: DataConfig,
) -> tuple[pd.Series, pd.DataFrame, pd.DataFrame | None]:
    factor_names = list(composite_config.factor_names)
    if not factor_names:
        raise ValueError("CompositeConfig.factor_names 不能为空")

    trade_date_column = data_config.trade_date_column
    factor_frame = prepared_bars[factor_names].copy()
    for factor_name in factor_names:
        factor_frame[factor_name] = factor_frame[factor_name] * get_factor_definition(factor_name).direction

    trade_dates = pd.Index(
        prepared_bars[trade_date_column].drop_duplicates().sort_values(),
        name=trade_date_column,
    )
    if composite_config.method == "equal":
        weights = _equal_weight_frame(trade_dates, factor_names)
        ic_history = None
    elif composite_config.method == "rolling_ic":
        weights, ic_history = _rolling_ic_weights(
            trade_dates,
            factor_results,
            factor_names,
            horizon=composite_config.ic_horizon,
            lookback=composite_config.ic_lookback,
        )
    else:
        raise ValueError(f"不支持的 composite method: {composite_config.method}")

    row_weights = pd.DataFrame(
        {
            factor_name: prepared_bars[trade_date_column].map(weights[factor_name])
            for factor_name in factor_names
        },
        index=prepared_bars.index,
    )
    active_weights = row_weights.where(factor_frame.notna())
    denom = active_weights.abs().sum(axis=1).replace(0, np.nan)
    normalized_weights = active_weights.div(denom, axis=0)
    composite_signal = factor_frame.mul(normalized_weights).sum(axis=1, min_count=1)
    return composite_signal, weights, ic_history
