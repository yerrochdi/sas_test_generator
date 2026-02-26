"""Tests for the %INCLUDE resolver module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sas_data_generator.include_resolver import (
    ResolvedSource,
    resolve_includes,
    scan_project_directory,
)


@pytest.fixture
def project_dir(tmp_path):
    """Create a temporary SAS project structure."""
    # Main file
    main = tmp_path / "main.sas"
    main.write_text(
        'data a; set b; run;\n'
        '%include "macros/calc.sas";\n'
        '%include "step2.sas";\n'
    )

    # Macro file in subdirectory
    macros_dir = tmp_path / "macros"
    macros_dir.mkdir()
    (macros_dir / "calc.sas").write_text(
        "/* calc macro */\n"
        "data calc_result;\n"
        "    set input;\n"
        "    if x > 10 then y = 1;\n"
        "    else y = 0;\n"
        "run;\n"
    )

    # Step 2 file at same level
    (tmp_path / "step2.sas").write_text(
        "proc sql;\n"
        "    create table summary as\n"
        "    select * from calc_result\n"
        "    where y = 1;\n"
        "quit;\n"
    )

    return tmp_path


@pytest.fixture
def nested_project(tmp_path):
    """Project with nested includes (A includes B includes C)."""
    (tmp_path / "a.sas").write_text(
        'data step_a; x = 1; run;\n'
        '%include "b.sas";\n'
    )
    (tmp_path / "b.sas").write_text(
        'data step_b; y = 2; run;\n'
        '%include "c.sas";\n'
    )
    (tmp_path / "c.sas").write_text(
        "data step_c;\n"
        "    set input;\n"
        "    if z > 5 then flag = 1;\n"
        "    else flag = 0;\n"
        "run;\n"
    )
    return tmp_path


class TestResolveIncludes:
    def test_basic_resolution(self, project_dir):
        result = resolve_includes(project_dir / "main.sas")

        # All files should be included
        assert len(result.included_files) == 3  # main + calc + step2
        assert not result.errors or all("not found" not in e for e in result.errors)

        # Resolved code should contain content from all files
        assert "calc_result" in result.resolved_code
        assert "summary" in result.resolved_code
        assert "set b" in result.resolved_code

    def test_nested_includes(self, nested_project):
        result = resolve_includes(nested_project / "a.sas")

        assert len(result.included_files) == 3
        assert "step_a" in result.resolved_code
        assert "step_b" in result.resolved_code
        assert "step_c" in result.resolved_code
        assert "if z > 5" in result.resolved_code

    def test_circular_include_detected(self, tmp_path):
        # A includes B, B includes A
        (tmp_path / "a.sas").write_text('%include "b.sas";\n')
        (tmp_path / "b.sas").write_text('%include "a.sas";\n')

        result = resolve_includes(tmp_path / "a.sas")

        # Should detect circular reference
        assert any("ircular" in err for err in result.errors)
        # Should not loop forever (test itself is the proof)

    def test_missing_include_reported(self, tmp_path):
        (tmp_path / "main.sas").write_text(
            'data a; run;\n'
            '%include "nonexistent.sas";\n'
        )

        result = resolve_includes(tmp_path / "main.sas")

        assert any("not found" in err for err in result.errors)
        # Original code should still be present
        assert "data a" in result.resolved_code

    def test_extra_search_dirs(self, tmp_path):
        # Main file in one dir, included file in another
        main_dir = tmp_path / "src"
        main_dir.mkdir()
        lib_dir = tmp_path / "lib"
        lib_dir.mkdir()

        (main_dir / "main.sas").write_text('%include "util.sas";\n')
        (lib_dir / "util.sas").write_text("data util; x = 1; run;\n")

        result = resolve_includes(
            main_dir / "main.sas",
            search_dirs=[str(lib_dir)],
        )

        assert "data util" in result.resolved_code
        assert not any("not found" in e for e in result.errors)

    def test_single_quoted_include(self, tmp_path):
        (tmp_path / "main.sas").write_text("%include 'sub.sas';\n")
        (tmp_path / "sub.sas").write_text("data sub; run;\n")

        result = resolve_includes(tmp_path / "main.sas")
        assert "data sub" in result.resolved_code

    def test_inc_shorthand(self, tmp_path):
        (tmp_path / "main.sas").write_text('%inc "sub.sas";\n')
        (tmp_path / "sub.sas").write_text("data sub; run;\n")

        result = resolve_includes(tmp_path / "main.sas")
        assert "data sub" in result.resolved_code

    def test_macro_var_in_path(self, tmp_path):
        (tmp_path / "main.sas").write_text('%include "&ROOT./sub.sas";\n')
        sub_dir = tmp_path / "myroot"
        sub_dir.mkdir()
        (sub_dir / "sub.sas").write_text("data sub; run;\n")

        result = resolve_includes(
            tmp_path / "main.sas",
            macro_vars={"ROOT": str(sub_dir)},
        )
        assert "data sub" in result.resolved_code

    def test_source_map_populated(self, project_dir):
        result = resolve_includes(project_dir / "main.sas")
        assert len(result.source_map) >= 1
        # Each entry is (start_line, end_line, file_path)
        for start, end, path in result.source_map:
            assert start < end
            assert path

    def test_no_includes(self, tmp_path):
        (tmp_path / "simple.sas").write_text(
            "data a; set b; if x > 1 then y = 1; run;\n"
        )
        result = resolve_includes(tmp_path / "simple.sas")
        assert len(result.included_files) == 1
        assert "data a" in result.resolved_code


class TestScanProjectDirectory:
    def test_scan_finds_all_sas(self, project_dir):
        files = scan_project_directory(project_dir)
        names = {f.name for f in files}
        assert "main.sas" in names
        assert "calc.sas" in names
        assert "step2.sas" in names

    def test_entry_file_first(self, project_dir):
        files = scan_project_directory(project_dir, entry_file="main.sas")
        assert files[0].name == "main.sas"

    def test_auto_detect_main(self, project_dir):
        files = scan_project_directory(project_dir)
        # main.sas should be auto-detected and placed first
        assert files[0].name == "main.sas"

    def test_empty_directory(self, tmp_path):
        files = scan_project_directory(tmp_path)
        assert len(files) == 0

    def test_nonexistent_directory(self):
        with pytest.raises(FileNotFoundError):
            scan_project_directory("/nonexistent/path")


class TestResolveWithParser:
    """Integration test: resolve includes then parse the result."""

    def test_parse_resolved_project(self, project_dir):
        from sas_data_generator.sas_parser import parse_sas_project

        result = parse_sas_project(project_dir / "main.sas")

        # Should find blocks from all included files
        assert len(result.blocks) >= 2  # DATA step from calc + PROC SQL from step2

        # Should find variables from conditions in included files
        var_names = {v.name for v in result.all_variables}
        assert "x" in var_names  # from calc.sas: if x > 10

        # Should have coverage points
        assert len(result.all_coverage_points) >= 3

    def test_parse_nested_project(self, nested_project):
        from sas_data_generator.sas_parser import parse_sas_project

        result = parse_sas_project(nested_project / "a.sas")

        # Should find blocks from all three files
        block_names = [b.name for b in result.blocks]
        assert "step_a" in block_names
        assert "step_b" in block_names
        assert "step_c" in block_names
