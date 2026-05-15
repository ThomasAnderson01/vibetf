from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence


@dataclass(frozen=True)
class FactorSpec:
    name: str
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DataConfig:
    asset_type_column: str = "asset_type"
    stock_asset_type_value: str = "股票"
    trade_date_column: str = "trade_date"
    instrument_column: str = "ts_code"
    open_column: str = "open"
    high_column: str = "high"
    low_column: str = "low"
    close_column: str = "close"
    volume_column: str = "vol"
    amount_column: str = "amount"

    @property
    def required_bar_columns(self) -> tuple[str, ...]:
        return (
            self.trade_date_column,
            self.instrument_column,
            self.open_column,
            self.high_column,
            self.low_column,
            self.close_column,
            self.volume_column,
            self.amount_column,
        )

    @property
    def optional_meta_columns(self) -> tuple[str, ...]:
        return (
            self.asset_type_column,
            "stock_subtype",
            "extname",
            "mgr_name",
            "index_name",
        )


@dataclass(frozen=True)
class ResearchConfig:
    horizons: tuple[int, ...] = (1, 2, 5, 20)
    quantiles: int = 5
    min_history: int = 60
    min_avg_amount_100m: float = 1.0
    normalize_factors: bool = True
    clip_zscore: float = 3.0


@dataclass(frozen=True)
class PortfolioConfig:
    top_n: int = 10
    weighting: str = "equal"
    cost_bps: float = 5.0
    return_column: str = "fwd_ret_1d"
    min_names: int = 5
    rebalance_freq_days: int | None = None
    benchmark: Literal["equal_weight_universe", "none"] = "equal_weight_universe"


@dataclass(frozen=True)
class CompositeConfig:
    method: Literal["equal", "rolling_ic"] = "equal"
    factor_names: tuple[str, ...] = field(default_factory=tuple)
    ic_horizon: int = 5
    ic_lookback: int = 20
    name: str = "composite"


@dataclass(frozen=True)
class RunContext:
    daily_bars_path: Path | None = None
    factor_specs: Sequence[FactorSpec] = field(default_factory=tuple)
