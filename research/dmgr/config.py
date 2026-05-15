from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class StorageConfig:
    dump_root: Path


@dataclass(frozen=True)
class TushareConfig:
    token: str
    rate_limit_per_minute: int = 180


@dataclass(frozen=True)
class DmgrConfig:
    project_root: Path
    storage: StorageConfig
    tushare: TushareConfig


def load_dmgr_config(config_path: Path | None = None) -> DmgrConfig:
    resolved_config_path = config_path or Path(__file__).resolve().parents[1] / "config.toml"
    payload = tomllib.loads(resolved_config_path.read_text(encoding="utf-8"))
    project_root = resolved_config_path.parent.parent
    dump_dir = Path(payload["storage"]["dump_dir"])
    dump_root = dump_dir if dump_dir.is_absolute() else (project_root / dump_dir).resolve()
    return DmgrConfig(
        project_root=project_root,
        storage=StorageConfig(dump_root=dump_root / "dmgr"),
        tushare=TushareConfig(
            token=payload["tushare"]["token"],
            rate_limit_per_minute=int(payload["tushare"].get("rate_limit_per_minute", 180)),
        ),
    )
