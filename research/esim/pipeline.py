from __future__ import annotations

from pathlib import Path

import pandas as pd

from .analytics import (
    add_factor_quantiles,
    build_factor_panel,
    compute_factor_autocorrelation,
    compute_ic_series,
    compute_quantile_return_table,
    summarize_ic,
    summarize_autocorrelation,
    summarize_quantile_returns,
)
from .config import DataConfig, FactorSpec, PortfolioConfig, ResearchConfig
from .data import load_table, prepare_daily_bars
from .factors import compute_raw_factor_frame, normalize_factor_frame
from .labels import add_forward_returns
from .portfolio import simulate_top_n_portfolio
from .results import FactorResult, StudyResult


def prepare_study_dataset(
    daily_bars: str | Path | pd.DataFrame,
    factor_specs: list[FactorSpec],
    data_config: DataConfig | None = None,
    research_config: ResearchConfig | None = None,
) -> tuple[pd.DataFrame, DataConfig, ResearchConfig]:
    data_config = data_config or DataConfig()
    research_config = research_config or ResearchConfig()

    if isinstance(daily_bars, (str, Path)):
        bar_frame = load_table(daily_bars)
    else:
        bar_frame = daily_bars.copy()

    dataset = prepare_daily_bars(bar_frame, data_config, research_config)
    dataset = compute_raw_factor_frame(dataset, factor_specs, data_config)
    dataset = add_forward_returns(dataset, research_config.horizons, data_config)
    eligible_dataset = dataset[dataset["is_eligible"]].copy()
    eligible_dataset = normalize_factor_frame(
        eligible_dataset,
        factor_specs,
        data_config,
        research_config,
    )
    return eligible_dataset, data_config, research_config


def evaluate_factor_results(
    prepared_bars: pd.DataFrame,
    factor_names: list[str],
    data_config: DataConfig,
    research_config: ResearchConfig,
    portfolio_config: PortfolioConfig,
) -> dict[str, FactorResult]:
    results: dict[str, FactorResult] = {}
    for factor_name in factor_names:
        panel = build_factor_panel(
            prepared_bars,
            factor_name,
            research_config.horizons,
            data_config,
        )
        panel = add_factor_quantiles(
            panel,
            factor_name,
            research_config.quantiles,
            trade_date_column=data_config.trade_date_column,
        )

        ic_series_by_horizon: dict[int, pd.Series] = {}
        ic_summary_by_horizon: dict[int, pd.DataFrame] = {}
        quantile_returns_by_horizon: dict[int, pd.DataFrame] = {}
        quantile_summary_by_horizon: dict[int, pd.DataFrame] = {}
        for horizon in research_config.horizons:
            return_column = f"fwd_ret_{horizon}d"
            ic_series = compute_ic_series(
                panel,
                factor_name,
                return_column,
                trade_date_column=data_config.trade_date_column,
            )
            quantile_table = compute_quantile_return_table(
                panel,
                return_column,
                trade_date_column=data_config.trade_date_column,
            )
            ic_series_by_horizon[horizon] = ic_series
            ic_summary_by_horizon[horizon] = summarize_ic(ic_series, nw_lag=max(horizon - 1, 1))
            quantile_returns_by_horizon[horizon] = quantile_table
            quantile_summary_by_horizon[horizon] = summarize_quantile_returns(quantile_table)

        autocorrelation_series = compute_factor_autocorrelation(
            panel,
            factor_name,
            instrument_column=data_config.instrument_column,
            trade_date_column=data_config.trade_date_column,
        )
        autocorrelation_summary = summarize_autocorrelation(autocorrelation_series)

        portfolio_curve, portfolio_summary = simulate_top_n_portfolio(
            panel,
            factor_name,
            portfolio_config,
            data_config,
        )
        results[factor_name] = FactorResult(
            name=factor_name,
            panel=panel,
            ic_series=ic_series_by_horizon,
            ic_summary=ic_summary_by_horizon,
            quantile_returns=quantile_returns_by_horizon,
            quantile_summary=quantile_summary_by_horizon,
            autocorrelation_series=autocorrelation_series,
            autocorrelation_summary=autocorrelation_summary,
            portfolio_curve=portfolio_curve,
            portfolio_summary=portfolio_summary,
        )
    return results


def run_factor_study(
    daily_bars: str | Path | pd.DataFrame,
    factor_specs: list[FactorSpec],
    data_config: DataConfig | None = None,
    research_config: ResearchConfig | None = None,
    portfolio_config: PortfolioConfig | None = None,
) -> StudyResult:
    portfolio_config = portfolio_config or PortfolioConfig()
    eligible_dataset, data_config, research_config = prepare_study_dataset(
        daily_bars=daily_bars,
        factor_specs=factor_specs,
        data_config=data_config,
        research_config=research_config,
    )

    results = evaluate_factor_results(
        prepared_bars=eligible_dataset,
        factor_names=[spec.name for spec in factor_specs],
        data_config=data_config,
        research_config=research_config,
        portfolio_config=portfolio_config,
    )
    return StudyResult(prepared_bars=eligible_dataset, factor_results=results)
