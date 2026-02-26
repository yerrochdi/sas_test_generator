"""Tests for the dataset generator module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sas_data_generator.dataset_generator import (
    GeneratedDataset,
    _extract_string_values,
    _extract_threshold_values,
    _value_to_satisfy,
    _value_to_violate,
    export_dataset,
    generate_seed_datasets,
    mutate_datasets,
)
from sas_data_generator.coverage import CoverageReport, parse_coverage_from_log
from sas_data_generator.sas_parser import (
    CoveragePoint,
    CoveragePointType,
    ParseResult,
    parse_sas_code,
)


class TestThresholdExtraction:
    def test_greater_than(self):
        values = _extract_threshold_values("age > 65")
        assert 64 in values
        assert 65 in values
        assert 66 in values

    def test_greater_equal(self):
        values = _extract_threshold_values("score >= 80")
        assert 79 in values
        assert 80 in values
        assert 81 in values

    def test_less_than(self):
        values = _extract_threshold_values("age < 25")
        assert 24 in values
        assert 25 in values
        assert 26 in values

    def test_equals(self):
        values = _extract_threshold_values("status = 1")
        assert 0 in values
        assert 1 in values
        assert 2 in values

    def test_multiple_conditions(self):
        values = _extract_threshold_values("age >= 25 and age < 45")
        assert 24 in values
        assert 25 in values
        assert 44 in values
        assert 45 in values

    def test_in_list(self):
        values = _extract_threshold_values("x in (100, 200, 300)")
        assert 100 in values
        assert 200 in values
        assert 300 in values


class TestStringExtraction:
    def test_double_quoted(self):
        values = _extract_string_values('status = "ACTIVE"')
        assert "ACTIVE" in values

    def test_single_quoted(self):
        values = _extract_string_values("type = 'A'")
        assert "A" in values

    def test_includes_empty(self):
        values = _extract_string_values('x = "YES"')
        assert "" in values  # Edge case value


class TestValueSatisfyViolate:
    def test_satisfy_gt(self):
        assert _value_to_satisfy(">", 10) > 10

    def test_satisfy_ge(self):
        assert _value_to_satisfy(">=", 10) >= 10

    def test_satisfy_lt(self):
        assert _value_to_satisfy("<", 10) < 10

    def test_satisfy_eq(self):
        assert _value_to_satisfy("=", 10) == 10

    def test_violate_gt(self):
        assert _value_to_violate(">", 10) <= 10

    def test_violate_ge(self):
        assert _value_to_violate(">=", 10) < 10

    def test_violate_lt(self):
        assert _value_to_violate("<", 10) >= 10

    def test_violate_eq(self):
        assert _value_to_violate("=", 10) != 10


class TestGenerateSeedDatasets:
    def test_basic_generation(self):
        code = """\
data output;
    set customers;
    if age > 65 then status = "SENIOR";
    else status = "OTHER";
run;
"""
        parse_result = parse_sas_code(code)
        datasets = generate_seed_datasets(parse_result, num_rows=20, seed=42)

        assert len(datasets) >= 1
        ds = datasets[0]
        assert len(ds.df) == 20
        assert "age" in [c.lower() for c in ds.df.columns]

    def test_deterministic_with_seed(self):
        code = "data a; set b; if x > 10 then y = 1; run;"
        parse_result = parse_sas_code(code)

        ds1 = generate_seed_datasets(parse_result, seed=123)
        ds2 = generate_seed_datasets(parse_result, seed=123)

        pd.testing.assert_frame_equal(ds1[0].df, ds2[0].df)

    def test_different_seeds_differ(self):
        code = "data a; set b; if x > 10 then y = 1; run;"
        parse_result = parse_sas_code(code)

        ds1 = generate_seed_datasets(parse_result, seed=1)
        ds2 = generate_seed_datasets(parse_result, seed=2)

        # DataFrames should not be identical
        assert not ds1[0].df.equals(ds2[0].df)

    def test_boundary_values_included(self):
        code = """\
data output;
    set input;
    if score >= 80 then grade = "A";
    else if score >= 60 then grade = "B";
    else grade = "F";
run;
"""
        parse_result = parse_sas_code(code)
        datasets = generate_seed_datasets(parse_result, num_rows=30, seed=42)

        ds = datasets[0]
        scores = ds.df["score"].dropna()
        # Should include values around 80 and 60 boundaries
        assert any(s >= 80 for s in scores)
        assert any(s < 60 for s in scores)

    def test_empty_code(self):
        parse_result = parse_sas_code("")
        datasets = generate_seed_datasets(parse_result)
        # No input datasets detected, so either empty list or dataset with no vars
        assert len(datasets) == 0 or len(datasets[0].df.columns) == 0


class TestMutateDatasets:
    def test_mutation_adds_rows(self):
        code = """\
data output;
    set input;
    if age > 65 then x = 1;
    else x = 0;
run;
"""
        parse_result = parse_sas_code(code)
        datasets = generate_seed_datasets(parse_result, num_rows=10, seed=42)

        # Simulate partial coverage (only IF_TRUE hit)
        points = parse_result.all_coverage_points
        hit_ids = {cp.point_id for cp in points if cp.point_type == CoveragePointType.STEP_ENTRY}
        report = CoverageReport(
            total_points=len(points),
            hit_points=len(hit_ids),
            hit_point_ids=hit_ids,
            missed_point_ids={cp.point_id for cp in points if cp.point_id not in hit_ids},
            points_detail={cp.point_id: cp for cp in points},
            is_complete=True,
        )

        mutated = mutate_datasets(datasets, report, parse_result, seed=42)
        assert len(mutated[0].df) > len(datasets[0].df)


class TestExportDataset:
    def test_csv_export(self):
        df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
        ds = GeneratedDataset(name="test", df=df)

        with tempfile.TemporaryDirectory() as tmpdir:
            paths = export_dataset(ds, tmpdir, formats=["csv"])
            assert len(paths) == 1
            assert paths[0].endswith(".csv")

            loaded = pd.read_csv(paths[0])
            assert len(loaded) == 3
            assert list(loaded.columns) == ["a", "b"]
