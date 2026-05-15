from __future__ import annotations

import argparse
from datetime import date
import logging

from .core import dump_etf_raw_data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dump ETF raw data to partitioned CSV files.")
    parser.add_argument("--source", default="tushare", help="Data source name.")
    parser.add_argument("--start-date", default="20260101", help="Inclusive start date in YYYYMMDD format.")
    parser.add_argument(
        "--end-date",
        default=date.today().strftime("%Y%m%d"),
        help="Inclusive end date in YYYYMMDD format.",
    )
    parser.add_argument(
        "--tables",
        nargs="*",
        default=None,
        help="Optional table names. Defaults to all tables provided by the source adapter.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files instead of skipping them.",
    )
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    args = build_parser().parse_args()
    results = dump_etf_raw_data(
        start_date=args.start_date,
        end_date=args.end_date,
        source_name=args.source,
        tables=args.tables,
        skip_existing=not args.force,
    )
    for result in results:
        print(
            f"{result.source_name}.{result.table_name}: "
            f"requested={result.requested_dates} written={result.written_files} "
            f"skipped={result.skipped_files} empty={result.empty_dates}"
        )


if __name__ == "__main__":
    main()
