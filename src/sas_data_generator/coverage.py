"""Coverage tracking — parse coverage markers from SAS log and compute statistics."""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from .sas_parser import CoveragePoint, CoveragePointType

logger = logging.getLogger(__name__)

_COV_MARKER_RE = re.compile(r"COV:POINT=([\w:]+)")
_COV_COMPLETE_RE = re.compile(r"COV:COMPLETE")


@dataclass
class CoverageReport:
    """Coverage report for a single run or accumulated across runs."""
    total_points: int = 0
    hit_points: int = 0
    hit_point_ids: set[str] = field(default_factory=set)
    missed_point_ids: set[str] = field(default_factory=set)
    points_detail: dict[str, CoveragePoint] = field(default_factory=dict)
    is_complete: bool = False  # Whether SAS ran to completion

    @property
    def coverage_pct(self) -> float:
        if self.total_points == 0:
            return 0.0
        return (self.hit_points / self.total_points) * 100.0

    @property
    def missed_points(self) -> list[CoveragePoint]:
        return [
            self.points_detail[pid]
            for pid in self.missed_point_ids
            if pid in self.points_detail
        ]

    def summary(self) -> str:
        lines = [
            f"Coverage: {self.hit_points}/{self.total_points} "
            f"({self.coverage_pct:.1f}%)",
            f"  Hit:    {sorted(self.hit_point_ids)}",
            f"  Missed: {sorted(self.missed_point_ids)}",
        ]
        if not self.is_complete:
            lines.append("  WARNING: SAS did not run to completion (COV:COMPLETE not found)")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize to a dictionary for JSON export."""
        return {
            "total_points": self.total_points,
            "hit_points": self.hit_points,
            "coverage_pct": round(self.coverage_pct, 2),
            "is_complete": self.is_complete,
            "hit_point_ids": sorted(self.hit_point_ids),
            "missed_point_ids": sorted(self.missed_point_ids),
            "missed_details": [
                {
                    "point_id": cp.point_id,
                    "type": cp.point_type.name,
                    "line": cp.line_number,
                    "description": cp.description,
                    "condition": cp.condition,
                }
                for cp in self.missed_points
            ],
        }


def parse_coverage_from_log(
    log_text: str,
    expected_points: list[CoveragePoint],
) -> CoverageReport:
    """Parse coverage markers from SAS log output.

    Args:
        log_text: The full SAS log text.
        expected_points: List of all coverage points we instrumented.

    Returns:
        CoverageReport with hit/miss information.
    """
    all_ids = {cp.point_id for cp in expected_points}
    detail = {cp.point_id: cp for cp in expected_points}

    hit_ids: set[str] = set()
    for match in _COV_MARKER_RE.finditer(log_text):
        point_id = match.group(1)
        if point_id in all_ids:
            hit_ids.add(point_id)
        else:
            logger.warning("Unknown coverage point in log: %s", point_id)

    is_complete = bool(_COV_COMPLETE_RE.search(log_text))

    missed_ids = all_ids - hit_ids

    report = CoverageReport(
        total_points=len(all_ids),
        hit_points=len(hit_ids),
        hit_point_ids=hit_ids,
        missed_point_ids=missed_ids,
        points_detail=detail,
        is_complete=is_complete,
    )

    logger.info("Coverage: %d/%d (%.1f%%)", report.hit_points, report.total_points, report.coverage_pct)
    return report


def parse_coverage_from_csv(
    csv_path: str | Path,
    expected_points: list[CoveragePoint],
) -> CoverageReport:
    """Parse coverage from the exported coverage CSV dataset.

    This is the secondary mechanism. The CSV is written by the postamble
    PROC EXPORT of the _cov_tracker dataset.
    """
    csv_path = Path(csv_path)
    all_ids = {cp.point_id for cp in expected_points}
    detail = {cp.point_id: cp for cp in expected_points}

    hit_ids: set[str] = set()

    if csv_path.exists():
        try:
            with csv_path.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    point_id = row.get("point_id", "").strip()
                    if point_id in all_ids:
                        hit_ids.add(point_id)
        except Exception as exc:
            logger.warning("Failed to read coverage CSV %s: %s", csv_path, exc)
    else:
        logger.warning("Coverage CSV not found: %s", csv_path)

    missed_ids = all_ids - hit_ids

    return CoverageReport(
        total_points=len(all_ids),
        hit_points=len(hit_ids),
        hit_point_ids=hit_ids,
        missed_point_ids=missed_ids,
        points_detail=detail,
        is_complete=True,  # If CSV exists, SAS completed
    )


def merge_coverage_reports(*reports: CoverageReport) -> CoverageReport:
    """Merge multiple coverage reports (from multiple runs).

    A point is considered covered if ANY run hit it.
    """
    if not reports:
        return CoverageReport()

    # Use the first report's point detail as the base
    all_detail = {}
    all_ids: set[str] = set()
    all_hits: set[str] = set()

    for report in reports:
        all_detail.update(report.points_detail)
        all_ids.update(report.hit_point_ids | report.missed_point_ids)
        all_hits.update(report.hit_point_ids)

    missed = all_ids - all_hits

    return CoverageReport(
        total_points=len(all_ids),
        hit_points=len(all_hits),
        hit_point_ids=all_hits,
        missed_point_ids=missed,
        points_detail=all_detail,
        is_complete=any(r.is_complete for r in reports),
    )


def export_coverage_report(
    report: CoverageReport,
    output_path: str | Path,
    format: str = "json",
) -> None:
    """Export coverage report to file."""
    import json

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if format == "json":
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)
        logger.info("Coverage report written to %s", output_path)
    elif format == "text":
        with output_path.open("w", encoding="utf-8") as f:
            f.write(report.summary())
            f.write("\n\nMissed Points Detail:\n")
            for cp in report.missed_points:
                f.write(f"  [{cp.point_id}] {cp.point_type.name} line {cp.line_number}: "
                        f"{cp.description}\n")
                if cp.condition:
                    f.write(f"    Condition: {cp.condition}\n")
        logger.info("Coverage report written to %s", output_path)
    else:
        raise ValueError(f"Unknown format: {format}")
