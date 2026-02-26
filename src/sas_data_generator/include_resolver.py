"""Resolve %INCLUDE directives and collect macro definitions from a SAS project.

Given an entry-point SAS file (e.g., main.sas) and a list of search
directories, this module:

1. Reads the entry file
2. Finds all %INCLUDE / %INC directives
3. Recursively inlines the included files
4. Returns one big resolved SAS source with all code visible

It also supports scanning a whole project directory to discover all .sas
files and build a dependency graph.

Handles these common patterns:
    %include "path/to/file.sas";
    %include 'path/to/file.sas';
    %include path_no_quotes;
    %inc "file.sas";
    %include "&macro_var./file.sas";   (partial — expands known macros)
    %include "/absolute/path/file.sas";
    %include "./relative/path/file.sas";

Limitations:
    - Macro variables in paths are only resolved if provided in macro_vars dict
    - Does not handle fileref-based includes: %include myfileref;
      (unless the fileref happens to match a filename)
    - Does not handle %INCLUDE with multiple files on one line:
      %include "a.sas" "b.sas"; (rare but valid in SAS)
    - Circular includes are detected and reported as errors
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Match %INCLUDE or %INC with quoted or unquoted path
_INCLUDE_RE = re.compile(
    r"""(?ix)
    %\s*inc(?:lude)?\s+      # %include or %inc
    (?:
        "([^"]+)"            # double-quoted path  (group 1)
        |'([^']+)'           # single-quoted path  (group 2)
        |(\S+?)              # unquoted path        (group 3)
    )
    \s*;                     # trailing semicolon
    """,
)

# Match macro variable references in paths: &varname. or &varname
_MACRO_VAR_RE = re.compile(r"&(\w+)\.?")


@dataclass
class ResolvedSource:
    """Result of resolving includes for a SAS project."""
    resolved_code: str
    entry_file: str
    included_files: list[str] = field(default_factory=list)
    all_sas_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Map from line ranges in resolved_code back to original files
    source_map: list[tuple[int, int, str]] = field(default_factory=list)
    # (start_line, end_line, original_file_path)


def _expand_macro_vars(path_str: str, macro_vars: dict[str, str]) -> str:
    """Expand &macro_var references in an include path."""
    def _replacer(m: re.Match) -> str:
        var_name = m.group(1).lower()
        for key, value in macro_vars.items():
            if key.lower() == var_name:
                return value
        # Unknown macro var — leave as-is but warn
        logger.warning("Unresolved macro variable in include path: &%s", m.group(1))
        return m.group(0)

    return _MACRO_VAR_RE.sub(_replacer, path_str)


def _find_include_file(
    include_path: str,
    current_file_dir: Path,
    search_dirs: list[Path],
) -> Path | None:
    """Find an included file by searching multiple directories.

    Search order:
    1. Absolute path (if the include path is absolute)
    2. Relative to the current file's directory
    3. Each directory in search_dirs, in order
    """
    include_p = Path(include_path)

    # 1. Absolute path
    if include_p.is_absolute() and include_p.exists():
        return include_p

    # 2. Relative to current file
    candidate = current_file_dir / include_p
    if candidate.exists():
        return candidate.resolve()

    # 3. Search directories
    for search_dir in search_dirs:
        candidate = search_dir / include_p
        if candidate.exists():
            return candidate.resolve()

        # Also try just the filename (common: %include "macro_risque.sas"
        # when the file is in a macros/ subfolder)
        candidate = search_dir / include_p.name
        if candidate.exists():
            return candidate.resolve()

    return None


def resolve_includes(
    entry_file: str | Path,
    search_dirs: list[str | Path] | None = None,
    macro_vars: dict[str, str] | None = None,
    max_depth: int = 20,
) -> ResolvedSource:
    """Resolve all %INCLUDE directives starting from an entry file.

    Args:
        entry_file: The main SAS program file.
        search_dirs: Directories to search for included files.
            The entry file's directory and its parent are always searched.
        macro_vars: Macro variable definitions for expanding paths
            like "&chemin./file.sas".
        max_depth: Maximum include nesting depth (protection against loops).

    Returns:
        ResolvedSource with fully inlined code.
    """
    entry_file = Path(entry_file).resolve()
    macro_vars = macro_vars or {}

    # Build search path list
    resolved_search_dirs: list[Path] = []
    # Always search in the entry file's directory and parent
    resolved_search_dirs.append(entry_file.parent)
    if entry_file.parent.parent != entry_file.parent:
        resolved_search_dirs.append(entry_file.parent.parent)
    # Add all subdirectories of the entry file's parent (common pattern)
    for subdir in entry_file.parent.parent.iterdir():
        if subdir.is_dir() and subdir not in resolved_search_dirs:
            resolved_search_dirs.append(subdir)

    if search_dirs:
        for sd in search_dirs:
            p = Path(sd).resolve()
            if p.is_dir() and p not in resolved_search_dirs:
                resolved_search_dirs.append(p)

    logger.info("Include search dirs: %s", [str(d) for d in resolved_search_dirs])

    result = ResolvedSource(
        resolved_code="",
        entry_file=str(entry_file),
    )

    visited: set[str] = set()  # Tracks files already included (circular ref protection)
    output_lines: list[str] = []
    current_line = 1

    def _resolve_file(file_path: Path, depth: int) -> None:
        nonlocal current_line

        file_key = str(file_path.resolve())
        if file_key in visited:
            msg = f"Circular include detected: {file_path}"
            result.errors.append(msg)
            logger.warning(msg)
            output_lines.append(f"/* SKIPPED — circular include: {file_path.name} */")
            current_line += 1
            return

        if depth > max_depth:
            msg = f"Max include depth ({max_depth}) exceeded at: {file_path}"
            result.errors.append(msg)
            logger.warning(msg)
            return

        visited.add(file_key)
        result.included_files.append(str(file_path))

        try:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            msg = f"Cannot read included file {file_path}: {exc}"
            result.errors.append(msg)
            logger.warning(msg)
            return

        # Add source map marker
        output_lines.append(f"/* === BEGIN INCLUDE: {file_path.name} ({file_path}) === */")
        start_line = current_line + 1
        current_line += 1

        # Process line by line, looking for %INCLUDE directives
        for line in raw.splitlines():
            include_match = _INCLUDE_RE.search(line)

            if include_match:
                # Extract the path from whichever group matched
                inc_path = (
                    include_match.group(1)
                    or include_match.group(2)
                    or include_match.group(3)
                )

                if not inc_path:
                    output_lines.append(line)
                    current_line += 1
                    continue

                # Expand macro variables in path
                inc_path = _expand_macro_vars(inc_path, macro_vars)

                # Find the actual file
                found = _find_include_file(
                    inc_path,
                    file_path.parent,
                    resolved_search_dirs,
                )

                if found:
                    output_lines.append(f"/* %INCLUDE resolved: {inc_path} -> {found} */")
                    current_line += 1
                    _resolve_file(found, depth + 1)
                else:
                    msg = f"Include file not found: {inc_path} (referenced in {file_path.name})"
                    result.errors.append(msg)
                    logger.warning(msg)
                    output_lines.append(f"/* WARNING: include not found: {inc_path} */")
                    output_lines.append(line)  # Keep original line as comment
                    current_line += 2
            else:
                output_lines.append(line)
                current_line += 1

        # Source map entry
        result.source_map.append((start_line, current_line, str(file_path)))

        output_lines.append(f"/* === END INCLUDE: {file_path.name} === */")
        current_line += 1

    # Start resolution from entry file
    _resolve_file(entry_file, depth=0)

    result.resolved_code = "\n".join(output_lines)
    result.all_sas_files = list(visited)

    logger.info(
        "Resolved %s: %d files included, %d errors, %d total lines",
        entry_file.name,
        len(result.included_files),
        len(result.errors),
        current_line,
    )

    return result


def scan_project_directory(
    project_dir: str | Path,
    entry_file: str | None = None,
) -> list[Path]:
    """Scan a project directory and return all .sas files.

    If entry_file is specified, it's returned first (as the main file).
    Otherwise, tries to detect the entry point by looking for common names:
    main.sas, autoexec.sas, run_all.sas, etc.

    Args:
        project_dir: Root directory of the SAS project.
        entry_file: Explicit entry point file name (optional).

    Returns:
        List of .sas file paths, with the entry point first if detected.
    """
    project_dir = Path(project_dir).resolve()

    if not project_dir.is_dir():
        raise FileNotFoundError(f"Not a directory: {project_dir}")

    # Collect all .sas files recursively
    all_sas = sorted(project_dir.rglob("*.sas"))

    if not all_sas:
        logger.warning("No .sas files found in %s", project_dir)
        return []

    # Determine entry point
    entry: Path | None = None
    if entry_file:
        for f in all_sas:
            if f.name.lower() == entry_file.lower() or str(f).endswith(entry_file):
                entry = f
                break
        if entry is None:
            logger.warning("Entry file '%s' not found in %s", entry_file, project_dir)

    if entry is None:
        # Try common entry point names
        common_names = ["main.sas", "run_all.sas", "autoexec.sas", "master.sas", "run.sas"]
        for name in common_names:
            for f in all_sas:
                if f.name.lower() == name:
                    entry = f
                    logger.info("Auto-detected entry point: %s", entry)
                    break
            if entry:
                break

    # Reorder: entry first, then the rest
    if entry and entry in all_sas:
        all_sas.remove(entry)
        all_sas.insert(0, entry)

    logger.info(
        "Scanned %s: %d .sas files, entry=%s",
        project_dir, len(all_sas), entry or "none detected",
    )

    return all_sas
