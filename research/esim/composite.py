from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np
import pandas as pd

from .config import CompositeConfig, DataConfig
from .factors import get_factor_definition
from .results import FactorResult


@runtime_checkable
class CompositeMethod(Protocol):
    def compute_weights(
        self,
        trade_dates: pd.Index,
        factor_names: list[str],
        composite_config: CompositeConfig,
        factor_results: dict[str, FactorResult] | None,
    ) -> tuple[pd.DataFrame, pd.DataFrame | None]: ...


class EqualWeightComposite:
    def compute_weights(
        self,
        trade_dates: pd.Index,
        factor_names: list[str],
        composite_config: CompositeConfig,
        factor_results: dict[str, FactorResult] | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        if not factor_names:
            raise ValueError("至少需要一个因子用于合成")
        weights = pd.DataFrame(1.0 / len(factor_names), index=trade_dates, columns=factor_names)
        return weights, None


class RollingICComposite:
    def compute_weights(
        self,
        trade_dates: pd.Index,
        factor_names: list[str],
        composite_config: CompositeConfig,
        factor_results: dict[str, FactorResult] | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame | None]:
        if factor_results is None:
            raise ValueError("rolling_ic 合成需要 factor_results")
        ic_history = pd.DataFrame(
            {
                factor_name: factor_results[factor_name].ic_series[composite_config.ic_horizon].reindex(trade_dates)
                for factor_name in factor_names
            }
        )
        realized_ic_lag = composite_config.ic_horizon + 1
        rolling_ic = ic_history.rolling(
            composite_config.ic_lookback,
            min_periods=max(5, composite_config.ic_lookback // 2),
        ).mean().shift(realized_ic_lag)
        denom = rolling_ic.abs().sum(axis=1).replace(0, np.nan)
        weights = rolling_ic.div(denom, axis=0)
        fallback = pd.DataFrame(1.0 / len(factor_names), index=trade_dates, columns=factor_names)
        return weights.where(weights.notna(), fallback), ic_history


COMPOSITE_REGISTRY: dict[str, CompositeMethod] = {
    "equal": EqualWeightComposite(),
    "rolling_ic": RollingICComposite(),
}


def register_composite_method(name: str, method: CompositeMethod) -> None:
    if name in COMPOSITE_REGISTRY:
        raise KeyError(f"合成方法已注册: {name}")
    COMPOSITE_REGISTRY[name] = method


def get_composite_method(name: str) -> CompositeMethod:
    try:
        return COMPOSITE_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"未知合成方法: {name}") from exc


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

    method = get_composite_method(composite_config.method)
    weights, ic_history = method.compute_weights(trade_dates, factor_names, composite_config, factor_results)

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
