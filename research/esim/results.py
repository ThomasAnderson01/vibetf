from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(frozen=True)
class FactorResult:
    name: str
    panel: pd.DataFrame
    ic_series: dict[int, pd.Series]
    ic_summary: dict[int, pd.DataFrame]
    quantile_returns: dict[int, pd.DataFrame]
    quantile_summary: dict[int, pd.DataFrame]
    autocorrelation_series: pd.Series
    autocorrelation_summary: pd.DataFrame
    portfolio_curve: pd.DataFrame
    portfolio_summary: pd.DataFrame


@dataclass(frozen=True)
class CompositeResult:
    name: str
    factor_name: str
    factor_result: FactorResult
    weights: pd.DataFrame
    ic_history: pd.DataFrame | None = None


@dataclass(frozen=True)
class StudyResult:
    prepared_bars: pd.DataFrame
    factor_results: dict[str, FactorResult] = field(default_factory=dict)

    def get_factor(self, name: str) -> FactorResult:
        return self.factor_results[name]


@dataclass(frozen=True)
class ExperimentResult:
    study_result: StudyResult
    factor_ic_summary: pd.DataFrame
    factor_correlation: pd.DataFrame
    composite_result: CompositeResult | None = None
