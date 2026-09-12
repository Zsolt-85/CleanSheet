"""CLI entry point for CleanSheet cleaning engine."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from cleaning_engine import (
    __version__,
    analyze_spreadsheet,
    create_aggressive_pipeline,
    create_conservative_pipeline,
    create_default_pipeline,
    export_both,
    load_spreadsheet,
    profile_spreadsheet,
)

app = typer.Typer(
    name="cleansheet",
    help="CleanSheet - Automated spreadsheet cleaning engine",
    add_completion=False,
)
console = Console()


@app.command()
def clean(
    input_file: Annotated[
        Path, typer.Argument(help="Input spreadsheet file (CSV/XLSX)", exists=True, readable=True)
    ],
    output: Annotated[
        Path | None, typer.Option("--output", "-o", help="Output cleaned file path")
    ] = None,
    report: Annotated[
        Path | None, typer.Option("--report", "-r", help="Output change report file path")
    ] = None,
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            "-m",
            help="Cleaning mode: conservative (sure fixes only), default (recommended), "
            "aggressive (also assumes ambiguous dates are MM/DD). See 'cleansheet modes'.",
        ),
    ] = "default",
    email_column: Annotated[
        str | None,
        typer.Option(
            "--email-column", "-e", help="Email column name (auto-detect if not specified)"
        ),
    ] = None,
    no_duplicate_rows: Annotated[
        bool, typer.Option("--no-duplicate-rows", help="Disable duplicate row removal")
    ] = False,
    no_duplicate_emails: Annotated[
        bool, typer.Option("--no-duplicate-emails", help="Disable duplicate email removal")
    ] = False,
    no_whitespace: Annotated[
        bool, typer.Option("--no-whitespace", help="Disable whitespace normalization")
    ] = False,
    no_capitalization: Annotated[
        bool, typer.Option("--no-capitalization", help="Disable capitalization normalization")
    ] = False,
    no_dates: Annotated[
        bool, typer.Option("--no-dates", help="Disable date normalization")
    ] = False,
    no_emails: Annotated[
        bool, typer.Option("--no-emails", help="Disable email validation")
    ] = False,
    no_empty_rows: Annotated[
        bool, typer.Option("--no-empty-rows", help="Disable empty row removal")
    ] = False,
    capitalization_mode: Annotated[
        str, typer.Option("--cap-mode", help="Capitalization mode: title, lower, upper")
    ] = "title",
    safe_dates_only: Annotated[
        bool,
        typer.Option("--safe-dates-only/--unsafe-dates", help="Only normalize unambiguous dates"),
    ] = True,
    fix_email_typos: Annotated[
        bool,
        typer.Option("--fix-email-typos/--no-fix-email-typos", help="Auto-fix common email typos"),
    ] = True,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
) -> None:
    """
    Clean a spreadsheet file.

    Examples:
        cleansheet clean messy_data.csv -o clean.xlsx -r report.xlsx
        cleansheet clean leads.xlsx --mode conservative
        cleansheet clean data.csv --email-column "Email Address"
    """
    console.print(f"[bold blue]CleanSheet[/bold blue] - Cleaning [cyan]{input_file.name}[/cyan]")

    # Determine output paths
    if output is None:
        output = input_file.with_stem(f"{input_file.stem}_cleaned").with_suffix(".xlsx")
    if report is None:
        report = input_file.with_stem(f"{input_file.stem}_report").with_suffix(".xlsx")

    # Load spreadsheet
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Loading spreadsheet...", total=None)
        try:
            data = load_spreadsheet(input_file)
        except Exception as e:
            console.print(f"[red]Error loading file:[/red] {e}")
            raise typer.Exit(1)
        progress.update(task, description="Spreadsheet loaded", completed=True)

    console.print(
        f"  Rows: [green]{data.dataframe.shape[0]}[/green], Columns: [green]{data.dataframe.shape[1]}[/green]"
    )

    # Create pipeline based on mode
    if mode == "conservative":
        pipeline = create_conservative_pipeline()
    elif mode == "aggressive":
        pipeline = create_aggressive_pipeline()
    else:
        pipeline = create_default_pipeline()

    # Override config with CLI flags
    cfg = pipeline.config
    if email_column:
        cfg.email_column = email_column
    if no_duplicate_rows:
        cfg.remove_duplicate_rows = False
    if no_duplicate_emails:
        cfg.remove_duplicate_emails = False
    if no_whitespace:
        cfg.normalize_whitespace = False
    if no_capitalization:
        cfg.normalize_capitalization = False
    if no_dates:
        cfg.normalize_dates = False
    if no_emails:
        cfg.validate_emails = False
    if no_empty_rows:
        cfg.remove_empty_rows = False
    cfg.capitalization_mode = capitalization_mode
    cfg.dates_only_safe = safe_dates_only
    cfg.auto_fix_email_typos = fix_email_typos

    # Run pipeline
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Running cleaning pipeline...", total=None)
        cleaned_data, tracker = pipeline.run(data)
        progress.update(task, description="Cleaning complete", completed=True)

    # Export results
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Exporting results...", total=None)
        export_both(cleaned_data, tracker, output, report)
        progress.update(task, description="Export complete", completed=True)

    # Print summary (plain ASCII: Windows cp1252 consoles can't encode U+2713)
    console.print("\n[bold green]Cleaning complete![/bold green]")
    console.print(f"  Cleaned file: [cyan]{output}[/cyan]")
    console.print(f"  Change report: [cyan]{report}[/cyan]")
    console.print(
        f"  Rows: [green]{cleaned_data.dataframe.shape[0]}[/green] (was {data.dataframe.shape[0]})"
    )

    # Show change summary
    report_obj = tracker.to_report()
    table = Table(title="Changes Applied", show_header=True, header_style="bold")
    table.add_column("Rule", style="cyan")
    table.add_column("Count", justify="right", style="green")
    for rule, count in sorted(report_obj.summary.items(), key=lambda x: -x[1]):
        table.add_row(rule, str(count))
    console.print(table)

    if verbose:
        console.print("\n[bold]Full change log:[/bold]")
        changes_df = tracker.to_dataframe()
        if len(changes_df) > 0:
            console.print(changes_df.to_string(index=False))
        else:
            console.print("  No changes made.")


@app.command()
def analyze(
    input_file: Annotated[
        Path, typer.Argument(help="Input spreadsheet file (CSV/XLSX)", exists=True, readable=True)
    ],
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
) -> None:
    """
    Analyze a spreadsheet for data quality issues without cleaning.
    """
    console.print(f"[bold blue]CleanSheet[/bold blue] - Analyzing [cyan]{input_file.name}[/cyan]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Loading spreadsheet...", total=None)
        try:
            data = load_spreadsheet(input_file)
        except Exception as e:
            console.print(f"[red]Error loading file:[/red] {e}")
            raise typer.Exit(1)
        progress.update(task, description="Profiling...", total=None)
        profile = profile_spreadsheet(data)
        progress.update(task, description="Analyzing...", total=None)
        analysis = analyze_spreadsheet(data, profile)
        progress.update(task, description="Analysis complete", completed=True)

    # Print profile summary (plain ASCII: safe on all Windows consoles)
    console.print("\n[bold]Spreadsheet Profile[/bold]")
    console.print(f"  File: {profile.filename}")
    console.print(f"  Shape: {profile.shape[0]} rows x {profile.shape[1]} columns")
    console.print(f"  Empty rows: {profile.empty_rows}")
    console.print(f"  Duplicate rows: {profile.duplicate_rows}")
    console.print(f"  Empty cells: {profile.empty_cells} / {profile.total_cells}")

    # Column profiles
    table = Table(title="Columns", show_header=True, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="magenta")
    table.add_column("Nulls", justify="right")
    table.add_column("Unique", justify="right")
    table.add_column("Sample Values")

    for i, col in enumerate(profile.columns):
        sample_str = ", ".join(str(v) for v in col.sample_values[:3])
        table.add_row(
            str(i + 1),
            col.name,
            col.inferred_type.value,
            str(col.null_count),
            str(col.unique_count),
            sample_str,
        )

    console.print(table)

    # Issues found
    if analysis.issues:
        console.print("\n[bold yellow]Issues Detected[/bold yellow]")
        for issue_type, items in analysis.issues.items():
            console.print(f"  {issue_type}: [red]{len(items)}[/red]")
            if verbose and items:
                for item in items[:5]:
                    console.print(f"    Row {item.get('row', '?')}: {item.get('issue', 'unknown')}")
                if len(items) > 5:
                    console.print(f"    ... and {len(items) - 5} more")

    # Suggested operations
    if analysis.suggested_operations:
        console.print("\n[bold]Suggested Cleaning Operations[/bold]")
        for op in analysis.suggested_operations:
            console.print(f"  - {op}")


@app.command()
def modes() -> None:
    """Show what each cleaning mode does and how they differ."""
    from cleaning_engine.modes import MODE_COMPARISON, MODES

    for mode_id, info in MODES.items():
        console.print(f"\n[bold cyan]{info['name']}[/bold cyan] [dim](--mode {mode_id})[/dim]")
        console.print(f"  {info['tagline']}")
        for line in info["details"]:
            console.print(f"  - {line}")
        if "warning" in info:
            console.print(f"  [bold yellow]Warning:[/bold yellow] {info['warning']}")

    table = Table(title="\nMode comparison", show_header=True, header_style="bold")
    table.add_column("Operation")
    for mode_id in MODES:
        table.add_column(MODES[mode_id]["name"])
    for row in MODE_COMPARISON:
        table.add_row(row["operation"], *[row[mode_id] for mode_id in MODES])
    console.print(table)
    console.print(
        "\n[dim]Always true, every mode: every applied change is logged with reason and "
        "confidence; invalid values are kept and flagged; removed rows are logged and "
        "recoverable from the report.[/dim]"
    )


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"CleanSheet v{__version__}")


if __name__ == "__main__":
    app()
