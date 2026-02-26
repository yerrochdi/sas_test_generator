"""SAS code instrumenter — injects coverage markers into SAS programs.

Strategy:
  We use a dual approach for recording coverage hits:
  1. PUT statements that write "COV:POINT=<id>" to the SAS log (always works)
  2. Optionally, output to a coverage dataset via a global _cov_* DATA step

  The PUT-based approach is primary for MVP because:
  - It requires no additional datasets or libname setup
  - It works inside DATA steps, PROC SQL (via execute), etc.
  - It's robust against errors in other parts of the code

Instrumentation rules:
  - DATA step entry: insert PUT after DATA statement
  - IF true branch: insert PUT after THEN (before DO or single statement)
  - IF false / ELSE: insert PUT after ELSE (or add ELSE with PUT)
  - SELECT/WHEN: insert PUT inside WHEN block
  - SELECT/OTHERWISE: insert PUT inside OTHERWISE block
  - PROC SQL WHERE: wrap in a passthrough comment (log-based only)
  - PROC SQL CASE/WHEN: add PUT via %PUT inside calculated column (limited)

For PROC SQL, we use %PUT (macro PUT) since regular PUT isn't available in SQL.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .sas_parser import (
    BlockType,
    CoveragePoint,
    CoveragePointType,
    ParseResult,
    SASBlock,
    parse_sas_file,
)

logger = logging.getLogger(__name__)


@dataclass
class InstrumentationResult:
    """Result of instrumenting a SAS file."""
    original_path: str
    instrumented_code: str
    coverage_points: list[CoveragePoint]
    preamble: str  # SAS code to prepend (coverage dataset init)
    postamble: str  # SAS code to append (coverage dataset export)
    coverage_dataset: str  # Name of the coverage tracking dataset


# Coverage dataset approach: we initialize a dataset at the top,
# append a row for each coverage hit via a tiny macro, and export at the end.
_PREAMBLE_TEMPLATE = """\
/************************************************************/
/* SAS Data Generator — Coverage Instrumentation Preamble   */
/* AUTO-GENERATED — DO NOT EDIT                             */
/************************************************************/

%macro _cov_hit(point_id);
  /* Write coverage marker to log (primary mechanism) */
  %put COV:POINT=&point_id;
%mend _cov_hit;

/* Initialize coverage tracking dataset */
data _cov_tracker;
  length point_id $50 hit_time 8;
  format hit_time datetime20.;
  stop;  /* Create empty dataset with correct structure */
run;

/* Macro to record a hit in the coverage dataset */
%macro _cov_record(point_id);
  data _cov_hit_temp;
    length point_id $50 hit_time 8;
    format hit_time datetime20.;
    point_id = "&point_id";
    hit_time = datetime();
    output;
  run;
  proc append base=_cov_tracker data=_cov_hit_temp force; run;
  proc delete data=_cov_hit_temp; run;
%mend _cov_record;

"""

_POSTAMBLE_TEMPLATE = """\

/************************************************************/
/* SAS Data Generator — Coverage Instrumentation Postamble  */
/* AUTO-GENERATED — DO NOT EDIT                             */
/************************************************************/

/* Export coverage results to CSV */
proc export data=_cov_tracker
  outfile="{coverage_csv_path}"
  dbms=csv replace;
run;

/* Also write summary to log */
data _null_;
  set _cov_tracker;
  put "COV:POINT=" point_id;
run;

%put COV:COMPLETE;
"""


def _make_put_statement(point_id: str) -> str:
    """Create a PUT statement that writes a coverage marker to the log."""
    return f'put "COV:POINT={point_id}";'


def _make_macro_call(point_id: str) -> str:
    """Create a macro call to record coverage hit (for use inside DATA steps)."""
    return f'%_cov_hit({point_id})'


def _instrument_data_step(block: SASBlock, raw_code: str) -> str:
    """Instrument a DATA step with coverage markers.

    We work on the raw text of the DATA step and insert PUT statements
    at the right locations.
    """
    lines = raw_code.split("\n")
    insertions: list[tuple[int, str]] = []  # (line_index, code_to_insert)

    for cp in block.coverage_points:
        # Convert absolute line number to relative within the block
        relative_line = cp.line_number - block.start_line

        if cp.point_type == CoveragePointType.STEP_ENTRY:
            # Insert after the DATA statement line (first line of block)
            insertions.append((1, f"  {_make_put_statement(cp.point_id)}"))

        elif cp.point_type == CoveragePointType.IF_TRUE:
            # Insert after THEN — we need to find the THEN on or after this line
            # and insert the PUT as the first statement in the DO block or before
            # the single statement
            target_line = max(0, min(relative_line, len(lines) - 1))
            # Search for THEN on this line or nearby
            for i in range(max(0, target_line), min(target_line + 3, len(lines))):
                if re.search(r"(?i)\bTHEN\b", lines[i]):
                    # Check if THEN is followed by DO on the same line
                    if re.search(r"(?i)\bTHEN\s+DO\b", lines[i]):
                        insertions.append((i + 1, f"    {_make_put_statement(cp.point_id)}"))
                    else:
                        # Insert PUT before the action statement
                        # We wrap: IF cond THEN DO; PUT; original_action; END;
                        # But simpler: just insert PUT after THEN on next line
                        insertions.append((i + 1, f"    {_make_put_statement(cp.point_id)}"))
                    break

        elif cp.point_type == CoveragePointType.IF_FALSE:
            # Find the ELSE clause corresponding to this IF
            target_line = max(0, min(relative_line, len(lines) - 1))
            found_else = False
            for i in range(max(0, target_line), min(target_line + 10, len(lines))):
                if re.search(r"(?i)\bELSE\b", lines[i]):
                    if re.search(r"(?i)\bELSE\s+DO\b", lines[i]):
                        insertions.append((i + 1, f"    {_make_put_statement(cp.point_id)}"))
                    else:
                        insertions.append((i + 1, f"    {_make_put_statement(cp.point_id)}"))
                    found_else = True
                    break

            if not found_else:
                # No ELSE exists — we need to add one
                # Find the end of the IF/THEN block
                for i in range(max(0, target_line), min(target_line + 15, len(lines))):
                    # Look for the end of the THEN block
                    if re.search(r"(?i)\bTHEN\b", lines[i]):
                        # Find matching END; or the single statement's semicolon
                        if re.search(r"(?i)\bTHEN\s+DO\b", lines[i]):
                            # Find the matching END;
                            depth = 1
                            for j in range(i + 1, len(lines)):
                                if re.search(r"(?i)\bDO\b", lines[j]):
                                    depth += 1
                                if re.search(r"(?i)\bEND\s*;", lines[j]):
                                    depth -= 1
                                    if depth == 0:
                                        insertions.append((
                                            j + 1,
                                            f"  else {_make_put_statement(cp.point_id)}",
                                        ))
                                        break
                        else:
                            # Single statement after THEN — find its semicolon
                            for j in range(i, len(lines)):
                                if ";" in lines[j] and j >= i:
                                    insertions.append((
                                        j + 1,
                                        f"  else {_make_put_statement(cp.point_id)}",
                                    ))
                                    break
                        break

        elif cp.point_type == CoveragePointType.SELECT_WHEN:
            target_line = max(0, min(relative_line, len(lines) - 1))
            for i in range(max(0, target_line), min(target_line + 3, len(lines))):
                if re.search(r"(?i)\bWHEN\b", lines[i]):
                    # Check for DO block
                    if re.search(r"(?i)\bDO\s*;", lines[i]):
                        insertions.append((i + 1, f"    {_make_put_statement(cp.point_id)}"))
                    else:
                        insertions.append((i + 1, f"    {_make_put_statement(cp.point_id)}"))
                    break

        elif cp.point_type == CoveragePointType.SELECT_OTHERWISE:
            target_line = max(0, min(relative_line, len(lines) - 1))
            for i in range(max(0, target_line), min(target_line + 3, len(lines))):
                if re.search(r"(?i)\bOTHERWISE\b", lines[i]):
                    insertions.append((i + 1, f"    {_make_put_statement(cp.point_id)}"))
                    break

    # Apply insertions in reverse order to preserve line indices
    insertions.sort(key=lambda x: x[0], reverse=True)
    for line_idx, code in insertions:
        line_idx = min(line_idx, len(lines))
        lines.insert(line_idx, code)

    return "\n".join(lines)


def _instrument_proc_sql(block: SASBlock, raw_code: str) -> str:
    """Instrument a PROC SQL block with coverage markers.

    PROC SQL doesn't support PUT directly, so we use %PUT (macro facility).
    For CASE/WHEN, we can't easily inject into SQL expressions,
    so we add %PUT before/after the SQL statement.
    """
    lines = raw_code.split("\n")
    insertions: list[tuple[int, str]] = []

    for cp in block.coverage_points:
        relative_line = cp.line_number - block.start_line

        if cp.point_type == CoveragePointType.STEP_ENTRY:
            # Insert %PUT after PROC SQL;
            insertions.append((1, f"  %_cov_hit({cp.point_id})"))

        elif cp.point_type == CoveragePointType.SQL_WHERE:
            # We can't instrument inside WHERE easily.
            # Strategy: Add %PUT before the SELECT that contains this WHERE.
            # The coverage will be "this SQL with WHERE was executed"
            target_line = max(0, min(relative_line, len(lines) - 1))
            insertions.append((target_line, f"  %_cov_hit({cp.point_id})"))

        elif cp.point_type in (
            CoveragePointType.SQL_CASE_WHEN,
            CoveragePointType.SQL_CASE_ELSE,
        ):
            # For CASE/WHEN in SQL, we record that the SQL block ran.
            # True branch-level coverage of SQL CASE requires runtime analysis
            # of the output data. We mark this as a limitation.
            target_line = max(0, min(relative_line, len(lines) - 1))
            insertions.append((target_line, f"  %_cov_hit({cp.point_id})"))

    insertions.sort(key=lambda x: x[0], reverse=True)
    for line_idx, code in insertions:
        line_idx = min(line_idx, len(lines))
        lines.insert(line_idx, code)

    return "\n".join(lines)


def instrument_sas_file(
    file_path: str | Path,
    coverage_csv_path: str = "_coverage_results.csv",
    parse_result: ParseResult | None = None,
) -> InstrumentationResult:
    """Instrument a SAS file with coverage markers.

    Args:
        file_path: Path to the original SAS file.
        coverage_csv_path: Where the coverage CSV should be written by SAS.
        parse_result: Pre-computed parse result (avoids re-parsing).

    Returns:
        InstrumentationResult with the instrumented code and metadata.
    """
    file_path = Path(file_path)
    logger.info("Instrumenting SAS file: %s", file_path)

    if parse_result is None:
        parse_result = parse_sas_file(file_path)

    original_code = file_path.read_text(encoding="utf-8", errors="replace")

    # Build a map from (start_line, end_line) -> instrumented text
    # Process blocks in reverse order to preserve positions
    blocks_sorted = sorted(parse_result.blocks, key=lambda b: b.start_line, reverse=True)

    code_lines = original_code.split("\n")

    for block in blocks_sorted:
        # Extract the block's raw text from the original code
        block_start_idx = block.start_line - 1  # 0-based
        block_end_idx = block.end_line  # exclusive

        block_lines = code_lines[block_start_idx:block_end_idx]
        block_text = "\n".join(block_lines)

        if block.block_type == BlockType.DATA_STEP:
            instrumented = _instrument_data_step(block, block_text)
        elif block.block_type == BlockType.PROC_SQL:
            instrumented = _instrument_proc_sql(block, block_text)
        else:
            continue  # Skip other PROC types for MVP

        # Replace in code_lines
        new_lines = instrumented.split("\n")
        code_lines[block_start_idx:block_end_idx] = new_lines

    instrumented_code = "\n".join(code_lines)

    preamble = _PREAMBLE_TEMPLATE
    postamble = _POSTAMBLE_TEMPLATE.format(coverage_csv_path=coverage_csv_path)

    return InstrumentationResult(
        original_path=str(file_path),
        instrumented_code=preamble + instrumented_code + postamble,
        coverage_points=parse_result.all_coverage_points,
        preamble=preamble,
        postamble=postamble,
        coverage_dataset="_cov_tracker",
    )


def instrument_sas_code(
    code: str,
    file_id: str = "inline",
    coverage_csv_path: str = "_coverage_results.csv",
) -> InstrumentationResult:
    """Instrument SAS code from a string (useful for testing)."""
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(
        mode="w", suffix=".sas", delete=False, encoding="utf-8"
    ) as f:
        f.write(code)
        f.flush()
        return instrument_sas_file(f.name, coverage_csv_path)
