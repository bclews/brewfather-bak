from pathlib import Path

import pytest
from typer.testing import CliRunner

from brewfather_backup import cli
from brewfather_backup.backup import BackupSummary

runner = CliRunner()


def test_cli_invokes_run_backup(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BREWFATHER_USER_ID", "u")
    monkeypatch.setenv("BREWFATHER_API_KEY", "k")

    captured: dict[str, object] = {}

    def fake_run_backup(settings, *, only=None, **kwargs):  # type: ignore[no-untyped-def]
        captured["only"] = only
        captured["output_dir"] = settings.output_dir
        return BackupSummary(path=tmp_path / "snap", timestamp="t", counts={"recipes": 2})

    monkeypatch.setattr(cli, "run_backup", fake_run_backup)

    result = runner.invoke(cli.app, ["--only", "recipes", "--verbose", "--out", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert captured["only"] == {"recipes"}
    assert captured["output_dir"] == tmp_path
    assert "Backup complete" in result.stdout
    assert "recipes" in result.stdout  # verbose table lists the resource


def test_cli_reports_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BREWFATHER_USER_ID", raising=False)
    monkeypatch.delenv("BREWFATHER_API_KEY", raising=False)

    result = runner.invoke(cli.app, [])

    assert result.exit_code != 0
    assert "user_id" in result.output or "api_key" in result.output
