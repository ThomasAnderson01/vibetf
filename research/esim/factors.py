from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import DataConfig, FactorSpec, ResearchConfig


FactorTransform = Callable[[pd.DataFrame, Mapping[str, object], DataConfig], pd.Series]


@dataclass(frozen=True)
class FactorDefinition:
    name: str
    direction: int
    category: str
    transform: FactorTransform


def _groupby_instrument(df: pd.DataFrame, data_config: DataConfig) -> pd.core.groupby.generic.DataFrameGroupBy:
    return df.groupby(data_config.instrument_column)


def _grouped_close(df: pd.DataFrame, data_config: DataConfig) -> pd.core.groupby.generic.SeriesGroupBy:
    return _groupby_instrument(df, data_config)[data_config.close_column]


def _rolling_linear_decay(series: pd.Series, days: int) -> pd.Series:
    if days < 1:
        raise ValueError(f"days 必须大于等于 1: {days}")
    weights = np.arange(1, days + 1, dtype=float)
    weight_sum = weights.sum()
    return series.rolling(days, min_periods=days).apply(
        lambda values: float(np.dot(values, weights) / weight_sum),
        raw=True,
    )


def _safe_vwap(df: pd.DataFrame, data_config: DataConfig) -> pd.Series:
    volume = df[data_config.volume_column].replace(0, np.nan)
    return df[data_config.amount_column] / volume


def _cross_sectional_rank(values: pd.Series, trade_dates: pd.Series) -> pd.Series:
    return values.groupby(trade_dates).transform(lambda series: series.rank(method="average", pct=True))


def _resolve_cap_100m(df: pd.DataFrame, data_config: DataConfig, params: Mapping[str, object]) -> pd.Series:
    cap_column = str(params.get("cap_column", "cap_100m"))
    if cap_column in df.columns:
        return df[cap_column].replace(0, np.nan)

    share_column = str(params.get("share_column", "fd_share"))
    if share_column in df.columns:
        return (df[share_column] * df[data_config.close_column]).replace(0, np.nan)

    raise ValueError(
        "tvr1m 需要点时规模列。请提供 `cap_100m` / 自定义 cap_column，"
        "或提供 `fd_share` 以便通过 `fd_share * close` 推导。"
    )


def factor_momentum(df: pd.DataFrame, params: Mapping[str, object], data_config: DataConfig) -> pd.Series:
    window = int(params.get("window", 20))
    return _grouped_close(df, data_config).pct_change(window)


def factor_reversal(df: pd.DataFrame, params: Mapping[str, object], data_config: DataConfig) -> pd.Series:
    window = int(params.get("window", 5))
    return -_grouped_close(df, data_config).pct_change(window)


def factor_volatility(df: pd.DataFrame, params: Mapping[str, object], data_config: DataConfig) -> pd.Series:
    window = int(params.get("window", 20))
    return (
        df.groupby(data_config.instrument_column)["daily_return"]
        .transform(lambda s: s.rolling(window, min_periods=window).std())
    )


def factor_liquidity(df: pd.DataFrame, params: Mapping[str, object], data_config: DataConfig) -> pd.Series:
    window = int(params.get("window", 20))
    rolling_mean = (
        df.groupby(data_config.instrument_column)["amount_100m"]
        .transform(lambda s: s.rolling(window, min_periods=window).mean())
    )
    return np.log1p(rolling_mean)


def factor_volume_trend(df: pd.DataFrame, params: Mapping[str, object], data_config: DataConfig) -> pd.Series:
    window = int(params.get("window", 20))
    rolling_mean = (
        _groupby_instrument(df, data_config)["amount_100m"]
        .transform(lambda s: s.rolling(window, min_periods=window).mean())
    )
    return df["amount_100m"] / rolling_mean - 1.0


def factor_fdr(df: pd.DataFrame, params: Mapping[str, object], data_config: DataConfig) -> pd.Series:
    days = int(params.get("days", 5))
    return _groupby_instrument(df, data_config)["daily_return"].transform(
        lambda series: -_rolling_linear_decay(series, days)
    )


def factor_vcr(df: pd.DataFrame, params: Mapping[str, object], data_config: DataConfig) -> pd.Series:
    days = int(params.get("days", 5))
    close = df[data_config.close_column].replace(0, np.nan)
    vwap_to_close = _safe_vwap(df, data_config) / close
    return vwap_to_close.groupby(df[data_config.instrument_column]).transform(
        lambda series: _rolling_linear_decay(series, days)
    )


def factor_rstd1m(df: pd.DataFrame, params: Mapping[str, object], data_config: DataConfig) -> pd.Series:
    days = int(params.get("days", 20))
    squared_return = df["daily_return"].pow(2)
    return squared_return.groupby(df[data_config.instrument_column]).transform(
        lambda series: series.rolling(days, min_periods=days).sum()
    )


def factor_tvr1m(df: pd.DataFrame, params: Mapping[str, object], data_config: DataConfig) -> pd.Series:
    days = int(params.get("days", 21))
    cap_100m = _resolve_cap_100m(df, data_config, params)
    turnover_ratio = df["amount_100m"] / cap_100m
    rolling_turnover = turnover_ratio.groupby(df[data_config.instrument_column]).transform(
        lambda series: series.rolling(days, min_periods=days).sum()
    )
    return -np.log(rolling_turnover.replace(0, np.nan))


def factor_liquidity_quality(
    df: pd.DataFrame,
    params: Mapping[str, object],
    data_config: DataConfig,
) -> pd.Series:
    long_window = int(params.get("long_window", 126))
    short_window = int(params.get("short_window", 21))
    trade_dates = df[data_config.trade_date_column]
    amount = df["amount_100m"].replace(0, np.nan)

    amihud_component = (df["daily_return"].abs() / amount).groupby(df[data_config.instrument_column]).transform(
        lambda series: series.rolling(long_window, min_periods=long_window).mean()
    )
    liquidity_component = amount.groupby(df[data_config.instrument_column]).transform(
        lambda series: series.rolling(short_window, min_periods=short_window).mean()
    )

    ranked_amihud = _cross_sectional_rank(amihud_component, trade_dates)
    ranked_liquidity = _cross_sectional_rank(liquidity_component, trade_dates)
    return -ranked_amihud * (ranked_liquidity - 0.5)


FACTOR_REGISTRY: dict[str, FactorDefinition] = {
    "momentum": FactorDefinition("momentum", direction=1, category="price", transform=factor_momentum),
    "reversal": FactorDefinition("reversal", direction=1, category="price", transform=factor_reversal),
    "volatility": FactorDefinition("volatility", direction=-1, category="risk", transform=factor_volatility),
    "liquidity": FactorDefinition("liquidity", direction=1, category="liquidity", transform=factor_liquidity),
    "volume_trend": FactorDefinition("volume_trend", direction=1, category="liquidity", transform=factor_volume_trend),
    "fdr": FactorDefinition("fdr", direction=1, category="price", transform=factor_fdr),
    "vcr": FactorDefinition("vcr", direction=1, category="microstructure", transform=factor_vcr),
    "rstd1m": FactorDefinition("rstd1m", direction=-1, category="risk", transform=factor_rstd1m),
    "tvr1m": FactorDefinition("tvr1m", direction=1, category="liquidity", transform=factor_tvr1m),
    "liquidity_quality": FactorDefinition(
        "liquidity_quality",
        direction=1,
        category="liquidity",
        transform=factor_liquidity_quality,
    ),
}


def get_factor_definition(name: str) -> FactorDefinition:
    try:
        return FACTOR_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"未知因子: {name}") from exc


def _winsorize_and_zscore(panel: pd.DataFrame, column: str, clip_zscore: float, trade_date_column: str) -> pd.Series:
    def _normalize(values: pd.Series) -> pd.Series:
        if values.notna().sum() < 2:
            return values
        mean = values.mean()
        std = values.std(ddof=0)
        if std == 0 or pd.isna(std):
            return values - mean
        zscore = (values - mean) / std
        return zscore.clip(-clip_zscore, clip_zscore)

    return panel.groupby(trade_date_column)[column].transform(_normalize)


def compute_raw_factor_frame(
    daily_bars: pd.DataFrame,
    factor_specs: list[FactorSpec],
    data_config: DataConfig,
) -> pd.DataFrame:
    factor_frame = daily_bars.copy()
    for spec in factor_specs:
        factor_definition = get_factor_definition(spec.name)
        raw_column = f"{spec.name}_raw"
        factor_frame[raw_column] = factor_definition.transform(
            factor_frame,
            spec.params,
            data_config,
        )
    return factor_frame


def normalize_factor_frame(
    daily_bars: pd.DataFrame,
    factor_specs: list[FactorSpec],
    data_config: DataConfig,
    research_config: ResearchConfig,
) -> pd.DataFrame:
    factor_frame = daily_bars.copy()
    for spec in factor_specs:
        raw_column = f"{spec.name}_raw"
        if raw_column not in factor_frame.columns:
            raise KeyError(f"缺少原始因子列: {raw_column}")
        if research_config.normalize_factors:
            factor_frame[spec.name] = _winsorize_and_zscore(
                factor_frame,
                raw_column,
                research_config.clip_zscore,
                data_config.trade_date_column,
            )
        else:
            factor_frame[spec.name] = factor_frame[raw_column]
    return factor_frame
