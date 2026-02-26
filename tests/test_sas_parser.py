"""Tests for the SAS parser module."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from sas_data_generator.sas_parser import (
    BlockType,
    CoveragePointType,
    ParseResult,
    _extract_variables_from_condition,
    _extract_variables_from_input,
    _strip_comments,
    parse_sas_code,
    parse_sas_file,
)

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


# ---------------------------------------------------------------------------
# Comment stripping
# ---------------------------------------------------------------------------

class TestStripComments:
    def test_block_comment(self):
        code = "data a; /* this is a comment */ set b; run;"
        result = _strip_comments(code)
        assert "this is a comment" not in result
        assert "data a;" in result
        assert "set b;" in result

    def test_multiline_block_comment(self):
        code = "data a;\n/* line1\nline2\nline3 */\nset b;\nrun;"
        result = _strip_comments(code)
        # Line count should be preserved
        assert result.count("\n") == code.count("\n")
        assert "line1" not in result

    def test_line_comment(self):
        code = "data a;\n* this is a comment;\nset b;\nrun;"
        result = _strip_comments(code)
        assert "this is a comment" not in result
        assert "set b;" in result

    def test_no_comments(self):
        code = "data a; set b; run;"
        result = _strip_comments(code)
        assert result.strip() == code.strip()


# ---------------------------------------------------------------------------
# Variable extraction from conditions
# ---------------------------------------------------------------------------

class TestVariableExtraction:
    def test_numeric_comparison(self):
        vars = _extract_variables_from_condition("age > 65", 1)
        assert len(vars) == 1
        assert vars[0].name == "age"
        assert vars[0].inferred_type == "numeric"

    def test_multiple_comparisons(self):
        vars = _extract_variables_from_condition("age >= 25 and income < 50000", 1)
        names = {v.name for v in vars}
        assert "age" in names
        assert "income" in names

    def test_skips_keywords(self):
        vars = _extract_variables_from_condition("if age > 10 then", 1)
        names = {v.name for v in vars}
        assert "if" not in names
        assert "then" not in names

    def test_sas_operators(self):
        vars = _extract_variables_from_condition("score ge 80", 1)
        assert len(vars) == 1
        assert vars[0].name == "score"


class TestInputParsing:
    def test_simple_input(self):
        vars = _extract_variables_from_input("name $ age salary", 1)
        names = {v.name for v in vars}
        assert "name" in names
        assert "age" in names
        assert "salary" in names

    def test_character_variable(self):
        vars = _extract_variables_from_input("name $ age", 1)
        name_var = next(v for v in vars if v.name == "name")
        assert name_var.inferred_type == "character"

    def test_formatted_input(self):
        vars = _extract_variables_from_input("dob date9. amount 8.2", 1)
        dob_var = next(v for v in vars if v.name == "dob")
        assert dob_var.inferred_type == "date"


# ---------------------------------------------------------------------------
# Full SAS parsing
# ---------------------------------------------------------------------------

class TestParseSASCode:
    def test_simple_data_step(self):
        code = textwrap.dedent("""\
            data output;
                set input;
                if age > 65 then status = "SENIOR";
                else status = "OTHER";
            run;
        """)
        result = parse_sas_code(code)
        assert len(result.blocks) == 1
        assert result.blocks[0].block_type == BlockType.DATA_STEP
        assert result.blocks[0].name == "output"

    def test_data_step_coverage_points(self):
        code = textwrap.dedent("""\
            data output;
                set input;
                if age > 65 then status = "SENIOR";
                else status = "OTHER";
            run;
        """)
        result = parse_sas_code(code)
        types = {cp.point_type for cp in result.all_coverage_points}
        assert CoveragePointType.STEP_ENTRY in types
        assert CoveragePointType.IF_TRUE in types
        assert CoveragePointType.IF_FALSE in types

    def test_multiple_if_branches(self):
        code = textwrap.dedent("""\
            data output;
                set input;
                if age < 25 then group = 1;
                else if age < 45 then group = 2;
                else group = 3;
            run;
        """)
        result = parse_sas_code(code)
        if_true_count = sum(
            1 for cp in result.all_coverage_points
            if cp.point_type == CoveragePointType.IF_TRUE
        )
        # Two IF conditions: age < 25 and age < 45
        assert if_true_count == 2

    def test_select_when(self):
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
        result = parse_sas_code(code)
        types = [cp.point_type for cp in result.all_coverage_points]
        assert CoveragePointType.SELECT_WHEN in types
        assert CoveragePointType.SELECT_OTHERWISE in types

        when_count = types.count(CoveragePointType.SELECT_WHEN)
        assert when_count == 2

    def test_proc_sql(self):
        code = textwrap.dedent("""\
            proc sql;
                create table summary as
                select name,
                    case
                        when score >= 80 then "HIGH"
                        when score >= 50 then "MED"
                        else "LOW"
                    end as tier
                from students
                where age > 18;
            quit;
        """)
        result = parse_sas_code(code)
        assert len(result.blocks) == 1
        assert result.blocks[0].block_type == BlockType.PROC_SQL

        types = {cp.point_type for cp in result.all_coverage_points}
        assert CoveragePointType.STEP_ENTRY in types
        assert CoveragePointType.SQL_CASE_WHEN in types
        assert CoveragePointType.SQL_CASE_ELSE in types
        assert CoveragePointType.SQL_WHERE in types

    def test_input_datasets_from_set(self):
        code = textwrap.dedent("""\
            data output;
                set mylib.customers;
                x = 1;
            run;
        """)
        result = parse_sas_code(code)
        assert "mylib.customers" in result.blocks[0].input_datasets

    def test_output_datasets(self):
        code = textwrap.dedent("""\
            data results;
                set input;
                x = 1;
            run;
        """)
        result = parse_sas_code(code)
        assert "results" in result.blocks[0].output_datasets

    def test_variables_detected(self):
        code = textwrap.dedent("""\
            data output;
                set input;
                if age > 65 then x = 1;
                if income < 50000 then y = 1;
            run;
        """)
        result = parse_sas_code(code)
        var_names = {v.name for v in result.all_variables}
        assert "age" in var_names
        assert "income" in var_names

    def test_condition_captured(self):
        code = textwrap.dedent("""\
            data output;
                set input;
                if age > 65 then x = 1;
            run;
        """)
        result = parse_sas_code(code)
        if_true_points = [
            cp for cp in result.all_coverage_points
            if cp.point_type == CoveragePointType.IF_TRUE
        ]
        assert len(if_true_points) == 1
        assert "age" in if_true_points[0].condition.lower()

    def test_empty_file(self):
        result = parse_sas_code("")
        assert len(result.blocks) == 0
        assert len(result.all_coverage_points) == 0

    def test_comments_ignored(self):
        code = textwrap.dedent("""\
            /* data fake; set nothing; if x > 1 then y = 2; run; */
            data real;
                set input;
                x = 1;
            run;
        """)
        result = parse_sas_code(code)
        assert len(result.blocks) == 1
        assert result.blocks[0].name == "real"


class TestSampleProgram:
    """Test parsing of the sample SAS program in examples/."""

    @pytest.fixture
    def sample_result(self) -> ParseResult:
        sample_path = EXAMPLES_DIR / "sample_program.sas"
        if not sample_path.exists():
            pytest.skip("Sample program not found")
        return parse_sas_file(sample_path)

    def test_blocks_found(self, sample_result: ParseResult):
        assert len(sample_result.blocks) >= 2  # DATA step + PROC SQL

    def test_data_step_found(self, sample_result: ParseResult):
        data_blocks = [b for b in sample_result.blocks if b.block_type == BlockType.DATA_STEP]
        assert len(data_blocks) >= 1
        assert data_blocks[0].name == "classified"

    def test_proc_sql_found(self, sample_result: ParseResult):
        sql_blocks = [b for b in sample_result.blocks if b.block_type == BlockType.PROC_SQL]
        assert len(sql_blocks) >= 1

    def test_many_coverage_points(self, sample_result: ParseResult):
        # The sample has: 5 IF branches + SELECT + PROC SQL = many points
        assert len(sample_result.all_coverage_points) >= 10

    def test_variables_detected(self, sample_result: ParseResult):
        var_names = {v.name for v in sample_result.all_variables}
        assert "age" in var_names
        assert "income" in var_names
        assert "score" in var_names

    def test_no_errors(self, sample_result: ParseResult):
        assert len(sample_result.errors) == 0
