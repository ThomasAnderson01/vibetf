from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .results import ExperimentResult, FactorResult


def _save_frame(frame: pd.DataFrame, path: Path, index: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=index)


def _save_factor_outputs(base_dir: Path, factor_result: FactorResult, nested: bool = True) -> None:
    factor_dir = base_dir / factor_result.name if nested else base_dir
    factor_dir.mkdir(parents=True, exist_ok=True)
    for horizon, frame in factor_result.ic_summary.items():
        _save_frame(frame, factor_dir / f"ic_summary_{horizon}d.csv", index=False)
    for horizon, series in factor_result.ic_series.items():
        _save_frame(series.rename("ic").to_frame(), factor_dir / f"ic_daily_{horizon}d.csv")
    for horizon, frame in factor_result.quantile_returns.items():
        _save_frame(frame, factor_dir / f"quantile_returns_{horizon}d.csv")
    for horizon, frame in factor_result.quantile_summary.items():
        _save_frame(frame, factor_dir / f"quantile_summary_{horizon}d.csv")
    _save_frame(
        factor_result.autocorrelation_series.rename("autocorrelation").to_frame(),
        factor_dir / "autocorrelation_daily.csv",
    )
    _save_frame(factor_result.autocorrelation_summary, factor_dir / "autocorrelation_summary.csv", index=False)
    _save_frame(factor_result.portfolio_curve, factor_dir / "portfolio_curve.csv", index=False)
    _save_frame(factor_result.portfolio_summary, factor_dir / "portfolio_summary.csv", index=False)


def save_outputs(
    output_dir: str | Path,
    experiment_result: ExperimentResult,
    run_metadata: dict[str, Any] | None = None,
) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    for factor_result in experiment_result.study_result.factor_results.values():
        _save_factor_outputs(out_dir / "factors", factor_result)

    _save_frame(experiment_result.factor_ic_summary, out_dir / "factor_ic_summary.csv", index=False)
    _save_frame(experiment_result.factor_correlation, out_dir / "factor_correlation.csv")

    if experiment_result.composite_result is not None:
        composite = experiment_result.composite_result
        _save_frame(composite.weights, out_dir / "composite_factor_weights.csv")
        if composite.ic_history is not None:
            _save_frame(composite.ic_history, out_dir / "rolling_ic_history.csv")
        _save_factor_outputs(out_dir / "composite", composite.factor_result, nested=False)

    if run_metadata is not None:
        metadata_path = out_dir / "run_metadata.json"
        metadata_path.write_text(json.dumps(run_metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    return out_dir
