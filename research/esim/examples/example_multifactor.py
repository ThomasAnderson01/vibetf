from __future__ import annotations

import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from research.esim.config import CompositeConfig, FactorSpec, PortfolioConfig, ResearchConfig
from research.esim.experiment import run_experiment
from research.esim.report import save_outputs
from research.esim.sample_data import make_sample_stock_etf_daily_data


def main() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    output_dir = repo_root / "research" / "esim" / "output" / "example_multifactor"
    result = run_experiment(
        daily_bars=make_sample_stock_etf_daily_data(),
        factor_specs=[
            FactorSpec(name="fdr"),
            FactorSpec(name="vcr"),
            FactorSpec(name="rstd1m"),
        ],
        research_config=ResearchConfig(horizons=(1, 2, 5, 20), quantiles=5, min_history=60, min_avg_amount_100m=0.0),
        portfolio_config=PortfolioConfig(top_n=5, min_names=5, cost_bps=5.0, return_column="fwd_ret_5d", rebalance_freq_days=5),
        composite_config=CompositeConfig(method="equal", factor_names=("fdr", "vcr", "rstd1m"), name="equal_composite"),
    )
    save_outputs(output_dir, result, run_metadata={"example": "multifactor_sample"})
    print(f"Done. Output saved to: {output_dir}")


if __name__ == "__main__":
    main()
