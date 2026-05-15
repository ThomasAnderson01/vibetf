from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class TableSpec:
    name: str
    date_parameter_mode: str


@dataclass(frozen=True)
class DumpResult:
    source_name: str
    table_name: str
    requested_dates: int
    written_files: int
    skipped_files: int
    empty_dates: int
    output_paths: tuple[Path, ...] = field(default_factory=tuple)


class DataSourceAdapter(Protocol):
    source_name: str

    def list_tables(self) -> tuple[TableSpec, ...]:
        ...

    def get_trade_dates(self, start_date: str, end_date: str) -> list[str]:
        ...

    def fetch_table(self, table: TableSpec, trade_date: str) -> pd.DataFrame:
        ...
