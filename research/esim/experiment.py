from __future__ import annotations

import pandas as pd

from .composite import build_composite_signal
from .config import CompositeConfig, DataConfig, FactorSpec, PortfolioConfig, ResearchConfig
from .pipeline import evaluate_factor_results, run_factor_study
from .results import CompositeResult, ExperimentResult


def build_factor_ic_summary(
    study_result: "StudyResult",
    composite_result: CompositeResult | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for factor_name, factor_result in study_result.factor_results.items():
        for horizon, summary in factor_result.ic_summary.items():
            row = {"factor": factor_name, "horizon": horizon}
            row.update(summary.iloc[0].to_dict())
            rows.append(row)

    if composite_result is not None:
        for horizon, summary in composite_result.factor_result.ic_summary.items():
            row = {"factor": composite_result.name, "horizon": horizon}
            row.update(summary.iloc[0].to_dict())
            rows.append(row)

    return pd.DataFrame(rows)


def compute_factor_correlation(prepared_bars: pd.DataFrame, factor_names: list[str]) -> pd.DataFrame:
    if not factor_names:
        return pd.DataFrame()
    return prepared_bars[factor_names].corr()


def run_experiment(
    daily_bars: pd.DataFrame | str,
    factor_specs: list[FactorSpec],
    data_config: DataConfig | None = None,
    research_config: ResearchConfig | None = None,
    portfolio_config: PortfolioConfig | None = None,
    composite_config: CompositeConfig | None = None,
) -> ExperimentResult:
    study_result = run_factor_study(
        daily_bars=daily_bars,
        factor_specs=factor_specs,
        data_config=data_config,
        research_config=research_config,
        portfolio_config=portfolio_config,
    )
    data_config = study_result.data_config
    research_config = study_result.research_config
    portfolio_config = study_result.portfolio_config

    factor_names = [spec.name for spec in factor_specs]
    factor_correlation = compute_factor_correlation(study_result.prepared_bars, factor_names)

    composite_result: CompositeResult | None = None
    if composite_config is not None:
        composite_signal, weights, ic_history = build_composite_signal(
            prepared_bars=study_result.prepared_bars,
            factor_results=study_result.factor_results,
            composite_config=composite_config,
            data_config=data_config,
        )
        composite_dataset = study_result.prepared_bars.copy()
        composite_dataset[composite_config.name] = composite_signal
        composite_factor_result = evaluate_factor_results(
            prepared_bars=composite_dataset,
            factor_names=[composite_config.name],
            data_config=data_config,
            research_config=research_config,
            portfolio_config=portfolio_config,
        )[composite_config.name]
        composite_result = CompositeResult(
            name=composite_config.name,
            factor_name=composite_config.name,
            factor_result=composite_factor_result,
            weights=weights,
            ic_history=ic_history,
        )

    factor_ic_summary = build_factor_ic_summary(study_result, composite_result)
    return ExperimentResult(
        study_result=study_result,
        factor_ic_summary=factor_ic_summary,
        factor_correlation=factor_correlation,
        composite_result=composite_result,
    )
