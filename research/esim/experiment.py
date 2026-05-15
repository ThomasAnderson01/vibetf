from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from .composite import build_composite_signal
from .config import CompositeConfig, DataConfig, FactorSpec, PortfolioConfig, ResearchConfig
from .data import load_partitioned_daily_table, merge_metadata
from .pipeline import evaluate_factor_results, run_factor_study
from .results import CompositeResult, ExperimentResult


def build_factor_ic_summary(experiment_result: ExperimentResult) -> pd.DataFrame:
    rows: list[dict[str, float | int | str]] = []
    for factor_name, factor_result in experiment_result.study_result.factor_results.items():
        for horizon, summary in factor_result.ic_summary.items():
            row = {"factor": factor_name, "horizon": horizon}
            row.update(summary.iloc[0].to_dict())
            rows.append(row)

    if experiment_result.composite_result is not None:
        composite_factor = experiment_result.composite_result.factor_result
        for horizon, summary in composite_factor.ic_summary.items():
            row = {"factor": experiment_result.composite_result.name, "horizon": horizon}
            row.update(summary.iloc[0].to_dict())
            rows.append(row)

    return pd.DataFrame(rows)


def compute_factor_correlation(prepared_bars: pd.DataFrame, factor_names: list[str]) -> pd.DataFrame:
    if not factor_names:
        return pd.DataFrame()
    return prepared_bars[factor_names].corr()


def run_experiment(
    daily_bars: pd.DataFrame | str | Path,
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
    data_config = data_config or DataConfig()
    research_config = research_config or ResearchConfig()
    portfolio_config = portfolio_config or PortfolioConfig()

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

    experiment_result = ExperimentResult(
        study_result=study_result,
        factor_ic_summary=pd.DataFrame(),
        factor_correlation=factor_correlation,
        composite_result=composite_result,
    )
    return ExperimentResult(
        study_result=study_result,
        factor_ic_summary=build_factor_ic_summary(experiment_result),
        factor_correlation=factor_correlation,
        composite_result=composite_result,
    )


def default_paths() -> tuple[Path, Path, Path]:
    repo_root = Path(__file__).resolve().parents[2]
    daily_root = repo_root / "data" / "raw" / "dmgr" / "tushare" / "fund_daily"
    metadata_path = repo_root / "research" / "outputs" / "etf_liquidity_snapshot_20260514.csv"
    output_dir = repo_root / "research" / "esim" / "output" / f"dmgr_stock_etf_{date.today():%Y%m%d}"
    return daily_root, metadata_path, output_dir


def load_real_etf_dataset(
    daily_root: Path,
    start_date: str,
    end_date: str,
    metadata_path: Path | None = None,
) -> pd.DataFrame:
    daily_bars = load_partitioned_daily_table(
        root=daily_root,
        file_prefix="fund_daily",
        start_date=start_date,
        end_date=end_date,
    )
    fund_share_root = daily_root.parent / "fund_share"
    if fund_share_root.exists():
        fund_share = load_partitioned_daily_table(
            root=fund_share_root,
            file_prefix="fund_share",
            start_date=start_date,
            end_date=end_date,
        )
        if {"ts_code", "trade_date", "fd_share"}.issubset(fund_share.columns):
            daily_bars = daily_bars.merge(
                fund_share[["ts_code", "trade_date", "fd_share"]].drop_duplicates(
                    ["ts_code", "trade_date"],
                    keep="last",
                ),
                on=["ts_code", "trade_date"],
                how="left",
            )
    if metadata_path is None:
        return daily_bars

    metadata = pd.read_csv(
        metadata_path,
        usecols=[
            "ts_code",
            "extname",
            "mgr_name",
            "index_code",
            "index_name",
            "asset_type",
            "stock_subtype",
        ],
    )
    dataset = merge_metadata(daily_bars, metadata)
    dataset["asset_type"] = dataset["asset_type"].fillna("其他")
    return dataset
