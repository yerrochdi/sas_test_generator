"""Lightweight regex-based SAS parser for MVP coverage instrumentation.

This parser identifies:
- DATA step boundaries (DATA ... RUN;)
- PROC step boundaries (PROC ... RUN;/QUIT;)
- IF/THEN/ELSE branches
- SELECT/WHEN/OTHERWISE blocks
- Variable references in conditions and assignments
- INPUT statement column definitions

Limitations (MVP):
- Does not resolve %macro/%include (treats them as opaque)
- Does not handle nested DATA steps (rare in practice)
- Regex-based: may misparse code inside comments or string literals
- Does not parse PROC SQL subqueries deeply

These are documented and planned for V1 improvements.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path

logger = logging.getLogger(__name__)


class BlockType(Enum):
    DATA_STEP = auto()
    PROC_SQL = auto()
    PROC_OTHER = auto()


class CoveragePointType(Enum):
    STEP_ENTRY = auto()       # DATA or PROC step entered
    IF_TRUE = auto()          # IF condition evaluated to true
    IF_FALSE = auto()         # ELSE branch taken (or IF condition false)
    SELECT_WHEN = auto()      # WHEN clause matched
    SELECT_OTHERWISE = auto() # OTHERWISE clause reached
    SQL_WHERE = auto()        # SQL WHERE filter path
    SQL_CASE_WHEN = auto()    # SQL CASE/WHEN branch
    SQL_CASE_ELSE = auto()    # SQL CASE/ELSE branch


@dataclass
class CoveragePoint:
    """A single instrumentable location in SAS code."""
    point_id: str
    point_type: CoveragePointType
    line_number: int
    description: str
    condition: str = ""  # The original condition text, if applicable


@dataclass
class VariableRef:
    """A variable referenced in SAS code with inferred type hints."""
    name: str
    inferred_type: str = "unknown"  # "numeric", "character", "date", "unknown"
    source: str = ""  # Where it was found: "input", "condition", "assignment", "set"
    line_number: int = 0
    format: str = ""  # SAS format if detected (e.g., "date9.", "$20.")


@dataclass
class SASBlock:
    """A parsed DATA or PROC block."""
    block_type: BlockType
    name: str                 # Dataset name or proc name
    start_line: int
    end_line: int
    raw_text: str
    coverage_points: list[CoveragePoint] = field(default_factory=list)
    variables: list[VariableRef] = field(default_factory=list)
    input_datasets: list[str] = field(default_factory=list)
    output_datasets: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    """Complete parse result for a SAS file."""
    file_path: str
    blocks: list[SASBlock] = field(default_factory=list)
    all_coverage_points: list[CoveragePoint] = field(default_factory=list)
    all_variables: list[VariableRef] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Strip block comments /* ... */ and line comments * ... ;
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"(?m)^\s*\*[^;]*;")

# DATA step: DATA <names> ; ... RUN ;
_DATA_STEP_RE = re.compile(
    r"(?i)\bDATA\s+([\w.'\"]+(?:\s+[\w.'\"]+)*)\s*;(.*?)RUN\s*;",
    re.DOTALL,
)

# PROC SQL: PROC SQL ... QUIT;
_PROC_SQL_RE = re.compile(
    r"(?i)\bPROC\s+SQL\b[^;]*;(.*?)QUIT\s*;",
    re.DOTALL,
)

# Other PROC: PROC <name> ... RUN;/QUIT;
_PROC_OTHER_RE = re.compile(
    r"(?i)\bPROC\s+(\w+)\b(?!\s+SQL)[^;]*;(.*?)(?:RUN|QUIT)\s*;",
    re.DOTALL,
)

# IF / THEN / ELSE  (DATA step style)
_IF_THEN_RE = re.compile(
    r"(?i)\bIF\b\s+(.+?)\s+\bTHEN\b",
    re.DOTALL,
)
_ELSE_RE = re.compile(r"(?i)\bELSE\b")

# SELECT / WHEN / OTHERWISE
_SELECT_RE = re.compile(r"(?i)\bSELECT\s*(?:\(([^)]*)\))?\s*;", re.DOTALL)
_WHEN_RE = re.compile(r"(?i)\bWHEN\s*\(([^)]+)\)", re.DOTALL)
_OTHERWISE_RE = re.compile(r"(?i)\bOTHERWISE\b")

# SQL: WHERE clause
_SQL_WHERE_RE = re.compile(r"(?i)\bWHERE\b\s+(.+?)(?:;|\bGROUP\b|\bORDER\b|\bHAVING\b)", re.DOTALL)

# SQL: CASE WHEN ... THEN ... ELSE ... END
_SQL_CASE_RE = re.compile(r"(?i)\bCASE\b(.*?)\bEND\b", re.DOTALL)
_SQL_WHEN_RE = re.compile(r"(?i)\bWHEN\b\s+(.+?)\s+\bTHEN\b", re.DOTALL)
_SQL_ELSE_RE = re.compile(r"(?i)\bELSE\b")

# SET statement (input datasets)
_SET_RE = re.compile(r"(?i)\bSET\s+([\w.]+(?:\s*\(.*?\))?(?:\s+[\w.]+(?:\s*\(.*?\))?)*)\s*;")

# MERGE statement
_MERGE_RE = re.compile(r"(?i)\bMERGE\s+([\w.]+(?:\s*\(.*?\))?(?:\s+[\w.]+(?:\s*\(.*?\))?)*)\s*;")

# INPUT statement (column definitions)
_INPUT_RE = re.compile(r"(?i)\bINPUT\b\s+(.+?)\s*;", re.DOTALL)

# Variable names in conditions: simple heuristic
_VAR_IN_CONDITION_RE = re.compile(r"\b([a-zA-Z_]\w*)\b")

# Numeric literals and comparison operators (for condition analysis)
_COMPARISON_RE = re.compile(
    r"([a-zA-Z_]\w*)\s*(>=?|<=?|=|ne|eq|gt|lt|ge|le|in)\s*"
    r"[('\"]?(\S+?)[)'\"]?(?:\s|$|;)",
    re.IGNORECASE,
)

# SAS keywords to exclude from variable detection
_SAS_KEYWORDS = frozenset({
    "if", "then", "else", "do", "end", "select", "when", "otherwise",
    "output", "return", "delete", "stop", "run", "quit", "data", "proc",
    "set", "merge", "by", "where", "and", "or", "not", "in", "eq", "ne",
    "gt", "lt", "ge", "le", "input", "put", "length", "format", "informat",
    "retain", "drop", "keep", "rename", "label", "array", "attrib",
    "cards", "datalines", "infile", "file", "filename", "libname",
    "options", "title", "footnote", "null", "missing",
    "create", "table", "as", "from", "group", "order", "having",
    "left", "right", "inner", "outer", "join", "on", "union", "all",
    "distinct", "into", "case", "sum", "count", "avg", "min", "max",
    "mean", "std", "var", "n",
})


def _strip_comments(code: str) -> str:
    """Remove SAS comments while preserving line numbers (replace with spaces)."""
    # Replace block comments with equivalent whitespace
    def _block_replacer(m: re.Match) -> str:
        text = m.group(0)
        return re.sub(r"[^\n]", " ", text)

    result = _BLOCK_COMMENT_RE.sub(_block_replacer, code)
    # Replace line comments
    result = _LINE_COMMENT_RE.sub(lambda m: " " * len(m.group(0)), result)
    return result


def _line_number_at(code: str, pos: int) -> int:
    """Return 1-based line number for character position in code."""
    return code[:pos].count("\n") + 1


def _extract_variables_from_condition(condition: str, line_number: int) -> list[VariableRef]:
    """Extract variable references from a SAS condition expression."""
    variables = []
    seen = set()

    for match in _COMPARISON_RE.finditer(condition):
        var_name = match.group(1).lower()
        operator = match.group(2).lower()
        value = match.group(3).strip("'\"()")

        if var_name in _SAS_KEYWORDS or var_name in seen:
            continue
        seen.add(var_name)

        # Infer type from the comparison value
        inferred_type = "unknown"
        if value.replace(".", "", 1).replace("-", "", 1).isdigit():
            inferred_type = "numeric"
        elif value.startswith("'") or value.startswith('"'):
            inferred_type = "character"

        variables.append(VariableRef(
            name=var_name,
            inferred_type=inferred_type,
            source="condition",
            line_number=line_number,
        ))

    return variables


def _extract_variables_from_input(input_text: str, line_number: int) -> list[VariableRef]:
    """Extract variable definitions from an INPUT statement."""
    variables = []
    # Tokenize loosely: name [$] [format] [@@]
    tokens = input_text.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        # Skip positional pointers like @1, +2, #3
        if re.match(r"^[@#+]\d*$", token) or token in ("@@", "@"):
            i += 1
            continue

        if re.match(r"^[a-zA-Z_]\w*$", token) and token.lower() not in _SAS_KEYWORDS:
            var_type = "unknown"
            fmt = ""
            # Check next token for $ or format
            if i + 1 < len(tokens):
                next_tok = tokens[i + 1]
                if next_tok == "$":
                    var_type = "character"
                    i += 1
                elif re.match(r"^\$?\d+\.$", next_tok):
                    var_type = "character" if next_tok.startswith("$") else "numeric"
                    fmt = next_tok
                    i += 1
                elif re.match(r"^\w+\d*\.\d*$", next_tok):
                    fmt = next_tok
                    if "date" in next_tok.lower() or "yymm" in next_tok.lower():
                        var_type = "date"
                    else:
                        var_type = "numeric"
                    i += 1

            variables.append(VariableRef(
                name=token.lower(),
                inferred_type=var_type if var_type != "unknown" else "numeric",
                source="input",
                line_number=line_number,
                format=fmt,
            ))
        i += 1

    return variables


def _parse_data_step(
    match: re.Match,
    code: str,
    point_counter: list[int],
    file_id: str,
) -> SASBlock:
    """Parse a single DATA step match into a SASBlock with coverage points."""
    dataset_names_raw = match.group(1)
    body = match.group(2)
    start_line = _line_number_at(code, match.start())
    end_line = _line_number_at(code, match.end())

    output_datasets = [
        name.strip().strip("'\"")
        for name in re.split(r"\s+", dataset_names_raw.strip())
        if name.strip()
    ]

    block = SASBlock(
        block_type=BlockType.DATA_STEP,
        name=output_datasets[0] if output_datasets else "unknown",
        start_line=start_line,
        end_line=end_line,
        raw_text=match.group(0),
        output_datasets=output_datasets,
    )

    # STEP_ENTRY point
    point_counter[0] += 1
    pid = f"{file_id}:{point_counter[0]}"
    block.coverage_points.append(CoveragePoint(
        point_id=pid,
        point_type=CoveragePointType.STEP_ENTRY,
        line_number=start_line,
        description=f"DATA step entry: {block.name}",
    ))

    # Input datasets from SET / MERGE
    for set_match in _SET_RE.finditer(body):
        datasets = re.findall(r"([\w.]+)", set_match.group(1))
        block.input_datasets.extend(d.lower() for d in datasets if d.lower() not in _SAS_KEYWORDS)

    for merge_match in _MERGE_RE.finditer(body):
        datasets = re.findall(r"([\w.]+)", merge_match.group(1))
        block.input_datasets.extend(d.lower() for d in datasets if d.lower() not in _SAS_KEYWORDS)

    # Variables from INPUT
    for input_match in _INPUT_RE.finditer(body):
        line_num = _line_number_at(code, match.start() + input_match.start())
        block.variables.extend(_extract_variables_from_input(input_match.group(1), line_num))

    # IF/THEN branches
    for if_match in _IF_THEN_RE.finditer(body):
        condition = if_match.group(1).strip()
        line_num = _line_number_at(code, match.start() + if_match.start())

        point_counter[0] += 1
        pid_true = f"{file_id}:{point_counter[0]}"
        block.coverage_points.append(CoveragePoint(
            point_id=pid_true,
            point_type=CoveragePointType.IF_TRUE,
            line_number=line_num,
            description=f"IF true: {condition[:60]}",
            condition=condition,
        ))

        point_counter[0] += 1
        pid_false = f"{file_id}:{point_counter[0]}"
        block.coverage_points.append(CoveragePoint(
            point_id=pid_false,
            point_type=CoveragePointType.IF_FALSE,
            line_number=line_num,
            description=f"IF false/ELSE: {condition[:60]}",
            condition=condition,
        ))

        # Extract variables from condition
        block.variables.extend(_extract_variables_from_condition(condition, line_num))

    # SELECT/WHEN/OTHERWISE
    for sel_match in _SELECT_RE.finditer(body):
        sel_start = match.start() + sel_match.start()
        # Find all WHENs between this SELECT and next END
        sel_body_start = sel_match.end()
        end_match = re.search(r"(?i)\bEND\s*;", body[sel_match.start():])
        if not end_match:
            continue
        sel_body = body[sel_match.start():sel_match.start() + end_match.end()]

        for when_match in _WHEN_RE.finditer(sel_body):
            condition = when_match.group(1).strip()
            line_num = _line_number_at(code, sel_start + when_match.start())
            point_counter[0] += 1
            pid = f"{file_id}:{point_counter[0]}"
            block.coverage_points.append(CoveragePoint(
                point_id=pid,
                point_type=CoveragePointType.SELECT_WHEN,
                line_number=line_num,
                description=f"WHEN: {condition[:60]}",
                condition=condition,
            ))
            block.variables.extend(_extract_variables_from_condition(condition, line_num))

        if _OTHERWISE_RE.search(sel_body):
            ow_match = _OTHERWISE_RE.search(sel_body)
            line_num = _line_number_at(code, sel_start + ow_match.start())
            point_counter[0] += 1
            pid = f"{file_id}:{point_counter[0]}"
            block.coverage_points.append(CoveragePoint(
                point_id=pid,
                point_type=CoveragePointType.SELECT_OTHERWISE,
                line_number=line_num,
                description="OTHERWISE branch",
            ))

    return block


def _parse_proc_sql(
    match: re.Match,
    code: str,
    point_counter: list[int],
    file_id: str,
) -> SASBlock:
    """Parse a PROC SQL block."""
    body = match.group(1)
    start_line = _line_number_at(code, match.start())
    end_line = _line_number_at(code, match.end())

    block = SASBlock(
        block_type=BlockType.PROC_SQL,
        name="SQL",
        start_line=start_line,
        end_line=end_line,
        raw_text=match.group(0),
    )

    # STEP_ENTRY
    point_counter[0] += 1
    pid = f"{file_id}:{point_counter[0]}"
    block.coverage_points.append(CoveragePoint(
        point_id=pid,
        point_type=CoveragePointType.STEP_ENTRY,
        line_number=start_line,
        description="PROC SQL entry",
    ))

    # WHERE clauses
    for where_match in _SQL_WHERE_RE.finditer(body):
        condition = where_match.group(1).strip()
        line_num = _line_number_at(code, match.start() + where_match.start())
        point_counter[0] += 1
        pid = f"{file_id}:{point_counter[0]}"
        block.coverage_points.append(CoveragePoint(
            point_id=pid,
            point_type=CoveragePointType.SQL_WHERE,
            line_number=line_num,
            description=f"SQL WHERE: {condition[:60]}",
            condition=condition,
        ))
        block.variables.extend(_extract_variables_from_condition(condition, line_num))

    # CASE/WHEN/ELSE
    for case_match in _SQL_CASE_RE.finditer(body):
        case_body = case_match.group(1)
        case_start = match.start() + case_match.start()

        for when_match in _SQL_WHEN_RE.finditer(case_body):
            condition = when_match.group(1).strip()
            line_num = _line_number_at(code, case_start + when_match.start())
            point_counter[0] += 1
            pid = f"{file_id}:{point_counter[0]}"
            block.coverage_points.append(CoveragePoint(
                point_id=pid,
                point_type=CoveragePointType.SQL_CASE_WHEN,
                line_number=line_num,
                description=f"CASE WHEN: {condition[:60]}",
                condition=condition,
            ))
            block.variables.extend(_extract_variables_from_condition(condition, line_num))

        if _SQL_ELSE_RE.search(case_body):
            el_match = _SQL_ELSE_RE.search(case_body)
            line_num = _line_number_at(code, case_start + el_match.start())
            point_counter[0] += 1
            pid = f"{file_id}:{point_counter[0]}"
            block.coverage_points.append(CoveragePoint(
                point_id=pid,
                point_type=CoveragePointType.SQL_CASE_ELSE,
                line_number=line_num,
                description="CASE ELSE branch",
            ))

    # Output tables from CREATE TABLE
    for ct_match in re.finditer(r"(?i)\bCREATE\s+TABLE\s+([\w.]+)", body):
        block.output_datasets.append(ct_match.group(1).lower())

    # Input tables from FROM
    for from_match in re.finditer(r"(?i)\bFROM\s+([\w.]+)", body):
        table = from_match.group(1).lower()
        if table not in _SAS_KEYWORDS:
            block.input_datasets.append(table)

    return block


def parse_sas_file(file_path: str | Path) -> ParseResult:
    """Parse a SAS file and return all blocks, coverage points, and variables."""
    file_path = Path(file_path)
    logger.info("Parsing SAS file: %s", file_path)

    result = ParseResult(file_path=str(file_path))

    try:
        raw_code = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        result.errors.append(f"Cannot read file: {exc}")
        return result

    code = _strip_comments(raw_code)
    file_id = file_path.stem[:20]  # Short ID for coverage points
    point_counter = [0]  # Mutable counter shared across parsers

    # Parse DATA steps
    for match in _DATA_STEP_RE.finditer(code):
        try:
            block = _parse_data_step(match, code, point_counter, file_id)
            result.blocks.append(block)
        except Exception as exc:
            line = _line_number_at(code, match.start())
            result.errors.append(f"Error parsing DATA step at line {line}: {exc}")
            logger.warning("Parse error at line %d: %s", line, exc)

    # Parse PROC SQL
    for match in _PROC_SQL_RE.finditer(code):
        try:
            block = _parse_proc_sql(match, code, point_counter, file_id)
            result.blocks.append(block)
        except Exception as exc:
            line = _line_number_at(code, match.start())
            result.errors.append(f"Error parsing PROC SQL at line {line}: {exc}")
            logger.warning("Parse error at line %d: %s", line, exc)

    # Collect all points and variables
    for block in result.blocks:
        result.all_coverage_points.extend(block.coverage_points)
        result.all_variables.extend(block.variables)

    # Deduplicate variables by name
    seen_vars: dict[str, VariableRef] = {}
    for var in result.all_variables:
        key = var.name.lower()
        if key not in seen_vars or (
            seen_vars[key].inferred_type == "unknown"
            and var.inferred_type != "unknown"
        ):
            seen_vars[key] = var
    result.all_variables = list(seen_vars.values())

    logger.info(
        "Parsed %s: %d blocks, %d coverage points, %d variables",
        file_path.name,
        len(result.blocks),
        len(result.all_coverage_points),
        len(result.all_variables),
    )

    return result


def parse_sas_code(code: str, file_id: str = "inline") -> ParseResult:
    """Parse SAS code from a string (useful for testing)."""
    from tempfile import NamedTemporaryFile

    with NamedTemporaryFile(mode="w", suffix=".sas", delete=False, encoding="utf-8") as f:
        f.write(code)
        f.flush()
        return parse_sas_file(f.name)
