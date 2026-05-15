from __future__ import annotations

from typing import Iterable

import pandas as pd

def validate_columns(df: pd.DataFrame, required: Iterable[str], dataset_name: str) -> None:
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"{dataset_name} 缺少必要字段: {missing}")


def normalize_trade_date(series: pd.Series) -> pd.Series:
    as_text = (
        series.astype(str)
        .str.replace(r"\.0+$", "", regex=True)
        .str.strip()
    )
    parsed = pd.to_datetime(as_text, format="%Y%m%d", errors="coerce")
    fallback_mask = parsed.isna()
    if fallback_mask.any():
        parsed.loc[fallback_mask] = pd.to_datetime(as_text.loc[fallback_mask], errors="coerce")
    return parsed.dt.normalize()


def infer_horizon_from_return_column(return_column: str) -> int:
    prefix = "fwd_ret_"
    suffix = "d"
    if not return_column.startswith(prefix) or not return_column.endswith(suffix):
        raise ValueError(f"无法从收益列推断持有期: {return_column}")
    return int(return_column.removeprefix(prefix).removesuffix(suffix))
