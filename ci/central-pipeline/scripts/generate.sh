#!/usr/bin/env bash
# =============================================================================
# generate.sh — Clone SAS projects and generate test datasets
#
# Usage:
#   ./scripts/generate.sh [options]
#
# Options:
#   --config FILE    Path to projects.yml (default: projects.yml)
#   --output DIR     Output directory (default: output/)
#   --dry-run        Skip SAS execution
#   --project NAME   Process only this project (by name)
#   --verbose        Show detailed output
# =============================================================================

set -euo pipefail

# ---- Default values ----
CONFIG_FILE="projects.yml"
OUTPUT_DIR="output"
DRY_RUN=""
SINGLE_PROJECT=""
VERBOSE=""
CLONE_DIR="workspace"

# ---- Parse arguments ----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)   CONFIG_FILE="$2";   shift 2 ;;
        --output)   OUTPUT_DIR="$2";    shift 2 ;;
        --dry-run)  DRY_RUN="--dry-run"; shift ;;
        --project)  SINGLE_PROJECT="$2"; shift 2 ;;
        --verbose)  VERBOSE="--verbose"; shift ;;
        *)          echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ---- Check dependencies ----
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 not found"; exit 1; }
command -v sas-datagen >/dev/null 2>&1 || { echo "ERROR: sas-datagen not found. Run: pip install git+https://github.com/yerrochdi/sas_test_generator.git"; exit 1; }
command -v yq >/dev/null 2>&1 || {
    echo "INFO: yq not found, using Python YAML parser"
    USE_PYTHON_YAML=true
}

# ---- Helper: read projects.yml with Python (no yq dependency) ----
read_projects() {
    python3 << 'PYEOF'
import yaml
import sys
import os

config_file = os.environ.get("CONFIG_FILE", "projects.yml")
single = os.environ.get("SINGLE_PROJECT", "")

with open(config_file) as f:
    config = yaml.safe_load(f)

for proj in config.get("projects", []):
    if not proj.get("enabled", True):
        continue
    if single and proj["name"] != single:
        continue

    name = proj["name"]
    repo = proj["repo"]
    branch = proj.get("branch", "main")
    entry = proj.get("entry", "main.sas")
    include_paths = ",".join(proj.get("include_paths", []))
    rows = proj.get("rows", 30)

    # Macro vars as key=value pairs separated by |
    macro_vars = "|".join(
        f"{k}={v}" for k, v in proj.get("macro_vars", {}).items()
    )

    print(f"{name}|{repo}|{branch}|{entry}|{include_paths}|{rows}|{macro_vars}")
PYEOF
}

# ---- Setup ----
mkdir -p "$OUTPUT_DIR"
mkdir -p "$CLONE_DIR"

TOTAL=0
SUCCESS=0
FAILED=0
FAILED_PROJECTS=""

echo "============================================="
echo "  SAS Test Data Generator — Central Pipeline"
echo "============================================="
echo "Config:  $CONFIG_FILE"
echo "Output:  $OUTPUT_DIR"
echo "Date:    $(date '+%Y-%m-%d %H:%M:%S')"
echo ""

# ---- Process each project ----
while IFS='|' read -r NAME REPO BRANCH ENTRY INCLUDE_PATHS ROWS MACRO_VARS; do
    TOTAL=$((TOTAL + 1))
    PROJECT_DIR="$CLONE_DIR/$NAME"
    PROJECT_OUTPUT="$OUTPUT_DIR/$NAME"

    echo "---------------------------------------------"
    echo "Project: $NAME"
    echo "Repo:    $REPO"
    echo "Branch:  $BRANCH"
    echo "Entry:   $ENTRY"
    echo "---------------------------------------------"

    # 1. Clone or update the repo
    if [ -d "$PROJECT_DIR" ]; then
        echo "  -> Updating existing clone..."
        (cd "$PROJECT_DIR" && git fetch origin && git checkout "$BRANCH" && git pull origin "$BRANCH") || {
            echo "  ERROR: Failed to update $NAME"
            FAILED=$((FAILED + 1))
            FAILED_PROJECTS="$FAILED_PROJECTS $NAME"
            continue
        }
    else
        echo "  -> Cloning $REPO (branch: $BRANCH)..."
        git clone --branch "$BRANCH" --depth 1 "$REPO" "$PROJECT_DIR" || {
            echo "  ERROR: Failed to clone $NAME"
            FAILED=$((FAILED + 1))
            FAILED_PROJECTS="$FAILED_PROJECTS $NAME"
            continue
        }
    fi

    # 2. Build sas-datagen command
    CMD="sas-datagen run"
    CMD="$CMD --project-dir $PROJECT_DIR"
    CMD="$CMD --entry $ENTRY"
    CMD="$CMD --output $PROJECT_OUTPUT"
    CMD="$CMD --rows $ROWS"
    CMD="$CMD --seed 42"
    CMD="$CMD --format csv"

    # Add include paths
    if [ -n "$INCLUDE_PATHS" ]; then
        IFS=',' read -ra PATHS <<< "$INCLUDE_PATHS"
        for p in "${PATHS[@]}"; do
            CMD="$CMD --include-path $PROJECT_DIR/$p"
        done
    fi

    # Add macro variables
    if [ -n "$MACRO_VARS" ]; then
        IFS='|' read -ra MVARS <<< "$MACRO_VARS"
        for mv in "${MVARS[@]}"; do
            CMD="$CMD --macro $mv"
        done
    fi

    # Add optional flags
    [ -n "$DRY_RUN" ] && CMD="$CMD $DRY_RUN"
    [ -n "$VERBOSE" ] && CMD="$CMD $VERBOSE"

    # 3. Run generation
    echo "  -> Running: $CMD"
    mkdir -p "$PROJECT_OUTPUT"

    if eval "$CMD"; then
        echo "  -> SUCCESS: Datasets generated in $PROJECT_OUTPUT/"
        SUCCESS=$((SUCCESS + 1))
    else
        echo "  -> FAILED: Generation failed for $NAME"
        FAILED=$((FAILED + 1))
        FAILED_PROJECTS="$FAILED_PROJECTS $NAME"
    fi

    echo ""

done < <(CONFIG_FILE="$CONFIG_FILE" SINGLE_PROJECT="$SINGLE_PROJECT" read_projects)

# ---- Summary ----
echo "============================================="
echo "  Summary"
echo "============================================="
echo "Total projects:  $TOTAL"
echo "Succeeded:       $SUCCESS"
echo "Failed:          $FAILED"
if [ -n "$FAILED_PROJECTS" ]; then
    echo "Failed projects: $FAILED_PROJECTS"
fi
echo "Output:          $OUTPUT_DIR/"
echo "============================================="

# Exit with error if any project failed
[ "$FAILED" -gt 0 ] && exit 1
exit 0
