from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from research.esim.composite import build_composite_signal
from research.esim.config import CompositeConfig, DataConfig, FactorSpec, PortfolioConfig, ResearchConfig
from research.esim.data import load_real_etf_dataset
from research.esim.experiment import run_experiment
from research.esim.factors import compute_raw_factor_frame
from research.esim.report import save_outputs
from research.esim.sample_data import make_sample_stock_etf_daily_data


class TestEsimFramework(unittest.TestCase):
    def test_equal_composite_signal(self) -> None:
        sample_bars = make_sample_stock_etf_daily_data(instruments=12, days=120)
        result = run_experiment(
            daily_bars=sample_bars,
            factor_specs=[FactorSpec(name="fdr"), FactorSpec(name="vcr"), FactorSpec(name="rstd1m")],
            research_config=ResearchConfig(horizons=(1, 2, 5, 20), quantiles=5, min_history=60, min_avg_amount_100m=0.0),
            portfolio_config=PortfolioConfig(top_n=5, min_names=5, return_column="fwd_ret_5d", rebalance_freq_days=5),
        )
        signal, weights, ic_history = build_composite_signal(
            prepared_bars=result.study_result.prepared_bars,
            factor_results=result.study_result.factor_results,
            composite_config=CompositeConfig(method="equal", factor_names=("fdr", "vcr", "rstd1m")),
            data_config=DataConfig(),
        )
        self.assertIsNone(ic_history)
        self.assertFalse(signal.dropna().empty)
        self.assertTrue((weights == 1.0 / 3.0).all().all())

    def test_rolling_ic_experiment(self) -> None:
        sample_bars = make_sample_stock_etf_daily_data(instruments=16, days=180)
        result = run_experiment(
            daily_bars=sample_bars,
            factor_specs=[FactorSpec(name="fdr"), FactorSpec(name="vcr"), FactorSpec(name="rstd1m")],
            research_config=ResearchConfig(horizons=(1, 2, 5, 20), quantiles=5, min_history=60, min_avg_amount_100m=0.0),
            portfolio_config=PortfolioConfig(top_n=5, min_names=5, return_column="fwd_ret_5d", rebalance_freq_days=5),
            composite_config=CompositeConfig(
                method="rolling_ic",
                factor_names=("fdr", "vcr", "rstd1m"),
                ic_horizon=5,
                ic_lookback=20,
                name="rolling_ic_composite",
            ),
        )
        self.assertIsNotNone(result.composite_result)
        assert result.composite_result is not None
        self.assertFalse(result.composite_result.weights.empty)
        self.assertFalse(result.factor_ic_summary.empty)
        self.assertIn("rolling_ic_composite", set(result.factor_ic_summary["factor"]))

    def test_rolling_ic_weights_do_not_use_unrealized_future_ic(self) -> None:
        sample_bars = make_sample_stock_etf_daily_data(instruments=24, days=220)

        def _run(frame: pd.DataFrame):
            return run_experiment(
                daily_bars=frame,
                factor_specs=[FactorSpec(name="fdr"), FactorSpec(name="vcr"), FactorSpec(name="rstd1m")],
                research_config=ResearchConfig(horizons=(1, 2, 5, 20), quantiles=5, min_history=60, min_avg_amount_100m=0.0),
                portfolio_config=PortfolioConfig(top_n=5, min_names=5, return_column="fwd_ret_5d", rebalance_freq_days=5),
                composite_config=CompositeConfig(
                    method="rolling_ic",
                    factor_names=("fdr", "vcr", "rstd1m"),
                    ic_horizon=5,
                    ic_lookback=20,
                    name="rolling_ic_composite",
                ),
            )

        baseline = _run(sample_bars)
        cutoff = pd.Timestamp(sorted(sample_bars["trade_date"].unique())[180])
        mutated = sample_bars.copy()
        future_mask = mutated["trade_date"] > cutoff
        rank = mutated.loc[future_mask, "trade_date"].rank(method="dense").to_numpy()
        mutated.loc[future_mask, "close"] = mutated.loc[future_mask, "close"].to_numpy() * (1.0 + 0.35 * np.sin(rank))
        mutated.loc[future_mask, "open"] = mutated.loc[future_mask, "open"].to_numpy() * (1.0 + 0.25 * np.cos(rank))
        mutated.loc[future_mask, "high"] = np.maximum(
            mutated.loc[future_mask, "high"].to_numpy(),
            np.maximum(
                mutated.loc[future_mask, "open"].to_numpy(),
                mutated.loc[future_mask, "close"].to_numpy(),
            ),
        )
        mutated.loc[future_mask, "low"] = np.minimum(
            mutated.loc[future_mask, "low"].to_numpy(),
            np.minimum(
                mutated.loc[future_mask, "open"].to_numpy(),
                mutated.loc[future_mask, "close"].to_numpy(),
            ),
        )

        changed = _run(mutated)
        baseline_weights = baseline.composite_result.weights.loc[lambda df: df.index <= cutoff]
        changed_weights = changed.composite_result.weights.loc[lambda df: df.index <= cutoff]
        pd.testing.assert_frame_equal(baseline_weights, changed_weights)

    def test_real_data_loader_and_output_save(self) -> None:
        sample_bars = make_sample_stock_etf_daily_data(instruments=8, days=80)
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            daily_root = root / "dmgr" / "tushare" / "fund_daily"
            metadata_path = root / "metadata.csv"

            for trade_date, frame in sample_bars.groupby("trade_date"):
                date_text = pd.Timestamp(trade_date).strftime("%Y%m%d")
                file_dir = daily_root / date_text[:4] / date_text[4:6]
                file_dir.mkdir(parents=True, exist_ok=True)
                frame.to_csv(file_dir / f"fund_daily.{date_text}.csv", index=False)

            sample_bars[["ts_code", "extname", "mgr_name", "index_name", "asset_type", "stock_subtype"]].drop_duplicates(
                "ts_code"
            ).assign(index_code="TEST").to_csv(metadata_path, index=False)

            dataset = load_real_etf_dataset(
                daily_root=daily_root,
                start_date="20240101",
                end_date="20251231",
                metadata_path=metadata_path,
            )
            result = run_experiment(
                daily_bars=dataset,
                factor_specs=[FactorSpec(name="fdr"), FactorSpec(name="vcr"), FactorSpec(name="rstd1m")],
                research_config=ResearchConfig(horizons=(1, 2, 5, 20), quantiles=5, min_history=60, min_avg_amount_100m=0.0),
                portfolio_config=PortfolioConfig(top_n=5, min_names=5, return_column="fwd_ret_5d", rebalance_freq_days=5),
                composite_config=CompositeConfig(method="equal", factor_names=("fdr", "vcr", "rstd1m")),
            )
            output_dir = save_outputs(root / "output", result, run_metadata={"test": True})

            self.assertTrue((output_dir / "factor_ic_summary.csv").exists())
            self.assertTrue((output_dir / "factor_correlation.csv").exists())
            self.assertTrue((output_dir / "composite_factor_weights.csv").exists())
            self.assertTrue((output_dir / "factors" / "fdr" / "ic_summary_1d.csv").exists())
            self.assertTrue((output_dir / "composite" / "portfolio_summary.csv").exists())

    def test_liquidity_factor_formulas(self) -> None:
        dates = pd.bdate_range("2024-01-01", periods=130)
        rows: list[dict[str, float | str | pd.Timestamp]] = []
        for asset_index, ts_code in enumerate(("510001.SH", "510002.SH")):
            fd_share = 25.0 + asset_index * 5.0
            for date_index, trade_date in enumerate(dates):
                close = 1.0 + 0.01 * date_index + 0.05 * asset_index
                open_price = close * (0.998 + 0.001 * asset_index)
                vol = 1_000_000 + 2_000 * date_index + 20_000 * asset_index
                vwap = close * (1.01 + 0.002 * asset_index)
                amount = vol * vwap
                rows.append(
                    {
                        "trade_date": trade_date,
                        "ts_code": ts_code,
                        "open": open_price,
                        "high": max(open_price, close) * 1.01,
                        "low": min(open_price, close) * 0.99,
                        "close": close,
                        "vol": vol,
                        "amount": amount,
                        "fd_share": fd_share,
                        "cap_100m": fd_share * close,
                    }
                )

        raw = pd.DataFrame(rows)
        prepared = raw.sort_values(["ts_code", "trade_date"]).copy()
        prepared["amount_100m"] = prepared["amount"] / 100_000
        prepared["daily_return"] = prepared.groupby("ts_code")["close"].pct_change()

        factor_frame = compute_raw_factor_frame(
            prepared,
            [
                FactorSpec(name="tvr1m"),
                FactorSpec(name="liquidity_quality"),
            ],
            DataConfig(),
        )

        asset_mask = factor_frame["ts_code"] == "510001.SH"
        latest_row = factor_frame.loc[asset_mask].iloc[-1]
        asset_series = factor_frame.loc[asset_mask]
        turnover_ratio = asset_series["amount_100m"] / asset_series["cap_100m"]
        expected_tvr1m = -np.log(turnover_ratio.iloc[-21:].sum())
        self.assertAlmostEqual(float(latest_row["tvr1m_raw"]), float(expected_tvr1m))

        latest_date = factor_frame["trade_date"].max()
        latest_slice = factor_frame[factor_frame["trade_date"] == latest_date].copy()
        amihud_mean = (
            factor_frame["daily_return"].abs() / factor_frame["amount_100m"]
        ).groupby(factor_frame["ts_code"]).tail(126).groupby(factor_frame["ts_code"]).mean()
        liquidity_mean = factor_frame.groupby("ts_code")["amount_100m"].tail(21).groupby(factor_frame["ts_code"]).mean()
        ranked_amihud = amihud_mean.rank(method="average", pct=True)
        ranked_liquidity = liquidity_mean.rank(method="average", pct=True)
        expected_liquidity_quality = -ranked_amihud * (ranked_liquidity - 0.5)
        actual = latest_slice.set_index("ts_code")["liquidity_quality_raw"]
        pd.testing.assert_series_equal(
            actual.sort_index(),
            expected_liquidity_quality.rename("liquidity_quality_raw").sort_index(),
            check_exact=False,
            atol=1e-12,
            rtol=1e-12,
        )


if __name__ == "__main__":
    unittest.main()
