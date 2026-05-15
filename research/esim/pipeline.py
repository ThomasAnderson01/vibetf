from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from .analytics import (
    add_factor_quantiles,
    build_factor_panel,
    compute_factor_autocorrelation,
    compute_ic_series,
    compute_quantile_return_table,
    summarize_autocorrelation,
    summarize_ic,
    summarize_quantile_returns,
)
from .config import DataConfig, FactorSpec, PortfolioConfig, ResearchConfig
from .data import load_table, prepare_daily_bars
from .factors import compute_raw_factor_frame, normalize_factor_frame
from .labels import add_forward_returns
from .portfolio import simulate_top_n_portfolio
from .results import FactorResult, StudyResult


@dataclass
class StudyContext:
    df: pd.DataFrame | None = None
    data_config: DataConfig = field(default_factory=DataConfig)
    research_config: ResearchConfig = field(default_factory=ResearchConfig)
    portfolio_config: PortfolioConfig = field(default_factory=PortfolioConfig)
    factor_specs: list[FactorSpec] = field(default_factory=list)
    factor_results: dict[str, FactorResult] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


Step = Callable[[StudyContext], StudyContext]


class StudyPipeline:
    def __init__(self, steps: Sequence[Step] | None = None) -> None:
        self._steps: list[Step] = list(steps) if steps else []

    def add(self, step: Step) -> StudyPipeline:
        self._steps.append(step)
        return self

    def run(self, ctx: StudyContext | None = None) -> StudyResult:
        ctx = ctx or StudyContext()
        for step in self._steps:
            ctx = step(ctx)
        return StudyResult(
            prepared_bars=ctx.df,
            factor_results=ctx.factor_results,
            data_config=ctx.data_config,
            research_config=ctx.research_config,
            portfolio_config=ctx.portfolio_config,
        )


def load_data(daily_bars: str | Path | pd.DataFrame) -> Step:
    def _step(ctx: StudyContext) -> StudyContext:
        if isinstance(daily_bars, (str, Path)):
            ctx.df = load_table(daily_bars)
        else:
            ctx.df = daily_bars.copy()
        return ctx
    return _step


def prepare_bars() -> Step:
    def _step(ctx: StudyContext) -> StudyContext:
        ctx.df = prepare_daily_bars(ctx.df, ctx.data_config, ctx.research_config)
        return ctx
    return _step


def compute_factors() -> Step:
    def _step(ctx: StudyContext) -> StudyContext:
        ctx.df = compute_raw_factor_frame(ctx.df, ctx.factor_specs, ctx.data_config)
        return ctx
    return _step


def add_labels() -> Step:
    def _step(ctx: StudyContext) -> StudyContext:
        ctx.df = add_forward_returns(ctx.df, ctx.research_config.horizons, ctx.data_config)
        return ctx
    return _step


def filter_eligible() -> Step:
    def _step(ctx: StudyContext) -> StudyContext:
        ctx.df = ctx.df[ctx.df["is_eligible"]].copy()
        return ctx
    return _step


def normalize_factors() -> Step:
    def _step(ctx: StudyContext) -> StudyContext:
        ctx.df = normalize_factor_frame(ctx.df, ctx.factor_specs, ctx.data_config, ctx.research_config)
        return ctx
    return _step


def evaluate_factors() -> Step:
    def _step(ctx: StudyContext) -> StudyContext:
        factor_names = [spec.name for spec in ctx.factor_specs]
        ctx.factor_results = _evaluate_factor_results(
            prepared_bars=ctx.df,
            factor_names=factor_names,
            data_config=ctx.data_config,
            research_config=ctx.research_config,
            portfolio_config=ctx.portfolio_config,
        )
        return ctx
    return _step


DEFAULT_STUDY_STEPS: list[Step] = [
    prepare_bars(),
    compute_factors(),
    add_labels(),
    filter_eligible(),
    normalize_factors(),
    evaluate_factors(),
]


def _evaluate_factor_results(
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


def prepare_study_dataset(
    daily_bars: str | Path | pd.DataFrame,
    factor_specs: list[FactorSpec],
    data_config: DataConfig | None = None,
    research_config: ResearchConfig | None = None,
) -> tuple[pd.DataFrame, DataConfig, ResearchConfig]:
    ctx = StudyContext(
        data_config=data_config or DataConfig(),
        research_config=research_config or ResearchConfig(),
        factor_specs=factor_specs,
    )
    pipeline = StudyPipeline([
        load_data(daily_bars),
        *DEFAULT_STUDY_STEPS[:4],
        normalize_factors(),
    ])
    result = pipeline.run(ctx)
    return result.prepared_bars, result.data_config, result.research_config


def evaluate_factor_results(
    prepared_bars: pd.DataFrame,
    factor_names: list[str],
    data_config: DataConfig,
    research_config: ResearchConfig,
    portfolio_config: PortfolioConfig,
) -> dict[str, FactorResult]:
    return _evaluate_factor_results(prepared_bars, factor_names, data_config, research_config, portfolio_config)


def run_factor_study(
    daily_bars: str | Path | pd.DataFrame,
    factor_specs: list[FactorSpec],
    data_config: DataConfig | None = None,
    research_config: ResearchConfig | None = None,
    portfolio_config: PortfolioConfig | None = None,
) -> StudyResult:
    ctx = StudyContext(
        data_config=data_config or DataConfig(),
        research_config=research_config or ResearchConfig(),
        portfolio_config=portfolio_config or PortfolioConfig(),
        factor_specs=factor_specs,
    )
    pipeline = StudyPipeline([
        load_data(daily_bars),
        *DEFAULT_STUDY_STEPS,
    ])
    return pipeline.run(ctx)
