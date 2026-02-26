"""Test dataset generator — create and mutate datasets to maximize SAS code coverage.

Strategy:
1. SEED phase: Analyze parsed SAS code to understand what variables are needed,
   their types, and what conditions exist. Generate initial datasets with:
   - Boundary values (0, -1, MAX_INT, empty string, etc.)
   - Values extracted from conditions (if age > 65, generate rows with age=64,65,66)
   - Random values with appropriate distributions

2. MUTATE phase: After each SAS run, look at which coverage points were missed.
   For missed IF/WHEN branches, analyze the condition and generate targeted values
   that should trigger the missed branch.

3. EDGE CASE phase: Add rows with NULL/missing values, extreme values, and
   type-boundary values.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import numpy as np

from .coverage import CoverageReport
from .sas_parser import (
    CoveragePoint,
    CoveragePointType,
    ParseResult,
    VariableRef,
)

logger = logging.getLogger(__name__)


@dataclass
class DatasetSpec:
    """Specification for a dataset to be generated."""
    name: str  # Dataset name (e.g., "work.input" or "mydata")
    variables: list[VariableRef] = field(default_factory=list)
    num_rows: int = 20


@dataclass
class GeneratedDataset:
    """A generated test dataset."""
    name: str
    df: pd.DataFrame
    csv_path: str = ""
    generation_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Value generation helpers
# ---------------------------------------------------------------------------

_NUMERIC_EDGE_VALUES = [0, 1, -1, 0.5, -0.5, 999999, -999999, 0.001]
_DATE_EDGE_VALUES = pd.to_datetime(["1960-01-01", "2000-01-01", "2025-12-31", "1999-12-31"])
_CHAR_EDGE_VALUES = ["", " ", "A", "test", "NULL", "missing", "X" * 50]


def _extract_threshold_values(condition: str) -> list[float]:
    """Extract numeric threshold values from a SAS condition.

    For example: 'age > 65' -> [64, 65, 66]
                 'score >= 80' -> [79, 80, 81]
                 'amount in (100, 200, 300)' -> [100, 200, 300, 99, 301]
    """
    values = []

    # Direct comparisons: var OP number
    for match in re.finditer(r"(\w+)\s*(>=?|<=?|=|eq|ne|gt|lt|ge|le)\s*(\d+\.?\d*)", condition, re.I):
        try:
            threshold = float(match.group(3))
            operator = match.group(2).lower()

            # Generate boundary values around the threshold
            if operator in (">", "gt"):
                values.extend([threshold - 1, threshold, threshold + 1])
            elif operator in (">=", "ge"):
                values.extend([threshold - 1, threshold, threshold + 1])
            elif operator in ("<", "lt"):
                values.extend([threshold - 1, threshold, threshold + 1])
            elif operator in ("<=", "le"):
                values.extend([threshold - 1, threshold, threshold + 1])
            elif operator in ("=", "eq"):
                values.extend([threshold - 1, threshold, threshold + 1])
            elif operator in ("ne",):
                values.extend([threshold, threshold + 1])
        except ValueError:
            pass

    # IN lists: var in (val1, val2, ...)
    for match in re.finditer(r"\bin\s*\(([^)]+)\)", condition, re.I):
        for val_str in match.group(1).split(","):
            val_str = val_str.strip().strip("'\"")
            try:
                values.append(float(val_str))
            except ValueError:
                pass  # Non-numeric, skip

    return values


def _extract_string_values(condition: str) -> list[str]:
    """Extract string literal values from a SAS condition.

    For example: 'status = "ACTIVE"' -> ["ACTIVE", "INACTIVE", ""]
                 'type in ("A", "B")' -> ["A", "B", "C", ""]
    """
    values = []

    # Quoted strings
    for match in re.finditer(r"""['"]([^'"]*?)['"]""", condition):
        values.append(match.group(1))

    # Add variations
    extra = []
    for v in values:
        if v.upper() != v:
            extra.append(v.upper())
        if v:
            extra.append("")
            extra.append(v[0])  # First character
    values.extend(extra)

    return list(set(values))


def _generate_column_values(
    var: VariableRef,
    num_rows: int,
    rng: np.random.Generator,
    conditions: list[str] | None = None,
) -> pd.Series:
    """Generate values for a single column based on variable metadata and conditions."""
    values = []

    # Gather condition-based values
    condition_numerics: list[float] = []
    condition_strings: list[str] = []
    if conditions:
        for cond in conditions:
            condition_numerics.extend(_extract_threshold_values(cond))
            condition_strings.extend(_extract_string_values(cond))

    if var.inferred_type == "character":
        # Mix of condition-extracted values and random strings
        pool = condition_strings or _CHAR_EDGE_VALUES[:]
        if not pool:
            pool = ["A", "B", "C", "X", ""]
        values = list(rng.choice(pool, size=num_rows))

    elif var.inferred_type == "date":
        # Generate date values
        base_dates = _DATE_EDGE_VALUES.tolist()
        if condition_numerics:
            # SAS dates are days since 1960-01-01
            for n in condition_numerics:
                try:
                    base_dates.append(pd.Timestamp("1960-01-01") + pd.Timedelta(days=int(n)))
                except (OverflowError, ValueError):
                    pass
        # Fill remaining with random dates
        pool_dates = base_dates[:num_rows]
        while len(pool_dates) < num_rows:
            random_days = rng.integers(0, 25000)
            pool_dates.append(pd.Timestamp("1960-01-01") + pd.Timedelta(days=int(random_days)))
        values = pool_dates[:num_rows]

    else:
        # Numeric (default)
        # Start with condition-based values and edge values
        seed_values = condition_numerics + _NUMERIC_EDGE_VALUES
        # Ensure we have enough values
        if len(seed_values) >= num_rows:
            values = list(rng.choice(seed_values, size=num_rows, replace=True))
        else:
            values = seed_values[:]
            # Fill remaining with random values in a reasonable range
            if condition_numerics:
                low = min(condition_numerics) - 10
                high = max(condition_numerics) + 10
            else:
                low, high = -100, 100
            remaining = num_rows - len(values)
            values.extend(rng.uniform(low, high, size=remaining).tolist())
        # Add some NaN (SAS missing) values
        if num_rows > 5:
            nan_indices = rng.choice(num_rows, size=max(1, num_rows // 10), replace=False)
            for idx in nan_indices:
                if idx < len(values):
                    values[idx] = np.nan

    return pd.Series(values[:num_rows], name=var.name)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_seed_datasets(
    parse_result: ParseResult,
    num_rows: int = 20,
    seed: int = 42,
) -> list[GeneratedDataset]:
    """Generate initial seed datasets based on parsed SAS code.

    Analyzes the SAS code to determine:
    - What input datasets are needed (from SET/MERGE/FROM statements)
    - What columns are needed (from INPUT/conditions)
    - What values to use (from conditions/comparisons)
    """
    rng = np.random.default_rng(seed)
    datasets: list[GeneratedDataset] = []

    # Collect all input datasets and their required variables
    dataset_vars: dict[str, list[VariableRef]] = {}
    dataset_conditions: dict[str, list[str]] = {}

    for block in parse_result.blocks:
        for ds_name in block.input_datasets:
            ds_key = ds_name.lower()
            if ds_key not in dataset_vars:
                dataset_vars[ds_key] = []
                dataset_conditions[ds_key] = []

            # Add variables found in this block
            dataset_vars[ds_key].extend(block.variables)

            # Collect conditions
            for cp in block.coverage_points:
                if cp.condition:
                    dataset_conditions[ds_key].append(cp.condition)

    # Also add variables from the global parse result
    if not dataset_vars:
        # No input datasets found — create a default one
        if parse_result.all_variables:
            dataset_vars["input"] = parse_result.all_variables
            dataset_conditions["input"] = [
                cp.condition for cp in parse_result.all_coverage_points if cp.condition
            ]

    # Generate each dataset
    for ds_name, variables in dataset_vars.items():
        # Deduplicate variables
        seen = {}
        for v in variables:
            key = v.name.lower()
            if key not in seen or (seen[key].inferred_type == "unknown" and v.inferred_type != "unknown"):
                seen[key] = v
        unique_vars = list(seen.values())

        if not unique_vars:
            logger.warning("No variables found for dataset %s, creating empty dataset", ds_name)
            datasets.append(GeneratedDataset(
                name=ds_name,
                df=pd.DataFrame(),
                generation_notes=["No variables detected"],
            ))
            continue

        # Find conditions that reference each variable
        conditions = dataset_conditions.get(ds_name, [])
        var_conditions: dict[str, list[str]] = {}
        for cond in conditions:
            for v in unique_vars:
                if re.search(rf"\b{re.escape(v.name)}\b", cond, re.I):
                    var_conditions.setdefault(v.name.lower(), []).append(cond)

        # Generate columns
        columns = {}
        for v in unique_vars:
            v_conds = var_conditions.get(v.name.lower(), [])
            columns[v.name] = _generate_column_values(v, num_rows, rng, v_conds)

        df = pd.DataFrame(columns)
        notes = [
            f"Seed dataset with {num_rows} rows, {len(unique_vars)} columns",
            f"Variables: {[v.name for v in unique_vars]}",
            f"Conditions analyzed: {len(conditions)}",
        ]

        datasets.append(GeneratedDataset(
            name=ds_name,
            df=df,
            generation_notes=notes,
        ))

        logger.info("Generated seed dataset '%s': %d rows x %d cols", ds_name, num_rows, len(unique_vars))

    return datasets


def mutate_datasets(
    datasets: list[GeneratedDataset],
    coverage_report: CoverageReport,
    parse_result: ParseResult,
    seed: int = 42,
    mutation_rows: int = 10,
) -> list[GeneratedDataset]:
    """Mutate datasets to target uncovered branches.

    For each missed coverage point, analyze its condition and generate
    new rows that should trigger it.
    """
    rng = np.random.default_rng(seed)
    mutated = []

    missed = coverage_report.missed_points
    if not missed:
        logger.info("No missed coverage points — nothing to mutate")
        return datasets

    logger.info("Targeting %d missed coverage points", len(missed))

    for ds in datasets:
        new_rows: list[dict] = []

        for cp in missed:
            if not cp.condition:
                continue

            # Generate values that should trigger this branch
            if cp.point_type == CoveragePointType.IF_TRUE:
                # Need to make the condition TRUE
                _add_targeted_rows(new_rows, cp.condition, ds.df.columns.tolist(), rng, target_true=True)
            elif cp.point_type == CoveragePointType.IF_FALSE:
                # Need to make the condition FALSE
                _add_targeted_rows(new_rows, cp.condition, ds.df.columns.tolist(), rng, target_true=False)
            elif cp.point_type in (CoveragePointType.SELECT_WHEN, CoveragePointType.SQL_CASE_WHEN):
                _add_targeted_rows(new_rows, cp.condition, ds.df.columns.tolist(), rng, target_true=True)
            elif cp.point_type in (CoveragePointType.SELECT_OTHERWISE, CoveragePointType.SQL_CASE_ELSE):
                # Need a value that doesn't match ANY of the WHEN conditions
                _add_edge_case_rows(new_rows, ds.df.columns.tolist(), rng)

        if new_rows:
            mutation_df = pd.DataFrame(new_rows)
            # Align columns
            for col in ds.df.columns:
                if col not in mutation_df.columns:
                    mutation_df[col] = np.nan
            mutation_df = mutation_df[ds.df.columns]

            combined = pd.concat([ds.df, mutation_df], ignore_index=True)
            notes = ds.generation_notes + [f"Mutated: added {len(new_rows)} targeted rows"]
            mutated.append(GeneratedDataset(
                name=ds.name,
                df=combined,
                generation_notes=notes,
            ))
            logger.info("Mutated dataset '%s': added %d rows", ds.name, len(new_rows))
        else:
            mutated.append(ds)

    return mutated


def _add_targeted_rows(
    rows: list[dict],
    condition: str,
    columns: list[str],
    rng: np.random.Generator,
    target_true: bool = True,
) -> None:
    """Generate rows targeting a specific condition to be true or false."""
    # Parse the condition to extract variable comparisons
    for match in re.finditer(
        r"(\w+)\s*(>=?|<=?|=|ne|eq|gt|lt|ge|le)\s*(\d+\.?\d*)",
        condition, re.I,
    ):
        var_name = match.group(1).lower()
        operator = match.group(2).lower()
        threshold = float(match.group(3))

        if var_name not in [c.lower() for c in columns]:
            continue

        # Map column name (case-insensitive match)
        col_name = next(c for c in columns if c.lower() == var_name)

        # Determine target value
        if target_true:
            value = _value_to_satisfy(operator, threshold)
        else:
            value = _value_to_violate(operator, threshold)

        row = {col_name: value}
        rows.append(row)
        return

    # String conditions
    for match in re.finditer(
        r"""(\w+)\s*=\s*['"]([^'"]*?)['"]""",
        condition, re.I,
    ):
        var_name = match.group(1).lower()
        string_val = match.group(2)

        if var_name not in [c.lower() for c in columns]:
            continue

        col_name = next(c for c in columns if c.lower() == var_name)

        if target_true:
            rows.append({col_name: string_val})
        else:
            rows.append({col_name: "ZZZZ_NOMATCH"})
        return


def _add_edge_case_rows(
    rows: list[dict],
    columns: list[str],
    rng: np.random.Generator,
) -> None:
    """Add edge-case rows (missing values, extremes)."""
    # Row with all missing
    rows.append({col: np.nan for col in columns})
    # Row with extreme values
    extreme_row = {}
    for col in columns:
        extreme_row[col] = rng.choice([999999, -999999, 0])
    rows.append(extreme_row)


def _value_to_satisfy(operator: str, threshold: float) -> float:
    """Return a value that satisfies: value <operator> threshold."""
    op = operator.lower()
    if op in (">", "gt"):
        return threshold + 1
    elif op in (">=", "ge"):
        return threshold
    elif op in ("<", "lt"):
        return threshold - 1
    elif op in ("<=", "le"):
        return threshold
    elif op in ("=", "eq"):
        return threshold
    elif op in ("ne",):
        return threshold + 1
    return threshold


def _value_to_violate(operator: str, threshold: float) -> float:
    """Return a value that violates: value <operator> threshold."""
    op = operator.lower()
    if op in (">", "gt"):
        return threshold - 1
    elif op in (">=", "ge"):
        return threshold - 1
    elif op in ("<", "lt"):
        return threshold + 1
    elif op in ("<=", "le"):
        return threshold + 1
    elif op in ("=", "eq"):
        return threshold + 1
    elif op in ("ne",):
        return threshold
    return threshold + 1


def export_dataset(
    dataset: GeneratedDataset,
    output_dir: str | Path,
    formats: list[str] | None = None,
) -> list[str]:
    """Export a generated dataset to files.

    Args:
        dataset: The dataset to export.
        output_dir: Directory to write files to.
        formats: List of formats ("csv", "sas7bdat"). Defaults to ["csv"].

    Returns:
        List of file paths created.
    """
    if formats is None:
        formats = ["csv"]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = []

    # Clean dataset name for filename
    clean_name = re.sub(r"[^\w]", "_", dataset.name)

    if "csv" in formats:
        csv_path = output_dir / f"{clean_name}.csv"
        dataset.df.to_csv(csv_path, index=False)
        dataset.csv_path = str(csv_path)
        paths.append(str(csv_path))
        logger.info("Exported CSV: %s", csv_path)

    if "sas7bdat" in formats:
        try:
            import pyreadstat
            sas_path = output_dir / f"{clean_name}.sas7bdat"
            pyreadstat.write_sas7bdat(dataset.df, str(sas_path))
            paths.append(str(sas_path))
            logger.info("Exported SAS7BDAT: %s", sas_path)
        except ImportError:
            logger.warning(
                "pyreadstat not installed — skipping SAS7BDAT export. "
                "Install with: pip install pyreadstat"
            )

    return paths
