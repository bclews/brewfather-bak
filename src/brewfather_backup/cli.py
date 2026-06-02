"""Command-line interface for the Brewfather backup tool."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn
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
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        summary = run_backup(settings, only=selected, reporter=_RichReporter(progress))
    _print_summary(summary, verbose=verbose)


class _RichReporter:
    """Renders backup progress as a live spinner + running count per resource."""

    def __init__(self, progress: Progress) -> None:
        self._progress = progress
        self._tasks: dict[str, TaskID] = {}
        self._counts: dict[str, int] = {}

    def resource_started(self, label: str) -> None:
        self._counts[label] = 0
        self._tasks[label] = self._progress.add_task(f"Fetching {label}…", total=None)

    def record_fetched(self, label: str) -> None:
        self._counts[label] += 1
        self._progress.update(
            self._tasks[label],
            description=f"Fetching {label}… ({self._counts[label]})",
            advance=1,
        )

    def resource_finished(self, label: str, count: int) -> None:
        task = self._tasks[label]
        self._progress.update(
            task,
            description=f"[green]✓[/green] {label} ({count})",
            total=count,
            completed=count,
        )
        self._progress.stop_task(task)


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
