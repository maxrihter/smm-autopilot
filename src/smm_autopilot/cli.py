"""Command-line interface for SMM-Autopilot."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from . import __version__

app = typer.Typer(
    add_completion=False,
    help="Your AI SMM team for any niche & region.",
)
console = Console()


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"smm-autopilot {__version__}")


@app.command()
def init(
    directory: Annotated[
        Path, typer.Option("--dir", "-d", help="Where to write the starter config.")
    ] = Path("config"),
) -> None:
    """Scaffold a starter tenant config from the bundled example."""
    from .templates import example_tenant_yaml

    target = directory / "tenant.yaml"
    if target.exists():
        console.print(f"[yellow]{target} already exists[/yellow] — not overwriting.")
        return
    try:
        directory.mkdir(parents=True, exist_ok=True)
        target.write_text(example_tenant_yaml(), encoding="utf-8")
    except OSError as exc:
        console.print(f"[red]Could not write {target}:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(
        f"[green]Wrote[/green] {target}. Edit it for your brand, then `smm-autopilot run`."
    )


@app.command()
def run(
    config: Annotated[
        Path, typer.Option("--config", "-c", help="Path to your tenant config.")
    ] = Path("config/tenant.yaml"),
) -> None:
    """Run the pipeline for a configured tenant (live — needs API keys)."""
    try:
        asyncio.run(_run(config))
    except FileNotFoundError as exc:
        console.print(
            f"[red]Config not found:[/red] {config} — run `smm-autopilot init` or pass --config."
        )
        raise typer.Exit(1) from exc
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1) from exc


async def _run(config: Path) -> None:
    from .config import load_settings
    from .engine.pipeline import run_pipeline
    from .engine.scrape import collect_datasets
    from .log import configure_logging

    configure_logging()
    settings = load_settings(config)
    console.print(
        f"[bold]Running[/bold] {settings.brand.name} ({settings.brand.region or 'global'})…"
    )
    dataset_ids, source_map = await collect_datasets(settings)
    report = await run_pipeline(settings, dataset_ids=dataset_ids, source_map=source_map)
    if report is None:
        console.print(
            "[yellow]No report produced — the run aborted (likely no relevant posts).[/yellow]"
        )
        return
    console.print(
        f"[green]Done.[/green] {len(report.trends)} trends, {len(report.briefs)} briefs "
        f"→ output/{report.run_id}.md"
    )


@app.command()
def demo() -> None:
    """Run the pipeline on bundled fixtures — no API keys needed."""
    from .engine.demo import run_demo
    from .log import configure_logging

    configure_logging()
    console.print("[bold]Running demo[/bold] on bundled fixtures (no API keys)…")
    report = asyncio.run(run_demo())
    if report is None:
        console.print("[red]Demo produced no report.[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]Demo done.[/green] {len(report.trends)} trends, {len(report.briefs)} briefs "
        f"→ output/{report.run_id}.md"
    )


if __name__ == "__main__":
    app()
