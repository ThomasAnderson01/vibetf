from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import DataConfig, ResearchConfig
from .schema import normalize_trade_date, validate_columns


def load_table(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"未找到数据文件: {file_path}")

    if file_path.suffix.lower() == ".csv":
        return pd.read_csv(file_path)
    if file_path.suffix.lower() == ".parquet":
        return pd.read_parquet(file_path)

    raise ValueError(f"不支持的数据格式: {file_path.suffix}")


def load_partitioned_daily_table(
    root: str | Path,
    file_prefix: str,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    data_root = Path(root)
    if not data_root.exists():
        raise FileNotFoundError(f"未找到分区数据目录: {data_root}")

    frames: list[pd.DataFrame] = []
    pattern = f"{file_prefix}.*.csv"
    for file_path in sorted(data_root.rglob(pattern)):
        trade_date = file_path.stem.split(".")[-1]
        if start_date <= trade_date <= end_date:
            frames.append(pd.read_csv(file_path))

    if not frames:
        raise FileNotFoundError(
            f"在 {data_root} 下未找到 {start_date} 到 {end_date} 的 {file_prefix} 分区文件"
        )
    return pd.concat(frames, ignore_index=True)


def merge_metadata(
    daily_bars: pd.DataFrame,
    metadata: pd.DataFrame | str | Path | None,
    instrument_column: str = "ts_code",
) -> pd.DataFrame:
    if metadata is None:
        return daily_bars.copy()
    metadata_frame = load_table(metadata) if isinstance(metadata, (str, Path)) else metadata.copy()
    metadata_frame = metadata_frame.drop_duplicates(subset=[instrument_column], keep="last")
    overlap_columns = [
        column
        for column in metadata_frame.columns
        if column != instrument_column and column in daily_bars.columns
    ]
    merged = daily_bars.merge(
        metadata_frame,
        on=instrument_column,
        how="left",
        suffixes=("", "_meta"),
    )
    for column in overlap_columns:
        meta_column = f"{column}_meta"
        merged[column] = merged[column].combine_first(merged[meta_column])
        merged = merged.drop(columns=[meta_column])
    return merged


def prepare_daily_bars(
    daily_bars: pd.DataFrame,
    data_config: DataConfig,
    research_config: ResearchConfig,
) -> pd.DataFrame:
    df = daily_bars.copy()
    validate_columns(df, data_config.required_bar_columns, "daily_bars")

    df[data_config.trade_date_column] = normalize_trade_date(df[data_config.trade_date_column])
    df = df.sort_values([data_config.instrument_column, data_config.trade_date_column]).drop_duplicates(
        [data_config.instrument_column, data_config.trade_date_column],
        keep="last",
    )

    if data_config.asset_type_column in df.columns:
        df = df[df[data_config.asset_type_column] == data_config.stock_asset_type_value].copy()

    df["amount_100m"] = df[data_config.amount_column] / 100_000
    df["daily_return"] = df.groupby(data_config.instrument_column)[data_config.close_column].pct_change()
    df["history_count"] = df.groupby(data_config.instrument_column).cumcount() + 1
    df["avg_amount_20d"] = (
        df.groupby(data_config.instrument_column)["amount_100m"]
        .transform(lambda s: s.rolling(20, min_periods=20).mean().shift(1))
    )
    df["is_eligible"] = (
        (df["history_count"] >= research_config.min_history)
        & (df["avg_amount_20d"] >= research_config.min_avg_amount_100m)
    )
    return df.reset_index(drop=True)
