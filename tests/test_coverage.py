"""Tests for the coverage module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from sas_data_generator.coverage import (
    CoverageReport,
    export_coverage_report,
    merge_coverage_reports,
    parse_coverage_from_csv,
    parse_coverage_from_log,
)
from sas_data_generator.sas_parser import CoveragePoint, CoveragePointType


@pytest.fixture
def sample_points() -> list[CoveragePoint]:
    return [
        CoveragePoint("f:1", CoveragePointType.STEP_ENTRY, 1, "DATA step entry"),
        CoveragePoint("f:2", CoveragePointType.IF_TRUE, 3, "IF true: age > 65", "age > 65"),
        CoveragePoint("f:3", CoveragePointType.IF_FALSE, 3, "IF false: age > 65", "age > 65"),
        CoveragePoint("f:4", CoveragePointType.SELECT_WHEN, 8, "WHEN: score >= 80", "score >= 80"),
        CoveragePoint("f:5", CoveragePointType.SELECT_OTHERWISE, 10, "OTHERWISE"),
    ]


class TestParseFromLog:
    def test_all_hit(self, sample_points):
        log = (
            "NOTE: some log line\n"
            "COV:POINT=f:1\n"
            "COV:POINT=f:2\n"
            "COV:POINT=f:3\n"
            "COV:POINT=f:4\n"
            "COV:POINT=f:5\n"
            "COV:COMPLETE\n"
        )
        report = parse_coverage_from_log(log, sample_points)
        assert report.coverage_pct == 100.0
        assert report.is_complete
        assert len(report.missed_point_ids) == 0

    def test_partial_hit(self, sample_points):
        log = "COV:POINT=f:1\nCOV:POINT=f:2\nCOV:COMPLETE\n"
        report = parse_coverage_from_log(log, sample_points)
        assert report.hit_points == 2
        assert report.total_points == 5
        assert report.coverage_pct == 40.0
        assert "f:3" in report.missed_point_ids
        assert "f:4" in report.missed_point_ids
        assert "f:5" in report.missed_point_ids

    def test_no_hits(self, sample_points):
        log = "NOTE: SAS ran but no branches hit\nCOV:COMPLETE\n"
        report = parse_coverage_from_log(log, sample_points)
        assert report.hit_points == 0
        assert report.coverage_pct == 0.0

    def test_incomplete_run(self, sample_points):
        log = "COV:POINT=f:1\nERROR: Something failed\n"
        report = parse_coverage_from_log(log, sample_points)
        assert not report.is_complete

    def test_duplicate_markers_counted_once(self, sample_points):
        log = "COV:POINT=f:1\nCOV:POINT=f:1\nCOV:POINT=f:1\nCOV:COMPLETE\n"
        report = parse_coverage_from_log(log, sample_points)
        assert report.hit_points == 1

    def test_empty_log(self, sample_points):
        report = parse_coverage_from_log("", sample_points)
        assert report.hit_points == 0
        assert not report.is_complete

    def test_no_expected_points(self):
        report = parse_coverage_from_log("COV:POINT=f:1\n", [])
        assert report.total_points == 0
        assert report.coverage_pct == 0.0


class TestMergeReports:
    def test_merge_two_runs(self, sample_points):
        log1 = "COV:POINT=f:1\nCOV:POINT=f:2\nCOV:COMPLETE\n"
        log2 = "COV:POINT=f:1\nCOV:POINT=f:3\nCOV:POINT=f:4\nCOV:COMPLETE\n"
        r1 = parse_coverage_from_log(log1, sample_points)
        r2 = parse_coverage_from_log(log2, sample_points)

        merged = merge_coverage_reports(r1, r2)
        assert merged.hit_points == 4  # f:1, f:2, f:3, f:4
        assert merged.coverage_pct == 80.0
        assert "f:5" in merged.missed_point_ids

    def test_merge_reaches_100(self, sample_points):
        log1 = "COV:POINT=f:1\nCOV:POINT=f:2\nCOV:POINT=f:4\nCOV:COMPLETE\n"
        log2 = "COV:POINT=f:3\nCOV:POINT=f:5\nCOV:COMPLETE\n"
        r1 = parse_coverage_from_log(log1, sample_points)
        r2 = parse_coverage_from_log(log2, sample_points)

        merged = merge_coverage_reports(r1, r2)
        assert merged.coverage_pct == 100.0

    def test_merge_empty(self):
        merged = merge_coverage_reports()
        assert merged.total_points == 0


class TestExportReport:
    def test_export_json(self, sample_points):
        log = "COV:POINT=f:1\nCOV:POINT=f:2\nCOV:COMPLETE\n"
        report = parse_coverage_from_log(log, sample_points)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            export_coverage_report(report, f.name, format="json")
            data = json.loads(Path(f.name).read_text())

        assert data["total_points"] == 5
        assert data["hit_points"] == 2
        assert data["coverage_pct"] == 40.0
        assert len(data["missed_details"]) == 3

    def test_export_text(self, sample_points):
        log = "COV:POINT=f:1\nCOV:COMPLETE\n"
        report = parse_coverage_from_log(log, sample_points)

        with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
            export_coverage_report(report, f.name, format="text")
            text = Path(f.name).read_text()

        assert "Coverage:" in text
        assert "20.0%" in text


class TestCoverageReportDict:
    def test_to_dict(self, sample_points):
        log = "COV:POINT=f:1\nCOV:POINT=f:2\nCOV:COMPLETE\n"
        report = parse_coverage_from_log(log, sample_points)
        d = report.to_dict()

        assert d["total_points"] == 5
        assert d["hit_points"] == 2
        assert isinstance(d["hit_point_ids"], list)
        assert isinstance(d["missed_point_ids"], list)
        assert isinstance(d["missed_details"], list)
