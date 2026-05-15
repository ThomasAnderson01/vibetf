from __future__ import annotations

import numpy as np
import pandas as pd

from .config import DataConfig


def build_factor_panel(
    dataset: pd.DataFrame,
    factor_column: str,
    horizons: tuple[int, ...],
    data_config: DataConfig,
) -> pd.DataFrame:
    columns = [data_config.trade_date_column, data_config.instrument_column, factor_column]
    forward_columns = [f"fwd_ret_{horizon}d" for horizon in horizons]
    optional_columns = [column for column in data_config.optional_meta_columns if column in dataset.columns]
    panel = dataset[columns + forward_columns + optional_columns].copy()
    return panel.dropna(subset=[factor_column]).reset_index(drop=True)


def compute_ic_series(
    panel: pd.DataFrame,
    factor_column: str,
    return_column: str,
    trade_date_column: str = "trade_date",
) -> pd.Series:
    grouped_panel = panel.groupby(trade_date_column)[[factor_column, return_column]]

    def _date_ic(group: pd.DataFrame) -> float:
        subset = group.dropna()
        if len(subset) < 3:
            return np.nan
        return subset[factor_column].corr(subset[return_column], method="spearman")

    return grouped_panel.apply(_date_ic)


def compute_factor_autocorrelation(
    panel: pd.DataFrame,
    factor_column: str,
    instrument_column: str = "ts_code",
    trade_date_column: str = "trade_date",
    lag: int = 1,
) -> pd.Series:
    if lag < 1:
        raise ValueError("lag 必须大于等于 1")

    ordered = panel.sort_values([instrument_column, trade_date_column]).copy()
    lagged_column = f"{factor_column}_lag_{lag}"
    ordered[lagged_column] = ordered.groupby(instrument_column)[factor_column].shift(lag)
    grouped_ordered = ordered.groupby(trade_date_column)[[factor_column, lagged_column]]

    def _date_autocorr(group: pd.DataFrame) -> float:
        subset = group.dropna()
        if len(subset) < 3:
            return np.nan
        return subset[factor_column].corr(subset[lagged_column], method="spearman")

    return grouped_ordered.apply(_date_autocorr)


def _newey_west_t_stat(series: pd.Series, max_lag: int | None = None) -> float:
    values = series.dropna().to_numpy(dtype=float)
    sample_size = values.size
    if sample_size < 2:
        return np.nan

    mean = values.mean()
    centered = values - mean
    lag = min(max_lag if max_lag is not None else int(sample_size ** 0.25), sample_size - 1)
    gamma0 = np.dot(centered, centered) / sample_size
    variance = gamma0
    for offset in range(1, lag + 1):
        gamma = np.dot(centered[offset:], centered[:-offset]) / sample_size
        weight = 1.0 - offset / (lag + 1)
        variance += 2.0 * weight * gamma

    if variance <= 0:
        return np.nan
    standard_error = np.sqrt(variance / sample_size)
    return mean / standard_error if standard_error > 0 else np.nan


def summarize_ic(ic_series: pd.Series, nw_lag: int | None = None) -> pd.DataFrame:
    valid = ic_series.dropna()
    if valid.empty:
        return pd.DataFrame(
            [{"mean": np.nan, "std": np.nan, "ir": np.nan, "positive_ratio": np.nan, "t_stat": np.nan, "nw_t_stat": np.nan, "obs": 0}]
        )

    std = valid.std(ddof=0)
    mean = valid.mean()
    ir = mean / std if std and not pd.isna(std) else np.nan
    standard_error = std / np.sqrt(valid.count()) if std and not pd.isna(std) else np.nan
    t_stat = mean / standard_error if standard_error and not pd.isna(standard_error) else np.nan
    return pd.DataFrame(
        [
            {
                "mean": mean,
                "std": std,
                "ir": ir,
                "positive_ratio": (valid > 0).mean(),
                "t_stat": t_stat,
                "nw_t_stat": _newey_west_t_stat(valid, max_lag=nw_lag),
                "obs": int(valid.count()),
            }
        ]
    )


def add_factor_quantiles(
    panel: pd.DataFrame,
    factor_column: str,
    quantiles: int,
    trade_date_column: str = "trade_date",
) -> pd.DataFrame:
    def _assign(values: pd.Series) -> pd.Series:
        if values.notna().sum() < quantiles:
            return pd.Series(np.nan, index=values.index)
        ranked = values.rank(method="first")
        return pd.qcut(ranked, quantiles, labels=False) + 1

    result = panel.copy()
    result["quantile"] = result.groupby(trade_date_column)[factor_column].transform(_assign)
    return result


def compute_quantile_return_table(
    panel: pd.DataFrame,
    return_column: str,
    trade_date_column: str = "trade_date",
) -> pd.DataFrame:
    quantile_table = (
        panel.dropna(subset=["quantile", return_column])
        .groupby([trade_date_column, "quantile"])[return_column]
        .mean()
        .unstack("quantile")
        .sort_index()
    )
    return quantile_table


def summarize_quantile_returns(quantile_table: pd.DataFrame) -> pd.DataFrame:
    summary = pd.DataFrame({"mean_return": quantile_table.mean()})
    if not quantile_table.empty:
        summary.loc["top_minus_bottom", "mean_return"] = (
            quantile_table.iloc[:, -1] - quantile_table.iloc[:, 0]
        ).mean()
    return summary


def summarize_autocorrelation(autocorrelation_series: pd.Series) -> pd.DataFrame:
    valid = autocorrelation_series.dropna()
    if valid.empty:
        return pd.DataFrame([{"mean": np.nan, "median": np.nan, "positive_ratio": np.nan, "obs": 0}])
    return pd.DataFrame(
        [
            {
                "mean": valid.mean(),
                "median": valid.median(),
                "positive_ratio": (valid > 0).mean(),
                "obs": int(valid.count()),
            }
        ]
    )
