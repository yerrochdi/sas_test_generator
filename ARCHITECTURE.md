# SAS Data Generator — Architecture

## Overview

A Python tool that **generates test datasets** designed to maximize execution
coverage of SAS programs. It works by:

1. **Parsing** SAS code to identify branches, conditions, and variable usage
2. **Instrumenting** the SAS code with coverage markers
3. **Generating** test datasets with targeted values
4. **Running** instrumented SAS in batch mode
5. **Analyzing** coverage and **mutating** datasets to fill gaps

```
┌─────────────┐     ┌──────────────┐     ┌────────────────┐
│  SAS Files  │────>│  sas_parser  │────>│ Coverage Points │
│  (.sas)     │     │  (regex)     │     │ + Variables     │
└─────────────┘     └──────────────┘     └───────┬────────┘
                                                  │
                    ┌──────────────┐               │
                    │  instrumenter│<──────────────┘
                    │  (inject PUT)│      ┌────────────────┐
                    └──────┬───────┘      │dataset_generator│
                           │              │ (seed+mutate)   │
                           v              └───────┬────────┘
                    ┌──────────────┐               │
                    │  sas_runner  │<──────────────┘
                    │  (batch sas) │     (CSV datasets)
                    └──────┬───────┘
                           │
                           v
                    ┌──────────────┐     ┌────────────────┐
                    │  SAS Log     │────>│   coverage.py  │
                    │  (COV:POINT) │     │   (parse+stats)│
                    └──────────────┘     └───────┬────────┘
                                                  │
                                          ┌───────v────────┐
                                          │ Coverage Report │
                                          │ (JSON/text)     │
                                          └────────────────┘
```

## Coverage Strategy

### Coverage Points

Each instrumentable location gets a unique ID: `<file_stem>:<counter>`.

| Type               | SAS Construct              | How Instrumented                |
|--------------------|----------------------------|---------------------------------|
| STEP_ENTRY         | `DATA ...;`                | PUT after DATA statement        |
| IF_TRUE            | `IF cond THEN`             | PUT inside THEN block           |
| IF_FALSE           | `ELSE` (or missing ELSE)   | PUT inside ELSE / add ELSE+PUT  |
| SELECT_WHEN        | `WHEN (cond)`              | PUT inside WHEN block           |
| SELECT_OTHERWISE   | `OTHERWISE`                | PUT inside OTHERWISE block      |
| SQL_WHERE          | `WHERE cond`               | %PUT before SQL statement       |
| SQL_CASE_WHEN      | `CASE WHEN cond THEN`      | %PUT before SQL statement       |
| SQL_CASE_ELSE      | `CASE ... ELSE`            | %PUT before SQL statement       |

### Dual Recording Mechanism

1. **Primary — Log markers**: `PUT "COV:POINT=<id>";` writes to SAS log.
   Parsed by `coverage.py` after execution.
2. **Secondary — Coverage dataset**: `_cov_tracker` dataset accumulates hits.
   Exported to CSV in the postamble.

### Why PUT-based?

- Works everywhere (DATA step, macro, even some PROC contexts)
- No additional library/dataset setup required
- Survives errors in other parts of the program
- Easy to grep from log files in CI

## Module Reference

### `sas_parser.py`

Regex-based parser. Identifies DATA steps, PROC SQL, IF/ELSE, SELECT/WHEN,
SET/MERGE, INPUT statements, and extracts variable references from conditions.

### `sas_instrumenter.py`

Takes parse results and injects PUT statements at each coverage point.
Wraps the original code with a preamble (macro definitions, tracker init)
and postamble (CSV export, completion marker).

### `dataset_generator.py`

**Seed phase**: Extracts variables and conditions from parse results.
Generates values around condition thresholds (boundary testing).

**Mutate phase**: Analyzes missed coverage points, generates targeted rows
that should trigger uncovered branches.

### `sas_runner.py`

Finds SAS executable, writes instrumented code to temp file, runs
`sas -batch -noterminal`, captures log.

### `coverage.py`

Parses `COV:POINT=<id>` markers from SAS log (or CSV). Computes
hit/miss/percentage. Supports merging across multiple runs.

### `cli.py`

Typer-based CLI with commands: `analyze`, `instrument`, `generate`, `run`.

## Data Flow (Full Loop)

```
for iteration in 1..max_iterations:
    1. Export datasets to CSV
    2. Build SAS code: data_load + instrumented_program
    3. Run SAS batch
    4. Parse coverage from log
    5. If coverage >= target: stop
    6. Analyze missed points → generate targeted mutation rows
    7. Append mutation rows to datasets
```

## Limitations (MVP)

| Limitation                          | Impact                            | Planned Fix (V1)                  |
|-------------------------------------|-----------------------------------|-----------------------------------|
| No macro resolution                 | %IF/%THEN not instrumented        | Macro pre-processor               |
| No %INCLUDE expansion               | Included files not analyzed       | Resolve includes before parsing   |
| Regex parser                        | May misparse edge cases           | Tree-sitter or ANTLR grammar      |
| Strings inside comments/quotes      | Could produce false matches       | Proper tokenizer                  |
| PROC SQL CASE/WHEN                  | Log-level only (not per-row)      | Post-execution output analysis    |
| Nested DO blocks                    | Depth tracking approximate        | Stack-based block tracker         |
| Formats/informats                   | Basic detection only              | Full SAS format catalog           |
| Arrays                              | Not parsed                        | Array reference expansion         |
| Multiple SET statements             | Detected but not sequenced        | Control flow analysis             |

## Phased Roadmap

### MVP (current)
- [x] Regex parser for DATA + PROC SQL
- [x] PUT-based coverage instrumentation
- [x] Seed + mutation dataset generator
- [x] SAS batch runner with log parsing
- [x] CLI with analyze/generate/run commands
- [x] GitLab CI pipeline
- [x] Unit tests

### V1 (next)
- [ ] %INCLUDE resolution (read and inline included files)
- [ ] Basic %MACRO/%MEND boundary detection
- [ ] SAS7BDAT export via pyreadstat
- [ ] HTML coverage report with annotated SAS source
- [ ] Configuration file (YAML) for project settings
- [ ] Parallel SAS execution for multiple test variants

### V2 (future)
- [ ] Proper SAS tokenizer (handle strings/comments correctly)
- [ ] PROC FREQ/MEANS/REG coverage points
- [ ] DATA step control flow graph
- [ ] Constraint-based data generation (SMT solver)
- [ ] Integration with SAS Viya / SAS Studio APIs
- [ ] Coverage badge for GitLab
