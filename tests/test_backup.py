import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from brewfather_backup.backup import INVENTORY_TYPES, run_backup
from brewfather_backup.config import Settings

BASE = "https://api.brewfather.app/v2"


def _mock_collection(name: str, path: str) -> None:
    """Mock a list endpoint (one summary) plus its full-detail record."""
    respx.get(f"{BASE}{path}").mock(
        return_value=httpx.Response(200, json=[{"_id": f"{name}-1"}])
    )
    respx.get(f"{BASE}{path}/{name}-1").mock(
        return_value=httpx.Response(200, json={"_id": f"{name}-1", "name": name, "complete": True})
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        user_id="u",
        api_key="k",
        base_url=BASE,
        output_dir=tmp_path,
        _env_file=None,  # type: ignore[call-arg]
    )


@respx.mock
def test_run_backup_writes_snapshot(tmp_path: Path) -> None:
    _mock_collection("recipes", "/recipes")
    _mock_collection("batches", "/batches")
    for inv in INVENTORY_TYPES:
        _mock_collection(inv, f"/inventory/{inv}")

    now = datetime(2026, 6, 2, 14, 30, 0, tzinfo=UTC)
    summary = run_backup(_settings(tmp_path), now=now)

    snapshot = tmp_path / "2026-06-02T14-30-00Z"
    assert summary.path == snapshot
    assert snapshot.is_dir()

    recipes = json.loads((snapshot / "recipes.json").read_text())
    assert recipes == [{"_id": "recipes-1", "name": "recipes", "complete": True}]

    fermentables = json.loads((snapshot / "inventory" / "fermentables.json").read_text())
    assert fermentables[0]["_id"] == "fermentables-1"

    manifest = json.loads((snapshot / "manifest.json").read_text())
    assert manifest["base_url"] == BASE
    assert manifest["counts"]["recipes"] == 1
    assert manifest["counts"]["inventory.hops"] == 1
    assert "version" in manifest


class _RecordingReporter:
    def __init__(self) -> None:
        self.events: list[tuple] = []

    def resource_started(self, label: str) -> None:
        self.events.append(("start", label))

    def record_fetched(self, label: str) -> None:
        self.events.append(("record", label))

    def resource_finished(self, label: str, count: int) -> None:
        self.events.append(("finish", label, count))


@respx.mock
def test_run_backup_reports_progress(tmp_path: Path) -> None:
    _mock_collection("recipes", "/recipes")
    reporter = _RecordingReporter()

    run_backup(_settings(tmp_path), only={"recipes"}, reporter=reporter)

    assert reporter.events == [
        ("start", "recipes"),
        ("record", "recipes"),
        ("finish", "recipes", 1),
    ]


@respx.mock
def test_run_backup_only_subset(tmp_path: Path) -> None:
    _mock_collection("recipes", "/recipes")

    now = datetime(2026, 6, 2, 14, 30, 0, tzinfo=UTC)
    summary = run_backup(_settings(tmp_path), now=now, only={"recipes"})

    snapshot = summary.path
    assert (snapshot / "recipes.json").exists()
    assert not (snapshot / "batches.json").exists()
    assert not (snapshot / "inventory").exists()
    assert summary.counts == {"recipes": 1}
