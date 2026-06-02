"""Command-line interface for the Brewfather backup tool."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from .backup import GROUPS, BackupSummary, run_backup
from .config import Settings

app = typer.Typer(
    add_completion=False,
    help="Back up Brewfather recipes, batches, and inventory to timestamped JSON snapshots.",
)
console = Console()


@app.command()
def run(
    out: Annotated[
        Path | None,
        typer.Option("--out", help="Output directory (overrides BREWFATHER_OUTPUT_DIR)."),
    ] = None,
    only: Annotated[
        list[str] | None,
        typer.Option("--only", help=f"Limit to groups: {', '.join(GROUPS)}. Repeatable."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Print the snapshot path and per-resource counts."),
    ] = False,
) -> None:
    """Run a backup."""
    try:
        settings = Settings()
    except ValidationError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if out is not None:
        settings = settings.model_copy(update={"output_dir": out})

    selected = _validate_groups(only)
    summary = run_backup(settings, only=selected)
    _print_summary(summary, verbose=verbose)


def _validate_groups(only: list[str] | None) -> set[str] | None:
    if not only:
        return None
    unknown = sorted(set(only) - set(GROUPS))
    if unknown:
        console.print(
            f"[red]Unknown group(s):[/red] {', '.join(unknown)}. "
            f"Choose from: {', '.join(GROUPS)}."
        )
        raise typer.Exit(code=2)
    return set(only)


def _print_summary(summary: BackupSummary, *, verbose: bool) -> None:
    total = sum(summary.counts.values())
    console.print(f"[green]Backup complete[/green] -> {summary.path} ({total} records)")
    if verbose:
        table = Table("Resource", "Records")
        for resource, count in summary.counts.items():
            table.add_row(resource, str(count))
        console.print(table)


if __name__ == "__main__":  # pragma: no cover
    app()
