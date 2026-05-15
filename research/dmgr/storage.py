from __future__ import annotations

from pathlib import Path

import pandas as pd


def build_dump_path(dump_root: Path, source_name: str, table_name: str, trade_date: str) -> Path:
    year = trade_date[:4]
    month = trade_date[4:6]
    return dump_root / source_name / table_name / year / month / f"{table_name}.{trade_date}.csv"


def write_csv(frame: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_path, index=False, encoding="utf-8")
