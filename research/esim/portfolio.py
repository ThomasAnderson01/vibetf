from __future__ import annotations

import math
from typing import Any, Protocol, runtime_checkable

import numpy as np
import pandas as pd

from .config import DataConfig, PortfolioConfig
from .schema import infer_horizon_from_return_column


@runtime_checkable
class SelectionStrategy(Protocol):
    def select(
        self,
        group: pd.DataFrame,
        factor_column: str,
        instrument_column: str,
        config: PortfolioConfig,
    ) -> dict[str, float]: ...


class EqualWeightTopN:
    def select(
        self,
        group: pd.DataFrame,
        factor_column: str,
        instrument_column: str,
        config: PortfolioConfig,
    ) -> dict[str, float]:
        selected = group.nlargest(config.top_n, factor_column)
        if selected.empty:
            return {}
        weight = 1.0 / len(selected)
        return dict(zip(selected[instrument_column], [weight] * len(selected), strict=False))


SELECTION_REGISTRY: dict[str, SelectionStrategy] = {
    "equal": EqualWeightTopN(),
}


def register_selection_strategy(name: str, strategy: SelectionStrategy) -> None:
    if name in SELECTION_REGISTRY:
        raise KeyError(f"选股策略已注册: {name}")
    SELECTION_REGISTRY[name] = strategy


def get_selection_strategy(name: str) -> SelectionStrategy:
    try:
        return SELECTION_REGISTRY[name]
    except KeyError as exc:
        raise KeyError(f"未知选股策略: {name}") from exc


def _compute_turnover(previous: dict[str, float], current: dict[str, float]) -> float:
    names = set(previous) | set(current)
    return 0.5 * sum(abs(previous.get(name, 0.0) - current.get(name, 0.0)) for name in names)


def simulate_top_n_portfolio(
    panel: pd.DataFrame,
    factor_column: str,
    portfolio_config: PortfolioConfig,
    data_config: DataConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    strategy = get_selection_strategy(portfolio_config.weighting)

    rebalance_freq = portfolio_config.rebalance_freq_days or infer_horizon_from_return_column(
        portfolio_config.return_column
    )
    return_horizon = infer_horizon_from_return_column(portfolio_config.return_column)
    if rebalance_freq != return_horizon:
        raise ValueError(
            "rebalance_freq_days 必须与 return_column 的持有期一致，"
            f"当前分别为 {rebalance_freq} 和 {return_horizon}"
        )

    trade_date_column = data_config.trade_date_column
    instrument_column = data_config.instrument_column
    rebalance_dates = set(panel[trade_date_column].drop_duplicates().sort_values().iloc[::rebalance_freq])

    records: list[dict[str, Any]] = []
    previous_weights: dict[str, float] = {}

    for trade_date, group in panel.groupby(trade_date_column):
        if trade_date not in rebalance_dates:
            continue
        group = group.dropna(subset=[factor_column, portfolio_config.return_column])
        current_weights = strategy.select(
            group,
            factor_column,
            instrument_column,
            portfolio_config,
        )
        if len(current_weights) < portfolio_config.min_names:
            continue

        current_frame = group[group[instrument_column].isin(current_weights)].copy()
        current_frame["weight"] = current_frame[instrument_column].map(current_weights)
        gross_return = float((current_frame["weight"] * current_frame[portfolio_config.return_column]).sum())
        benchmark_return = (
            float(group[portfolio_config.return_column].mean())
            if portfolio_config.benchmark == "equal_weight_universe"
            else np.nan
        )
        turnover = _compute_turnover(previous_weights, current_weights)
        trading_cost = turnover * portfolio_config.cost_bps / 10_000
        net_return = gross_return - trading_cost
        excess_return = net_return - benchmark_return if not pd.isna(benchmark_return) else np.nan

        records.append(
            {
                trade_date_column: trade_date,
                "gross_return": gross_return,
                "benchmark_return": benchmark_return,
                "excess_return": excess_return,
                "turnover": turnover,
                "trading_cost": trading_cost,
                "net_return": net_return,
                "holdings_count": len(current_weights),
            }
        )
        previous_weights = current_weights

    curve = pd.DataFrame(records)
    if curve.empty:
        return curve, pd.DataFrame()

    periods_per_year = 252 / rebalance_freq
    curve["nav"] = (1.0 + curve["net_return"]).cumprod()
    if portfolio_config.benchmark != "none":
        curve["benchmark_nav"] = (1.0 + curve["benchmark_return"]).cumprod()
        curve["excess_nav"] = (1.0 + curve["excess_return"].fillna(0.0)).cumprod()
    curve["drawdown"] = curve["nav"] / curve["nav"].cummax() - 1.0

    annualized_return = curve["nav"].iloc[-1] ** (periods_per_year / len(curve)) - 1.0
    annualized_vol = curve["net_return"].std(ddof=0) * math.sqrt(periods_per_year)
    sharpe = annualized_return / annualized_vol if annualized_vol and not pd.isna(annualized_vol) else np.nan
    benchmark_annualized_return = (
        curve["benchmark_nav"].iloc[-1] ** (periods_per_year / len(curve)) - 1.0
        if "benchmark_nav" in curve
        else np.nan
    )
    tracking_error = (
        curve["excess_return"].std(ddof=0) * math.sqrt(periods_per_year)
        if "excess_return" in curve
        else np.nan
    )
    information_ratio = (
        curve["excess_return"].mean() / curve["excess_return"].std(ddof=0) * math.sqrt(periods_per_year)
        if "excess_return" in curve and curve["excess_return"].std(ddof=0) > 0
        else np.nan
    )
    beta = np.nan
    if "benchmark_return" in curve and curve["benchmark_return"].notna().sum() > 1:
        benchmark_variance = curve["benchmark_return"].var(ddof=0)
        if benchmark_variance > 0:
            beta = curve["net_return"].cov(curve["benchmark_return"]) / benchmark_variance
    summary = pd.DataFrame(
        [
            {
                "annualized_return": annualized_return,
                "annualized_volatility": annualized_vol,
                "sharpe": sharpe,
                "benchmark_annualized_return": benchmark_annualized_return,
                "annualized_excess_return": annualized_return - benchmark_annualized_return
                if not pd.isna(benchmark_annualized_return)
                else np.nan,
                "tracking_error": tracking_error,
                "information_ratio": information_ratio,
                "beta": beta,
                "max_drawdown": curve["drawdown"].min(),
                "avg_turnover": curve["turnover"].mean(),
                "periods": int(len(curve)),
                "rebalance_freq_days": rebalance_freq,
            }
        ]
    )
    return curve, summary
