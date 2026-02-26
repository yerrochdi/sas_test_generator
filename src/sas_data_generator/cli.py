"""CLI interface for sas-data-generator.

Usage:
    # Single file
    sas-datagen analyze  program.sas
    sas-datagen generate program.sas -o out/
    sas-datagen run      program.sas -o out/
    sas-datagen instrument program.sas

    # Multi-file project with %INCLUDE resolution
    sas-datagen analyze  --project-dir /projets/sas/projet_A/ --entry main.sas
    sas-datagen generate --project-dir /projets/sas/projet_A/ --entry main.sas -o out/
    sas-datagen run      --project-dir /projets/sas/projet_A/ --entry main.sas -o out/

    # With extra include search paths
    sas-datagen run main.sas --include-path ./macros --include-path ./includes
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

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


def _resolve_sas_files(
    sas_files: list[Path] | None,
    project_dir: str | None,
    entry_file: str | None,
    include_paths: list[str] | None,
    macro_vars: dict[str, str] | None = None,
) -> tuple[list[Path], bool]:
    """Resolve which SAS files to process.

    Returns:
        (list_of_files, use_project_mode)
        - If project_dir is set: returns files from project scanning
        - Otherwise: returns the explicit file list
    """
    if project_dir:
        from .include_resolver import scan_project_directory
        files = scan_project_directory(project_dir, entry_file=entry_file)
        if not files:
            console.print(f"[red]No .sas files found in {project_dir}[/red]")
        return files, True
    elif sas_files:
        return sas_files, False
    else:
        console.print("[red]Provide SAS files or --project-dir[/red]")
        return [], False


def _parse_file_or_project(
    sas_file: Path,
    include_paths: list[str] | None,
    macro_vars: dict[str, str] | None,
    use_project_mode: bool,
):
    """Parse a SAS file, with or without include resolution."""
    from .sas_parser import parse_sas_file, parse_sas_project

    if use_project_mode or include_paths:
        return parse_sas_project(
            sas_file,
            search_dirs=include_paths,
            macro_vars=macro_vars,
        )
    else:
        return parse_sas_file(sas_file)


def _display_parse_result(result, file_label: str) -> None:
    """Display parse results in a formatted table."""
    console.print(f"\n[bold]File: {file_label}[/bold]")
    console.print(f"  Blocks: {len(result.blocks)}")
    console.print(f"  Coverage points: {len(result.all_coverage_points)}")
    console.print(f"  Variables: {len(result.all_variables)}")

    if result.errors:
        console.print(f"  [yellow]Warnings: {len(result.errors)}[/yellow]")
        for err in result.errors:
            console.print(f"    {err}")

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


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", "-V", help="Show version"),
) -> None:
    if version:
        console.print(f"sas-data-generator {__version__}")
        raise typer.Exit()


@app.command()
def analyze(
    sas_files: Optional[list[Path]] = typer.Argument(None, help="SAS program files to analyze"),
    project_dir: Optional[str] = typer.Option(
        None, "--project-dir", "-p",
        help="SAS project directory (scans all .sas files, resolves %INCLUDE)",
    ),
    entry_file: Optional[str] = typer.Option(
        None, "--entry", "-e",
        help="Entry-point file name within --project-dir (e.g., main.sas)",
    ),
    include_paths: Optional[list[str]] = typer.Option(
        None, "--include-path", "-I",
        help="Additional directories to search for %%INCLUDE files",
    ),
    macro_vars_json: Optional[str] = typer.Option(
        None, "--macros",
        help="JSON file with macro variables (used for resolving %%INCLUDE paths)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Parse SAS files and display coverage points and variables.

    Supports two modes:
    - File mode: pass one or more .sas files directly
    - Project mode: pass --project-dir to scan a directory and resolve %INCLUDE
    """
    _setup_logging(verbose)

    macro_vars = None
    if macro_vars_json:
        macro_vars = json.loads(Path(macro_vars_json).read_text())

    files, use_project = _resolve_sas_files(sas_files, project_dir, entry_file, include_paths, macro_vars)

    if not files:
        raise typer.Exit(1)

    if use_project and entry_file:
        # In project mode with an entry file: parse the whole project as one unit
        entry = files[0]
        result = _parse_file_or_project(entry, include_paths, macro_vars, use_project)
        _display_parse_result(result, f"{entry} (project mode, {len(files)} files scanned)")
    else:
        # File-by-file mode
        for sas_file in files:
            if not sas_file.exists():
                console.print(f"[red]File not found: {sas_file}[/red]")
                continue
            result = _parse_file_or_project(sas_file, include_paths, macro_vars, use_project)
            _display_parse_result(result, str(sas_file))


@app.command()
def instrument(
    sas_file: Path = typer.Argument(..., help="SAS program to instrument"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (stdout if omitted)"),
    include_paths: Optional[list[str]] = typer.Option(
        None, "--include-path", "-I",
        help="Additional directories to search for %%INCLUDE files",
    ),
    macro_vars_json: Optional[str] = typer.Option(
        None, "--macros",
        help="JSON file with macro variables",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Instrument a SAS file and show/write the result.

    With --include-path, resolves %INCLUDE before instrumenting.
    """
    _setup_logging(verbose)
    from .sas_instrumenter import instrument_sas_file

    if not sas_file.exists():
        console.print(f"[red]File not found: {sas_file}[/red]")
        raise typer.Exit(1)

    macro_vars = None
    if macro_vars_json:
        macro_vars = json.loads(Path(macro_vars_json).read_text())

    # If include paths are provided, resolve includes first and write a temp file
    if include_paths:
        from .include_resolver import resolve_includes
        resolved = resolve_includes(sas_file, search_dirs=include_paths, macro_vars=macro_vars)
        if resolved.errors:
            for err in resolved.errors:
                console.print(f"  [yellow]{err}[/yellow]")

        # Write resolved code to temp file for instrumentation
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(mode="w", suffix=".sas", delete=False, encoding="utf-8") as f:
            f.write(resolved.resolved_code)
            f.flush()
            result = instrument_sas_file(f.name)
        console.print(f"  Resolved {len(resolved.included_files)} included files")
    else:
        result = instrument_sas_file(sas_file)

    if output:
        output.write_text(result.instrumented_code, encoding="utf-8")
        console.print(f"Instrumented code written to: {output}")
    else:
        console.print(result.instrumented_code)

    console.print(f"\n[bold]Coverage points: {len(result.coverage_points)}[/bold]")


@app.command()
def generate(
    sas_files: Optional[list[Path]] = typer.Argument(None, help="SAS program files"),
    project_dir: Optional[str] = typer.Option(
        None, "--project-dir", "-p",
        help="SAS project directory",
    ),
    entry_file: Optional[str] = typer.Option(
        None, "--entry", "-e",
        help="Entry-point file within --project-dir",
    ),
    include_paths: Optional[list[str]] = typer.Option(
        None, "--include-path", "-I",
        help="Additional directories to search for %%INCLUDE files",
    ),
    output_dir: Path = typer.Option("./output", "--output", "-o", help="Output directory"),
    num_rows: int = typer.Option(20, "--rows", "-n", help="Number of rows per dataset"),
    seed: int = typer.Option(42, "--seed", "-s", help="Random seed for reproducibility"),
    formats: list[str] = typer.Option(["csv"], "--format", "-f", help="Output formats"),
    macro_vars_json: Optional[str] = typer.Option(
        None, "--macros",
        help="JSON file with macro variables",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Generate test datasets from SAS program analysis (no SAS execution).

    Supports --project-dir to analyze a whole SAS project at once.
    """
    _setup_logging(verbose)
    from .dataset_generator import generate_seed_datasets, export_dataset

    macro_vars = None
    if macro_vars_json:
        macro_vars = json.loads(Path(macro_vars_json).read_text())

    files, use_project = _resolve_sas_files(sas_files, project_dir, entry_file, include_paths, macro_vars)

    if not files:
        raise typer.Exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # In project mode with entry: parse everything as one unit
    if use_project and entry_file:
        entry = files[0]
        parse_result = _parse_file_or_project(entry, include_paths, macro_vars, use_project)
        console.print(f"\n[bold]Project: {entry} ({len(files)} files)[/bold]")
        console.print(f"  Blocks: {len(parse_result.blocks)}, "
                      f"Coverage points: {len(parse_result.all_coverage_points)}")

        datasets = generate_seed_datasets(parse_result, num_rows=num_rows, seed=seed)
        for ds in datasets:
            paths = export_dataset(ds, output_dir, formats=formats)
            console.print(f"  Generated: {ds.name} -> {paths}")
            for note in ds.generation_notes:
                console.print(f"    {note}")
    else:
        for sas_file in files:
            if not sas_file.exists():
                console.print(f"[red]File not found: {sas_file}[/red]")
                continue

            parse_result = _parse_file_or_project(sas_file, include_paths, macro_vars, use_project)
            datasets = generate_seed_datasets(parse_result, num_rows=num_rows, seed=seed)

            for ds in datasets:
                paths = export_dataset(ds, output_dir, formats=formats)
                console.print(f"  Generated: {ds.name} -> {paths}")
                for note in ds.generation_notes:
                    console.print(f"    {note}")


@app.command()
def run(
    sas_files: Optional[list[Path]] = typer.Argument(None, help="SAS program files"),
    project_dir: Optional[str] = typer.Option(
        None, "--project-dir", "-p",
        help="SAS project directory (resolves all %INCLUDE automatically)",
    ),
    entry_file: Optional[str] = typer.Option(
        None, "--entry", "-e",
        help="Entry-point file within --project-dir (e.g., main.sas)",
    ),
    include_paths: Optional[list[str]] = typer.Option(
        None, "--include-path", "-I",
        help="Additional directories to search for %%INCLUDE files",
    ),
    output_dir: Path = typer.Option("./output", "--output", "-o", help="Output directory"),
    num_rows: int = typer.Option(20, "--rows", "-n", help="Number of rows per seed dataset"),
    seed: int = typer.Option(42, "--seed", "-s", help="Random seed"),
    max_iterations: int = typer.Option(5, "--max-iter", "-i", help="Max mutation iterations"),
    coverage_target: float = typer.Option(100.0, "--target", "-t", help="Target coverage %%"),
    sas_executable: Optional[str] = typer.Option(None, "--sas", help="Path to SAS executable"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip SAS execution"),
    timeout: int = typer.Option(300, "--timeout", help="SAS execution timeout (seconds)"),
    formats: list[str] = typer.Option(["csv"], "--format", "-f", help="Output formats"),
    macro_vars_json: Optional[str] = typer.Option(None, "--macros", help="JSON file with macro variables"),
    libname_json: Optional[str] = typer.Option(None, "--libnames", help="JSON file with libname mappings"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Full loop: generate datasets, run SAS, measure coverage, mutate, repeat.

    Two modes:
    - File mode: sas-datagen run prog1.sas prog2.sas
    - Project mode: sas-datagen run --project-dir /path/to/project --entry main.sas

    Project mode resolves all %INCLUDE directives automatically.
    """
    _setup_logging(verbose)
    from .sas_parser import parse_sas_file, parse_sas_project
    from .sas_instrumenter import instrument_sas_file, instrument_sas_code
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

    files, use_project = _resolve_sas_files(sas_files, project_dir, entry_file, include_paths, macro_vars)
    if not files:
        raise typer.Exit(1)

    all_reports: list[CoverageReport] = []

    # In project mode with entry: treat the whole project as a single unit
    if use_project and entry_file:
        files_to_process = [files[0]]  # Only the resolved entry
    else:
        files_to_process = files

    for sas_file in files_to_process:
        if not sas_file.exists():
            console.print(f"[red]File not found: {sas_file}[/red]")
            continue

        console.print(f"\n[bold]=== Processing: {sas_file} ===[/bold]")

        # Phase 1: Parse (with or without include resolution)
        parse_result = _parse_file_or_project(sas_file, include_paths, macro_vars, use_project)
        console.print(f"  Parsed: {len(parse_result.blocks)} blocks, "
                      f"{len(parse_result.all_coverage_points)} coverage points")

        if parse_result.errors:
            for err in parse_result.errors:
                console.print(f"  [yellow]{err}[/yellow]")

        if not parse_result.all_coverage_points:
            console.print("  [yellow]No coverage points found — skipping[/yellow]")
            continue

        # Phase 2: Instrument
        coverage_csv = str(output_dir / f"{sas_file.stem}_coverage.csv")
        if use_project or include_paths:
            # Resolve includes first, then instrument the resolved code
            from .include_resolver import resolve_includes
            resolved = resolve_includes(sas_file, search_dirs=include_paths, macro_vars=macro_vars)
            instr_result = instrument_sas_code(
                resolved.resolved_code,
                coverage_csv_path=coverage_csv,
            )
        else:
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
