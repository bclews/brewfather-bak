"""Orchestrates a full Brewfather backup into a timestamped snapshot directory."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from .client import BrewfatherClient
from .config import Settings

INVENTORY_TYPES: tuple[str, ...] = ("fermentables", "hops", "yeasts", "miscs")

# Top-level resource groups that ``--only`` can select.
GROUPS: tuple[str, ...] = ("recipes", "batches", "inventory")


@dataclass(frozen=True)
class BackupSummary:
    """Result of a backup run."""

    path: Path
    timestamp: str
    counts: dict[str, int]


def _tool_version() -> str:
    try:
        return version("brewfather-backup")
    except PackageNotFoundError:  # pragma: no cover - only when running from source tree
        return "0.0.0+unknown"


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_backup(
    settings: Settings,
    *,
    client: BrewfatherClient | None = None,
    only: Iterable[str] | None = None,
    now: datetime | None = None,
) -> BackupSummary:
    """Fetch the selected resources in full and write a snapshot to disk.

    ``only`` restricts the run to a subset of :data:`GROUPS`; by default every
    group is backed up.
    """
    selected = set(only) if only is not None else set(GROUPS)
    timestamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H-%M-%SZ")
    snapshot = settings.output_dir / timestamp

    owned_client = client is None
    client = client or BrewfatherClient(settings)
    counts: dict[str, int] = {}
    try:
        if "recipes" in selected:
            records = list(client.iter_full("/recipes"))
            _write_json(snapshot / "recipes.json", records)
            counts["recipes"] = len(records)

        if "batches" in selected:
            records = list(client.iter_full("/batches"))
            _write_json(snapshot / "batches.json", records)
            counts["batches"] = len(records)

        if "inventory" in selected:
            for inv in INVENTORY_TYPES:
                records = list(client.iter_full(f"/inventory/{inv}"))
                _write_json(snapshot / "inventory" / f"{inv}.json", records)
                counts[f"inventory.{inv}"] = len(records)
    finally:
        if owned_client:
            client.close()

    manifest = {
        "tool": "brewfather-backup",
        "version": _tool_version(),
        "base_url": settings.base_url,
        "timestamp": timestamp,
        "counts": counts,
    }
    _write_json(snapshot / "manifest.json", manifest)

    return BackupSummary(path=snapshot, timestamp=timestamp, counts=counts)
