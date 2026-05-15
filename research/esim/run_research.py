from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from research.esim.config import CompositeConfig, FactorSpec, PortfolioConfig, ResearchConfig
from research.esim.data import default_paths, load_real_etf_dataset
from research.esim.experiment import run_experiment
from research.esim.report import save_outputs


def parse_args() -> argparse.Namespace:
    default_daily_root, default_metadata_path, default_output_dir = default_paths()
    parser = argparse.ArgumentParser(description="Run ETF multi-factor research and save outputs.")
    parser.add_argument("--data-root", type=Path, default=default_daily_root)
    parser.add_argument("--metadata", type=Path, default=default_metadata_path)
    parser.add_argument("--output", type=Path, default=default_output_dir)
    parser.add_argument("--start-date", type=str, default="20260101")
    parser.add_argument("--end-date", type=str, default=date.today().strftime("%Y%m%d"))
    parser.add_argument("--factors", type=str, default="fdr,vcr,rstd1m")
    parser.add_argument("--horizons", type=str, default="1,2,5,20")
    parser.add_argument("--quantiles", type=int, default=5)
    parser.add_argument("--min-history", type=int, default=60)
    parser.add_argument("--min-avg-amount-100m", type=float, default=1.0)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-names", type=int, default=10)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument("--return-column", type=str, default="fwd_ret_5d")
    parser.add_argument("--rebalance-freq-days", type=int, default=5)
    parser.add_argument("--composite-method", choices=("equal", "rolling_ic"), default="equal")
    parser.add_argument("--ic-horizon", type=int, default=5)
    parser.add_argument("--ic-lookback", type=int, default=20)
    parser.add_argument("--composite-name", type=str, default="composite")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    factor_names = tuple(name.strip() for name in args.factors.split(",") if name.strip())
    factor_specs = [FactorSpec(name=name) for name in factor_names]
    research_config = ResearchConfig(
        horizons=tuple(int(value) for value in args.horizons.split(",") if value),
        quantiles=args.quantiles,
        min_history=args.min_history,
        min_avg_amount_100m=args.min_avg_amount_100m,
    )
    portfolio_config = PortfolioConfig(
        top_n=args.top_n,
        min_names=args.min_names,
        cost_bps=args.cost_bps,
        return_column=args.return_column,
        rebalance_freq_days=args.rebalance_freq_days,
    )
    composite_config = CompositeConfig(
        method=args.composite_method,
        factor_names=factor_names,
        ic_horizon=args.ic_horizon,
        ic_lookback=args.ic_lookback,
        name=args.composite_name,
    )
    dataset = load_real_etf_dataset(
        daily_root=args.data_root,
        start_date=args.start_date,
        end_date=args.end_date,
        metadata_path=args.metadata,
    )
    result = run_experiment(
        daily_bars=dataset,
        factor_specs=factor_specs,
        research_config=research_config,
        portfolio_config=portfolio_config,
        composite_config=composite_config,
    )
    output_dir = save_outputs(
        args.output,
        experiment_result=result,
        run_metadata={
            "start_date": args.start_date,
            "end_date": args.end_date,
            "factor_names": list(factor_names),
            "research_config": asdict(research_config),
            "portfolio_config": asdict(portfolio_config),
            "composite_config": asdict(composite_config),
            "data_root": str(args.data_root),
            "metadata_path": str(args.metadata),
        },
    )
    print(f"Done. Output saved to: {output_dir}")


if __name__ == "__main__":
    main()
