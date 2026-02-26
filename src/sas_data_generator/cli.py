"""CLI interface for sas-data-generator.

Usage:
    sas-datagen analyze  program.sas           # Parse and show coverage points
    sas-datagen generate program.sas -o out/   # Generate test datasets
    sas-datagen run      program.sas -o out/   # Full loop: generate + run SAS + report
    sas-datagen instrument program.sas         # Show instrumented code (debug)
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from . import __version__

app = typer.Typer(
    name="sas-datagen",
    help="Generate test datasets to maximize SAS code coverage.",
    add_completion=False,
)
console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-V", help="Show version"),
) -> None:
    if version:
        console.print(f"sas-data-generator {__version__}")
        raise typer.Exit()


@app.command()
def analyze(
    sas_files: list[Path] = typer.Argument(..., help="SAS program files to analyze"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Parse SAS files and display coverage points and variables."""
    _setup_logging(verbose)
    from .sas_parser import parse_sas_file

    for sas_file in sas_files:
        if not sas_file.exists():
            console.print(f"[red]File not found: {sas_file}[/red]")
            continue

        result = parse_sas_file(sas_file)

        console.print(f"\n[bold]File: {sas_file}[/bold]")
        console.print(f"  Blocks: {len(result.blocks)}")
        console.print(f"  Coverage points: {len(result.all_coverage_points)}")
        console.print(f"  Variables: {len(result.all_variables)}")

        if result.errors:
            console.print(f"  [yellow]Warnings: {len(result.errors)}[/yellow]")
            for err in result.errors:
                console.print(f"    {err}")

        # Coverage points table
        if result.all_coverage_points:
            table = Table(title="Coverage Points")
            table.add_column("ID", style="cyan")
            table.add_column("Type", style="green")
            table.add_column("Line")
            table.add_column("Description")
            table.add_column("Condition", max_width=50)

            for cp in result.all_coverage_points:
                table.add_row(
                    cp.point_id,
                    cp.point_type.name,
                    str(cp.line_number),
                    cp.description,
                    cp.condition[:50] if cp.condition else "",
                )
            console.print(table)

        # Variables table
        if result.all_variables:
            vtable = Table(title="Detected Variables")
            vtable.add_column("Name", style="cyan")
            vtable.add_column("Type", style="green")
            vtable.add_column("Source")
            vtable.add_column("Line")
            vtable.add_column("Format")

            for v in result.all_variables:
                vtable.add_row(v.name, v.inferred_type, v.source, str(v.line_number), v.format)
            console.print(vtable)


@app.command()
def instrument(
    sas_file: Path = typer.Argument(..., help="SAS program to instrument"),
    output: Path = typer.Option(None, "--output", "-o", help="Output file (stdout if omitted)"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Instrument a SAS file and show/write the result."""
    _setup_logging(verbose)
    from .sas_instrumenter import instrument_sas_file

    if not sas_file.exists():
        console.print(f"[red]File not found: {sas_file}[/red]")
        raise typer.Exit(1)

    result = instrument_sas_file(sas_file)

    if output:
        output.write_text(result.instrumented_code, encoding="utf-8")
        console.print(f"Instrumented code written to: {output}")
    else:
        console.print(result.instrumented_code)

    console.print(f"\n[bold]Coverage points: {len(result.coverage_points)}[/bold]")


@app.command()
def generate(
    sas_files: list[Path] = typer.Argument(..., help="SAS program files"),
    output_dir: Path = typer.Option("./output", "--output", "-o", help="Output directory"),
    num_rows: int = typer.Option(20, "--rows", "-n", help="Number of rows per dataset"),
    seed: int = typer.Option(42, "--seed", "-s", help="Random seed for reproducibility"),
    formats: list[str] = typer.Option(["csv"], "--format", "-f", help="Output formats"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate test datasets from SAS program analysis (no SAS execution)."""
    _setup_logging(verbose)
    from .sas_parser import parse_sas_file
    from .dataset_generator import generate_seed_datasets, export_dataset

    output_dir.mkdir(parents=True, exist_ok=True)

    for sas_file in sas_files:
        if not sas_file.exists():
            console.print(f"[red]File not found: {sas_file}[/red]")
            continue

        parse_result = parse_sas_file(sas_file)
        datasets = generate_seed_datasets(parse_result, num_rows=num_rows, seed=seed)

        for ds in datasets:
            paths = export_dataset(ds, output_dir, formats=formats)
            console.print(f"  Generated: {ds.name} -> {paths}")
            for note in ds.generation_notes:
                console.print(f"    {note}")


@app.command()
def run(
    sas_files: list[Path] = typer.Argument(..., help="SAS program files"),
    output_dir: Path = typer.Option("./output", "--output", "-o", help="Output directory"),
    num_rows: int = typer.Option(20, "--rows", "-n", help="Number of rows per seed dataset"),
    seed: int = typer.Option(42, "--seed", "-s", help="Random seed"),
    max_iterations: int = typer.Option(5, "--max-iter", "-i", help="Max mutation iterations"),
    coverage_target: float = typer.Option(100.0, "--target", "-t", help="Target coverage %%"),
    sas_executable: str = typer.Option(None, "--sas", help="Path to SAS executable"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip SAS execution"),
    timeout: int = typer.Option(300, "--timeout", help="SAS execution timeout (seconds)"),
    formats: list[str] = typer.Option(["csv"], "--format", "-f", help="Output formats"),
    macro_vars_json: str = typer.Option(None, "--macros", help="JSON file with macro variables"),
    libname_json: str = typer.Option(None, "--libnames", help="JSON file with libname mappings"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Full loop: generate datasets, run SAS, measure coverage, mutate, repeat."""
    _setup_logging(verbose)
    from .sas_parser import parse_sas_file
    from .sas_instrumenter import instrument_sas_file
    from .sas_runner import run_sas, run_sas_dry
    from .dataset_generator import (
        generate_seed_datasets,
        mutate_datasets,
        export_dataset,
    )
    from .coverage import (
        parse_coverage_from_log,
        merge_coverage_reports,
        export_coverage_report,
        CoverageReport,
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load optional config
    macro_vars = None
    if macro_vars_json:
        macro_vars = json.loads(Path(macro_vars_json).read_text())

    libname_map = None
    if libname_json:
        libname_map = json.loads(Path(libname_json).read_text())

    all_reports: list[CoverageReport] = []

    for sas_file in sas_files:
        if not sas_file.exists():
            console.print(f"[red]File not found: {sas_file}[/red]")
            continue

        console.print(f"\n[bold]=== Processing: {sas_file} ===[/bold]")

        # Phase 1: Parse
        parse_result = parse_sas_file(sas_file)
        console.print(f"  Parsed: {len(parse_result.blocks)} blocks, "
                      f"{len(parse_result.all_coverage_points)} coverage points")

        if not parse_result.all_coverage_points:
            console.print("  [yellow]No coverage points found — skipping[/yellow]")
            continue

        # Phase 2: Instrument
        coverage_csv = str(output_dir / f"{sas_file.stem}_coverage.csv")
        instr_result = instrument_sas_file(sas_file, coverage_csv_path=coverage_csv)

        # Save instrumented code for debugging
        instr_path = output_dir / f"{sas_file.stem}_instrumented.sas"
        instr_path.write_text(instr_result.instrumented_code, encoding="utf-8")
        console.print(f"  Instrumented code: {instr_path}")

        # Phase 3: Generate seed datasets
        datasets = generate_seed_datasets(parse_result, num_rows=num_rows, seed=seed)

        # Phase 4: Iterate
        file_reports: list[CoverageReport] = []

        for iteration in range(max_iterations):
            console.print(f"\n  [cyan]--- Iteration {iteration + 1}/{max_iterations} ---[/cyan]")

            # Export datasets
            iter_dir = output_dir / f"iter_{iteration}"
            for ds in datasets:
                export_dataset(ds, iter_dir, formats=formats)

            # Build SAS code with data loading preamble
            data_load_code = _build_data_load_sas(datasets, iter_dir, libname_map)
            full_sas_code = data_load_code + "\n" + instr_result.instrumented_code

            # Run SAS
            if dry_run:
                sas_result = run_sas_dry(full_sas_code, work_dir=str(iter_dir))
                console.print("  [yellow]Dry run — no SAS execution[/yellow]")
            else:
                sas_result = run_sas(
                    full_sas_code,
                    work_dir=str(iter_dir),
                    sas_executable=sas_executable,
                    timeout_seconds=timeout,
                    macro_vars=macro_vars,
                    libname_map=libname_map,
                )

            if sas_result.sas_errors:
                console.print(f"  [red]SAS errors: {len(sas_result.sas_errors)}[/red]")
                for err in sas_result.sas_errors[:3]:
                    console.print(f"    {err}")

            # Parse coverage
            report = parse_coverage_from_log(
                sas_result.log_text,
                instr_result.coverage_points,
            )
            file_reports.append(report)

            merged = merge_coverage_reports(*file_reports)
            console.print(f"  Coverage: {merged.hit_points}/{merged.total_points} "
                          f"({merged.coverage_pct:.1f}%)")

            # Check if target reached
            if merged.coverage_pct >= coverage_target:
                console.print(f"  [green]Target coverage reached![/green]")
                break

            # Mutate datasets for next iteration
            datasets = mutate_datasets(
                datasets,
                merged,
                parse_result,
                seed=seed + iteration + 1,
            )

        # Export final datasets
        final_dir = output_dir / "final"
        for ds in datasets:
            export_dataset(ds, final_dir, formats=formats)

        # Export coverage report
        final_report = merge_coverage_reports(*file_reports)
        all_reports.append(final_report)

        report_path = output_dir / f"{sas_file.stem}_coverage_report.json"
        export_coverage_report(final_report, report_path, format="json")

        text_report_path = output_dir / f"{sas_file.stem}_coverage_report.txt"
        export_coverage_report(final_report, text_report_path, format="text")

        console.print(f"\n  [bold]Final coverage: {final_report.coverage_pct:.1f}%[/bold]")
        console.print(f"  Report: {report_path}")

    # Overall summary
    if all_reports:
        overall = merge_coverage_reports(*all_reports)
        console.print(f"\n[bold]=== Overall Coverage: {overall.coverage_pct:.1f}% ===[/bold]")

        if overall.missed_point_ids:
            console.print(f"  Missed points ({len(overall.missed_point_ids)}):")
            for cp in overall.missed_points:
                console.print(f"    [{cp.point_id}] {cp.description}")

        # Exit with non-zero if coverage is below target
        if overall.coverage_pct < coverage_target:
            raise typer.Exit(1)


def _build_data_load_sas(
    datasets: list,
    data_dir: Path,
    libname_map: dict[str, str] | None = None,
) -> str:
    """Build SAS code that loads generated CSV datasets into WORK library."""
    import re as _re

    lines = [
        "/* Auto-generated data loading */",
    ]

    for ds in datasets:
        clean_name = _re.sub(r"[^\w]", "_", ds.name)
        # Remove library prefix for WORK datasets
        sas_name = clean_name.split("_", 1)[-1] if "." in ds.name else clean_name
        csv_path = data_dir / f"{clean_name}.csv"

        if csv_path.exists() or True:  # Will exist at runtime
            lines.append(f'proc import datafile="{csv_path}"')
            lines.append(f"  out={sas_name} dbms=csv replace;")
            lines.append("  getnames=yes;")
            lines.append("run;")
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    app()
