# Task runner. `just check` runs the same steps as CI, failing fast.

set shell := ["bash", "-eu", "-c"]
# On Windows, run recipes with Git Bash's sh (System32\bash.exe would start WSL instead).
set windows-shell := ["sh", "-eu", "-c"]

# Keep Python output in UTF-8 on Windows consoles.
export PYTHONUTF8 := "1"

default:
    @just --list

# Install pinned tools, dependencies and the pre-commit hooks.
setup:
    mise install
    uv sync --locked
    pnpm install --frozen-lockfile
    uvx pre-commit@4.7.0 install

# Everything CI checks, in order. CI runs these same recipes, one job each.
check: check-py check-web check-workflows check-infra

# Python: format, lint, types, import contracts and tests with the domain coverage gate.
check-py:
    uv run --locked ruff format --check .
    uv run --locked ruff check .
    uv run --locked pyright
    uv run --locked lint-imports
    uv run --locked pytest --cov

# Front: lint, types and tests in every pnpm workspace.
check-web:
    pnpm -r --if-present run lint
    pnpm -r --if-present run typecheck
    pnpm -r --if-present run test

# Workflows: actionlint and zizmor (online audits only when GH_TOKEN is set).
check-workflows:
    actionlint
    zizmor .

# Terraform: format, validate each root (modules through them) without a backend, and tflint.
check-infra:
    if [ -d infra ]; then terraform fmt -check -recursive infra; fi
    for dir in infra/bootstrap infra/stack; do [ -d "$dir" ] || continue; terraform -chdir="$dir" init -backend=false -input=false -lockfile=readonly > /dev/null; terraform -chdir="$dir" validate; done
    if [ -d infra ]; then cd infra && tflint --init && tflint --recursive; fi

# Format and autofix.
fmt:
    uv run --locked ruff format .
    uv run --locked ruff check --fix .
    pnpm -r --if-present run lint --fix

# Run the Python and front tests.
test:
    uv run --locked pytest
    pnpm -r --if-present run test

# Start local Supabase (needs Docker).
up:
    supabase start

# Stop local Supabase.
down:
    supabase stop
