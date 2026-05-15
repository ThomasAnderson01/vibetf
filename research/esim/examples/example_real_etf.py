from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from research.esim.config import CompositeConfig, FactorSpec, PortfolioConfig, ResearchConfig
from research.esim.data import default_paths, load_real_etf_dataset
from research.esim.experiment import run_experiment
from research.esim.report import save_outputs


def main() -> None:
    daily_root, metadata_path, default_output_dir = default_paths()
    output_dir = default_output_dir.parent / "example_real_etf"
    dataset = load_real_etf_dataset(
        daily_root=daily_root,
        start_date="20260101",
        end_date="20260514",
        metadata_path=metadata_path,
    )
    result = run_experiment(
        daily_bars=dataset,
        factor_specs=[
            FactorSpec(name="fdr"),
            FactorSpec(name="vcr"),
            FactorSpec(name="rstd1m"),
        ],
        research_config=ResearchConfig(horizons=(1, 2, 5, 20), quantiles=5, min_history=60, min_avg_amount_100m=1.0),
        portfolio_config=PortfolioConfig(top_n=10, min_names=10, cost_bps=5.0, return_column="fwd_ret_5d", rebalance_freq_days=5),
        composite_config=CompositeConfig(method="rolling_ic", factor_names=("fdr", "vcr", "rstd1m"), name="rolling_ic_composite"),
    )
    save_outputs(output_dir, result, run_metadata={"example": "real_etf"})
    print(f"Done. Output saved to: {output_dir}")


if __name__ == "__main__":
    main()
