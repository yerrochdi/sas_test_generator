"""Tests for the SAS instrumenter module."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from sas_data_generator.sas_instrumenter import instrument_sas_code, instrument_sas_file
from sas_data_generator.sas_parser import CoveragePointType

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


class TestInstrumentCode:
    def test_basic_instrumentation(self):
        code = textwrap.dedent("""\
            data output;
                set input;
                if age > 65 then status = "SENIOR";
                else status = "OTHER";
            run;
        """)
        result = instrument_sas_code(code)

        # Should have coverage points
        assert len(result.coverage_points) >= 3  # STEP_ENTRY + IF_TRUE + IF_FALSE

        # Should contain PUT statements for log markers
        assert "COV:POINT=" in result.instrumented_code

        # Should contain preamble and postamble
        assert "_cov_hit" in result.instrumented_code
        assert "_cov_tracker" in result.instrumented_code
        assert "COV:COMPLETE" in result.instrumented_code

    def test_original_code_preserved(self):
        code = textwrap.dedent("""\
            data output;
                set input;
                if age > 65 then status = "SENIOR";
                else status = "OTHER";
            run;
        """)
        result = instrument_sas_code(code)

        # Original statements should still be present
        assert 'status = "SENIOR"' in result.instrumented_code
        assert 'status = "OTHER"' in result.instrumented_code
        assert "set input;" in result.instrumented_code

    def test_select_when_instrumented(self):
        code = textwrap.dedent("""\
            data output;
                set input;
                select;
                    when (score >= 80) grade = "A";
                    when (score >= 60) grade = "B";
                    otherwise grade = "F";
                end;
            run;
        """)
        result = instrument_sas_code(code)

        # Should have markers for each WHEN + OTHERWISE
        point_types = {cp.point_type for cp in result.coverage_points}
        assert CoveragePointType.SELECT_WHEN in point_types
        assert CoveragePointType.SELECT_OTHERWISE in point_types

        # Count PUT statements (rough check)
        put_count = result.instrumented_code.count('put "COV:POINT=')
        assert put_count >= 4  # STEP_ENTRY + 2 WHEN + OTHERWISE

    def test_proc_sql_instrumented(self):
        code = textwrap.dedent("""\
            proc sql;
                create table summary as
                select name,
                    case
                        when score >= 80 then "HIGH"
                        else "LOW"
                    end as tier
                from students
                where age > 18;
            quit;
        """)
        result = instrument_sas_code(code)

        # PROC SQL uses %_cov_hit macro calls
        assert "%_cov_hit(" in result.instrumented_code

    def test_coverage_csv_path_in_postamble(self):
        result = instrument_sas_code(
            "data a; set b; run;",
            coverage_csv_path="/tmp/my_coverage.csv",
        )
        assert "/tmp/my_coverage.csv" in result.instrumented_code

    def test_multiple_data_steps(self):
        code = textwrap.dedent("""\
            data step1;
                set input;
                if x > 0 then y = 1;
            run;

            data step2;
                set step1;
                if y = 1 then z = "YES";
                else z = "NO";
            run;
        """)
        result = instrument_sas_code(code)

        # Should have coverage points from both DATA steps
        step_entries = [
            cp for cp in result.coverage_points
            if cp.point_type == CoveragePointType.STEP_ENTRY
        ]
        assert len(step_entries) == 2

    def test_empty_code(self):
        result = instrument_sas_code("")
        assert result.instrumented_code  # Should at least have preamble/postamble
        assert len(result.coverage_points) == 0


class TestInstrumentSampleFile:
    """Test instrumentation of the sample SAS program."""

    def test_sample_program(self):
        sample_path = EXAMPLES_DIR / "sample_program.sas"
        if not sample_path.exists():
            pytest.skip("Sample program not found")

        result = instrument_sas_file(sample_path)

        # Should have many coverage points
        assert len(result.coverage_points) >= 10

        # Instrumented code should be longer than original
        original = sample_path.read_text()
        assert len(result.instrumented_code) > len(original)

        # Original code structures should be preserved
        assert "risk_category" in result.instrumented_code
        assert "classified" in result.instrumented_code
        assert "summary" in result.instrumented_code

        # Coverage infrastructure should be present
        assert "_cov_tracker" in result.instrumented_code
        assert "COV:COMPLETE" in result.instrumented_code
