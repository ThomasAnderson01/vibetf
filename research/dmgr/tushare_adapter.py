from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time

import pandas as pd
import tushare as ts

from .config import TushareConfig
from .models import TableSpec


class RateLimiter:
    def __init__(self, rate_limit_per_minute: int) -> None:
        if rate_limit_per_minute <= 0:
            raise ValueError("rate_limit_per_minute 必须大于 0")
        self._min_interval_seconds = 60.0 / rate_limit_per_minute
        self._last_call_timestamp = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last_call_timestamp
        if elapsed < self._min_interval_seconds:
            time.sleep(self._min_interval_seconds - elapsed)
        self._last_call_timestamp = time.monotonic()


@dataclass(frozen=True)
class EndpointSpec:
    endpoint_name: str
    date_parameter_mode: str


class TushareETFAdapter:
    source_name = "tushare"

    def __init__(self, config: TushareConfig) -> None:
        self._pro = ts.pro_api(config.token)
        self._limiter = RateLimiter(config.rate_limit_per_minute)
        self._endpoint_specs: dict[str, EndpointSpec] = {
            "etf_basic": EndpointSpec(endpoint_name="etf_basic", date_parameter_mode="snapshot"),
            "fund_daily": EndpointSpec(endpoint_name="fund_daily", date_parameter_mode="trade_date"),
            "fund_adj": EndpointSpec(endpoint_name="fund_adj", date_parameter_mode="trade_date"),
            "fund_share": EndpointSpec(endpoint_name="fund_share", date_parameter_mode="date_range"),
        }

    def list_tables(self) -> tuple[TableSpec, ...]:
        return tuple(
            TableSpec(name=table_name, date_parameter_mode=spec.date_parameter_mode)
            for table_name, spec in self._endpoint_specs.items()
        )

    def get_trade_dates(self, start_date: str, end_date: str) -> list[str]:
        self._limiter.wait()
        calendar = self._pro.trade_cal(
            exchange="SSE",
            start_date=start_date,
            end_date=end_date,
            is_open="1",
        )
        if calendar.empty:
            return []
        return sorted(calendar["cal_date"].astype(str).tolist())

    def fetch_table(self, table: TableSpec, trade_date: str) -> pd.DataFrame:
        endpoint = self._endpoint_specs[table.name]
        api_func = self._resolve_endpoint(endpoint.endpoint_name)
        kwargs = self._build_date_kwargs(endpoint.date_parameter_mode, trade_date)
        frame = self._paged_fetch(api_func, **kwargs)
        return frame.reset_index(drop=True)

    def _resolve_endpoint(self, endpoint_name: str) -> Callable[..., pd.DataFrame]:
        return getattr(self._pro, endpoint_name)

    def _build_date_kwargs(self, date_parameter_mode: str, trade_date: str) -> dict[str, str]:
        if date_parameter_mode == "trade_date":
            return {"trade_date": trade_date}
        if date_parameter_mode == "date_range":
            return {"start_date": trade_date, "end_date": trade_date}
        if date_parameter_mode == "snapshot":
            return {}
        raise ValueError(f"未知的 date_parameter_mode: {date_parameter_mode}")

    def _paged_fetch(
        self,
        api_func: Callable[..., pd.DataFrame],
        page_size: int = 2000,
        **kwargs: str,
    ) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        offset = 0

        while True:
            self._limiter.wait()
            frame = api_func(limit=page_size, offset=offset, **kwargs)
            if frame is None or frame.empty:
                break
            frames.append(frame)
            if len(frame) < page_size:
                break
            offset += page_size

        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)
