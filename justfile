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

# Everything CI checks, in order: lint, types, import contracts and tests.
check:
    uv run --locked ruff format --check .
    uv run --locked ruff check .
    uv run --locked pyright
    uv run --locked lint-imports
    uv run --locked pytest --cov
    pnpm -r --if-present run lint
    pnpm -r --if-present run typecheck
    pnpm -r --if-present run test

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
