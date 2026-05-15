from __future__ import annotations

from .config import FactorSpec, PortfolioConfig, ResearchConfig
from .pipeline import run_factor_study
from .sample_data import make_sample_stock_etf_daily_data


def main() -> None:
    sample_bars = make_sample_stock_etf_daily_data()
    results = run_factor_study(
        daily_bars=sample_bars,
        factor_specs=[
            FactorSpec(name="momentum", params={"window": 20}),
            FactorSpec(name="reversal", params={"window": 5}),
            FactorSpec(name="volatility", params={"window": 20}),
            FactorSpec(name="liquidity", params={"window": 20}),
            FactorSpec(name="volume_trend", params={"window": 20}),
            FactorSpec(name="fdr"),
            FactorSpec(name="vcr"),
            FactorSpec(name="rstd1m"),
        ],
        research_config=ResearchConfig(
            horizons=(1, 2, 5, 20),
            quantiles=5,
            min_history=60,
            min_avg_amount_100m=0.0,
        ),
        portfolio_config=PortfolioConfig(
            top_n=5,
            cost_bps=5.0,
            return_column="fwd_ret_5d",
            min_names=5,
            rebalance_freq_days=5,
        ),
    )

    factor_name = "fdr"
    factor_result = results.get_factor(factor_name)
    print(f"Factor: {factor_name}")
    print("IC summary (1d)")
    print(factor_result.ic_summary[1].to_string(index=False))
    print()
    print("Autocorrelation summary")
    print(factor_result.autocorrelation_summary.to_string(index=False))
    print()
    print("Quantile summary (5d)")
    print(factor_result.quantile_summary[5].to_string())
    print()
    print("Portfolio summary")
    print(factor_result.portfolio_summary.to_string(index=False))


if __name__ == "__main__":
    main()
