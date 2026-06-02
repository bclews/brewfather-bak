"""Command-line interface for the Brewfather backup tool."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import httpx
import typer
from pydantic import ValidationError
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TaskID, TextColumn, TimeElapsedColumn
from rich.table import Table

from .backup import BackupSummary, Group, NullReporter, run_backup
from .client import BrewfatherError
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
        list[Group] | None,
        typer.Option("--only", help="Limit to one or more resource groups. Repeatable."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Print the snapshot path and per-resource counts."),
    ] = False,
    quiet: Annotated[
        bool,
        typer.Option("--quiet", "-q", help="Suppress the live progress spinner."),
    ] = False,
    workers: Annotated[
        int | None,
        typer.Option("--workers", min=1, help="Concurrent record fetches (overrides config)."),
    ] = None,
) -> None:
    """Run a backup."""
    if quiet and verbose:
        console.print("[red]--quiet and --verbose cannot be used together.[/red]")
        raise typer.Exit(code=2)

    try:
        settings = Settings()
    except ValidationError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    overrides: dict[str, object] = {}
    if out is not None:
        overrides["output_dir"] = out
    if workers is not None:
        overrides["concurrency"] = workers
    if overrides:
        # Re-validate rather than model_copy(update=...) so field constraints
        # (e.g. concurrency >= 1) still apply to the overridden values.
        settings = Settings.model_validate({**settings.model_dump(), **overrides})

    selected = {group.value for group in only} if only else None
    try:
        if quiet:
            summary = run_backup(settings, only=selected, reporter=NullReporter())
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                TimeElapsedColumn(),
                console=console,
                transient=False,
            ) as progress:
                summary = run_backup(settings, only=selected, reporter=_RichReporter(progress))
    except (BrewfatherError, httpx.HTTPError) as exc:
        console.print(f"[red]Backup failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
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
