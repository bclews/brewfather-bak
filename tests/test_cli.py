from pathlib import Path

import pytest
from typer.testing import CliRunner

from brewfather_backup import cli
from brewfather_backup.backup import BackupSummary, NullReporter

runner = CliRunner()


def _stub_run_backup(monkeypatch: pytest.MonkeyPatch, captured: dict[str, object]) -> None:
    def fake_run_backup(settings, *, only=None, reporter=None, **kwargs):  # type: ignore[no-untyped-def]
        captured["only"] = only
        captured["reporter"] = reporter
        captured["concurrency"] = settings.concurrency
        captured["output_dir"] = settings.output_dir
        return BackupSummary(path=Path("snap"), timestamp="t", counts={"recipes": 2})

    monkeypatch.setattr(cli, "run_backup", fake_run_backup)


def test_cli_invokes_run_backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # isolate from any real .env in the project root
    monkeypatch.setenv("BREWFATHER_USER_ID", "u")
    monkeypatch.setenv("BREWFATHER_API_KEY", "k")

    captured: dict[str, object] = {}
    _stub_run_backup(monkeypatch, captured)

    result = runner.invoke(cli.app, ["--only", "recipes", "--verbose", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert captured["only"] == {"recipes"}
    assert captured["output_dir"] == tmp_path
    assert "Backup complete" in result.stdout
    assert "recipes" in result.stdout  # verbose table lists the resource


def test_cli_quiet_uses_null_reporter(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BREWFATHER_USER_ID", "u")
    monkeypatch.setenv("BREWFATHER_API_KEY", "k")

    captured: dict[str, object] = {}
    _stub_run_backup(monkeypatch, captured)

    result = runner.invoke(cli.app, ["--quiet"])

    assert result.exit_code == 0, result.output
    assert isinstance(captured["reporter"], NullReporter)
    assert "Fetching" not in result.output  # no live progress spinner


def test_cli_workers_overrides_concurrency(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BREWFATHER_USER_ID", "u")
    monkeypatch.setenv("BREWFATHER_API_KEY", "k")

    captured: dict[str, object] = {}
    _stub_run_backup(monkeypatch, captured)

    result = runner.invoke(cli.app, ["--workers", "3"])

    assert result.exit_code == 0, result.output
    assert captured["concurrency"] == 3


def test_cli_quiet_and_verbose_conflict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BREWFATHER_USER_ID", "u")
    monkeypatch.setenv("BREWFATHER_API_KEY", "k")
    monkeypatch.setattr(cli, "run_backup", lambda *a, **k: None)

    result = runner.invoke(cli.app, ["--quiet", "--verbose"])

    assert result.exit_code != 0


def test_cli_reports_config_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)  # no .env here, so missing creds surface
    monkeypatch.delenv("BREWFATHER_USER_ID", raising=False)
    monkeypatch.delenv("BREWFATHER_API_KEY", raising=False)

    result = runner.invoke(cli.app, [])

    assert result.exit_code != 0
    assert "user_id" in result.output or "api_key" in result.output
