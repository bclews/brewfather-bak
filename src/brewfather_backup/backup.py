"""Orchestrates a full Brewfather backup into a timestamped snapshot directory."""

from __future__ import annotations

import json
import shutil
import tempfile
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from functools import partial
from pathlib import Path
from typing import Any, Protocol

from . import __version__
from .client import BrewfatherClient
from .config import Settings

INVENTORY_TYPES: tuple[str, ...] = ("fermentables", "hops", "yeasts", "miscs")


class Group(StrEnum):
    """Top-level resource groups that ``--only`` can select."""

    recipes = "recipes"
    batches = "batches"
    inventory = "inventory"


GROUPS: tuple[str, ...] = tuple(group.value for group in Group)


class ProgressReporter(Protocol):
    """Receives progress events during a backup so callers can render feedback.

    The methods carry no-op default bodies so subclasses (e.g. :class:`NullReporter`)
    only override what they care about.
    """

    def resource_started(self, label: str) -> None:
        return None

    def record_fetched(self, label: str) -> None:
        return None

    def resource_finished(self, label: str, count: int) -> None:
        return None


class NullReporter(ProgressReporter):
    """A reporter that does nothing (the default).

    Inherits the protocol's no-op method bodies, so there is a single place to
    update if the reporter interface grows.
    """


def _selected_resources(selected: set[str]) -> list[tuple[str, str, tuple[str, ...]]]:
    """Return ``(label, api_path, snapshot_path_parts)`` for the chosen groups."""
    resources: list[tuple[str, str, tuple[str, ...]]] = []
    if "recipes" in selected:
        resources.append(("recipes", "/recipes", ("recipes.json",)))
    if "batches" in selected:
        resources.append(("batches", "/batches", ("batches.json",)))
    if "inventory" in selected:
        for inv in INVENTORY_TYPES:
            dest = ("inventory", f"{inv}.json")
            resources.append((f"inventory.{inv}", f"/inventory/{inv}", dest))
    return resources


@dataclass(frozen=True)
class BackupSummary:
    """Result of a backup run."""

    path: Path
    timestamp: str
    counts: dict[str, int]


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _fetch_full(
    client: BrewfatherClient,
    path: str,
    ids: list[str],
    *,
    max_workers: int,
    on_fetched: Callable[[], None],
) -> list[dict[str, Any]]:
    """Fetch each record by id concurrently, returning results in ``ids`` order.

    ``on_fetched`` is invoked once per completed record from the calling thread
    (not the worker threads), so reporters need not be thread-safe.
    """
    results: list[dict[str, Any] | None] = [None] * len(ids)
    if not ids:
        return []
    workers = min(max_workers, len(ids))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_to_index = {
            pool.submit(client.get, path, record_id): i for i, record_id in enumerate(ids)
        }
        for future in as_completed(future_to_index):
            results[future_to_index[future]] = future.result()
            on_fetched()
    return [record for record in results if record is not None]


def run_backup(
    settings: Settings,
    *,
    client: BrewfatherClient | None = None,
    only: Iterable[str] | None = None,
    now: datetime | None = None,
    reporter: ProgressReporter | None = None,
) -> BackupSummary:
    """Fetch the selected resources in full and write a snapshot to disk.

    ``only`` restricts the run to a subset of :data:`GROUPS`; by default every
    group is backed up. ``reporter`` receives per-resource and per-record events
    so callers can show live progress.
    """
    selected = set(only) if only is not None else set(GROUPS)
    reporter = reporter or NullReporter()
    timestamp = (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H-%M-%SZ")
    snapshot = settings.output_dir / timestamp

    owned_client = client is None
    client = client or BrewfatherClient(settings)
    # Write into a sibling staging directory and atomically rename on success, so
    # a mid-run failure never leaves a partial, manifest-less snapshot behind.
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(dir=settings.output_dir, prefix=f".{timestamp}.partial-"))
    counts: dict[str, int] = {}
    try:
        for label, path, dest in _selected_resources(selected):
            reporter.resource_started(label)
            ids = [summary["_id"] for summary in client.paginate(path)]
            records = _fetch_full(
                client,
                path,
                ids,
                max_workers=settings.concurrency,
                on_fetched=partial(reporter.record_fetched, label),
            )
            _write_json(staging.joinpath(*dest), records)
            counts[label] = len(records)
            reporter.resource_finished(label, len(records))

        manifest = {
            "tool": "brewfather-backup",
            "version": __version__,
            "base_url": str(settings.base_url),
            "timestamp": timestamp,
            "counts": counts,
        }
        _write_json(staging / "manifest.json", manifest)
        staging.replace(snapshot)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        if owned_client:
            client.close()

    return BackupSummary(path=snapshot, timestamp=timestamp, counts=counts)
