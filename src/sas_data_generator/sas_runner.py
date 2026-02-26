"""SAS batch runner — execute SAS programs and capture log output.

Assumes:
- `sas` executable is available on PATH (or configured via SAS_HOME env var)
- SAS can run in batch/headless mode: sas -batch -noterminal <file.sas>
- On Linux CI runners, SAS is typically at /usr/local/SASHome/SASFoundation/9.4/sas
  or configured via module load / PATH

The runner:
1. Writes the instrumented SAS code to a temp file
2. Executes SAS in batch mode
3. Captures the log file content
4. Returns log + return code
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Default SAS executable — can be overridden via SAS_EXECUTABLE env var
_DEFAULT_SAS_PATHS = [
    "sas",  # On PATH
    "/usr/local/SASHome/SASFoundation/9.4/sas",
    "/opt/sas/sas",
    "/usr/local/bin/sas",
]


@dataclass
class SASRunResult:
    """Result of running a SAS program."""
    return_code: int
    log_text: str
    log_path: str
    lst_text: str  # SAS listing output
    work_dir: str
    sas_errors: list[str]
    sas_warnings: list[str]
    duration_seconds: float


def find_sas_executable() -> str | None:
    """Find the SAS executable on this system."""
    # Check environment variable first
    env_sas = os.environ.get("SAS_EXECUTABLE")
    if env_sas and Path(env_sas).exists():
        return env_sas

    # Check common locations
    for path in _DEFAULT_SAS_PATHS:
        found = shutil.which(path)
        if found:
            return found

    return None


def _extract_errors_warnings(log_text: str) -> tuple[list[str], list[str]]:
    """Extract ERROR and WARNING lines from SAS log."""
    errors = []
    warnings = []
    for line in log_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("ERROR"):
            errors.append(stripped)
        elif stripped.startswith("WARNING"):
            warnings.append(stripped)
    return errors, warnings


def run_sas(
    sas_code: str,
    work_dir: str | Path | None = None,
    sas_executable: str | None = None,
    timeout_seconds: int = 300,
    extra_sas_options: list[str] | None = None,
    autoexec_path: str | Path | None = None,
    macro_vars: dict[str, str] | None = None,
    libname_map: dict[str, str] | None = None,
) -> SASRunResult:
    """Run a SAS program in batch mode and return the results.

    Args:
        sas_code: The SAS code to execute.
        work_dir: Working directory for SAS. If None, a temp dir is created.
        sas_executable: Path to SAS executable. Auto-detected if None.
        timeout_seconds: Maximum execution time.
        extra_sas_options: Additional command-line options for SAS.
        autoexec_path: Path to autoexec.sas file.
        macro_vars: Macro variable definitions to inject (name -> value).
        libname_map: Library name mappings (libref -> path).

    Returns:
        SASRunResult with log, return code, etc.
    """
    import time

    if sas_executable is None:
        sas_executable = find_sas_executable()
    if sas_executable is None:
        raise FileNotFoundError(
            "SAS executable not found. Set SAS_EXECUTABLE environment variable "
            "or ensure 'sas' is on PATH."
        )

    # Set up working directory
    cleanup_work_dir = False
    if work_dir is None:
        work_dir = tempfile.mkdtemp(prefix="sas_datagen_")
        cleanup_work_dir = True
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Prepend macro variables and libname statements
    preamble_parts = []

    if libname_map:
        for libref, lib_path in libname_map.items():
            lib_path_resolved = Path(lib_path).resolve()
            lib_path_resolved.mkdir(parents=True, exist_ok=True)
            preamble_parts.append(f'libname {libref} "{lib_path_resolved}";')

    if macro_vars:
        for name, value in macro_vars.items():
            preamble_parts.append(f"%let {name} = {value};")

    if preamble_parts:
        sas_code = "\n".join(preamble_parts) + "\n\n" + sas_code

    # Write SAS code to temp file
    sas_file = work_dir / "_sas_datagen_run.sas"
    sas_file.write_text(sas_code, encoding="utf-8")

    log_file = work_dir / "_sas_datagen_run.log"
    lst_file = work_dir / "_sas_datagen_run.lst"

    # Build command
    cmd = [
        sas_executable,
        "-batch",
        "-noterminal",
        "-nologo",
        f"-log", str(log_file),
        f"-print", str(lst_file),
        f"-work", str(work_dir),
    ]

    if autoexec_path:
        cmd.extend(["-autoexec", str(autoexec_path)])

    if extra_sas_options:
        cmd.extend(extra_sas_options)

    cmd.append(str(sas_file))

    logger.info("Running SAS: %s", " ".join(cmd))
    start_time = time.monotonic()

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(work_dir),
        )
        return_code = proc.returncode
    except subprocess.TimeoutExpired:
        logger.error("SAS execution timed out after %d seconds", timeout_seconds)
        return_code = -1
    except FileNotFoundError:
        logger.error("SAS executable not found: %s", sas_executable)
        raise

    duration = time.monotonic() - start_time

    # Read log
    log_text = ""
    if log_file.exists():
        log_text = log_file.read_text(encoding="utf-8", errors="replace")
    else:
        logger.warning("SAS log file not found: %s", log_file)

    # Read listing
    lst_text = ""
    if lst_file.exists():
        lst_text = lst_file.read_text(encoding="utf-8", errors="replace")

    errors, warnings = _extract_errors_warnings(log_text)

    if errors:
        logger.warning("SAS errors found: %d", len(errors))
        for err in errors[:5]:
            logger.warning("  %s", err)

    result = SASRunResult(
        return_code=return_code,
        log_text=log_text,
        log_path=str(log_file),
        lst_text=lst_text,
        work_dir=str(work_dir),
        sas_errors=errors,
        sas_warnings=warnings,
        duration_seconds=duration,
    )

    logger.info(
        "SAS completed: rc=%d, duration=%.1fs, errors=%d, warnings=%d",
        return_code, duration, len(errors), len(warnings),
    )

    return result


def run_sas_dry(
    sas_code: str,
    work_dir: str | Path | None = None,
) -> SASRunResult:
    """Dry-run mode: write SAS code to file but don't execute.

    Useful for testing instrumentation without a SAS installation.
    Returns a synthetic result.
    """
    if work_dir is None:
        work_dir = tempfile.mkdtemp(prefix="sas_datagen_dry_")
    work_dir = Path(work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)

    sas_file = work_dir / "_sas_datagen_run.sas"
    sas_file.write_text(sas_code, encoding="utf-8")

    logger.info("Dry run: SAS code written to %s", sas_file)

    return SASRunResult(
        return_code=0,
        log_text="/* DRY RUN — no SAS execution */\nCOV:COMPLETE",
        log_path="",
        lst_text="",
        work_dir=str(work_dir),
        sas_errors=[],
        sas_warnings=[],
        duration_seconds=0.0,
    )
