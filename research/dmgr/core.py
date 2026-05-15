from __future__ import annotations

from collections.abc import Iterable
import logging
from pathlib import Path

from .config import DmgrConfig, load_dmgr_config
from .models import DataSourceAdapter, DumpResult, TableSpec
from .storage import build_dump_path, write_csv
from .tushare_adapter import TushareETFAdapter


LOGGER = logging.getLogger(__name__)


class DumpManager:
    def __init__(self, config: DmgrConfig, adapters: Iterable[DataSourceAdapter] | None = None) -> None:
        self._config = config
        configured_adapters = tuple(adapters) if adapters is not None else (TushareETFAdapter(config.tushare),)
        self._adapters = {adapter.source_name: adapter for adapter in configured_adapters}

    def list_sources(self) -> tuple[str, ...]:
        return tuple(self._adapters)

    def list_tables(self, source_name: str) -> tuple[TableSpec, ...]:
        return self._require_adapter(source_name).list_tables()

    def dump_range(
        self,
        source_name: str,
        start_date: str,
        end_date: str,
        tables: Iterable[str] | None = None,
        skip_existing: bool = True,
    ) -> list[DumpResult]:
        adapter = self._require_adapter(source_name)
        trade_dates = adapter.get_trade_dates(start_date=start_date, end_date=end_date)
        requested_tables = self._resolve_tables(adapter, tables)
        return [
            self._dump_table(
                adapter=adapter,
                table=table,
                trade_dates=trade_dates,
                skip_existing=skip_existing,
            )
            for table in requested_tables
        ]

    def _dump_table(
        self,
        adapter: DataSourceAdapter,
        table: TableSpec,
        trade_dates: list[str],
        skip_existing: bool,
    ) -> DumpResult:
        written_paths: list[Path] = []
        skipped_files = 0
        empty_dates = 0

        for trade_date in trade_dates:
            output_path = build_dump_path(
                dump_root=self._config.storage.dump_root,
                source_name=adapter.source_name,
                table_name=table.name,
                trade_date=trade_date,
            )
            if skip_existing and output_path.exists():
                skipped_files += 1
                continue

            frame = adapter.fetch_table(table=table, trade_date=trade_date)
            if frame.empty:
                empty_dates += 1
                LOGGER.info("Skip empty payload: source=%s table=%s trade_date=%s", adapter.source_name, table.name, trade_date)
                continue

            write_csv(frame, output_path)
            written_paths.append(output_path)
            LOGGER.info("Wrote %s rows to %s", len(frame), output_path)

        return DumpResult(
            source_name=adapter.source_name,
            table_name=table.name,
            requested_dates=len(trade_dates),
            written_files=len(written_paths),
            skipped_files=skipped_files,
            empty_dates=empty_dates,
            output_paths=tuple(written_paths),
        )

    def _require_adapter(self, source_name: str) -> DataSourceAdapter:
        try:
            return self._adapters[source_name]
        except KeyError as exc:
            raise KeyError(f"未知数据源: {source_name}") from exc

    def _resolve_tables(self, adapter: DataSourceAdapter, tables: Iterable[str] | None) -> tuple[TableSpec, ...]:
        available_tables = {table.name: table for table in adapter.list_tables()}
        if tables is None:
            return tuple(available_tables.values())

        resolved: list[TableSpec] = []
        for table_name in tables:
            try:
                resolved.append(available_tables[table_name])
            except KeyError as exc:
                raise KeyError(f"数据源 {adapter.source_name} 不支持表: {table_name}") from exc
        return tuple(resolved)


def dump_etf_raw_data(
    start_date: str,
    end_date: str,
    source_name: str = "tushare",
    tables: Iterable[str] | None = None,
    skip_existing: bool = True,
    config: DmgrConfig | None = None,
) -> list[DumpResult]:
    dump_manager = DumpManager(config=config or load_dmgr_config())
    return dump_manager.dump_range(
        source_name=source_name,
        start_date=start_date,
        end_date=end_date,
        tables=tables,
        skip_existing=skip_existing,
    )
