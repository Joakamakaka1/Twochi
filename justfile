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
check: check-db check-py check-web check-workflows check-infra

# Database: lint the local schema. Needs local Supabase (`just up`), as the tests do.
check-db:
    supabase db lint --level warning --fail-on warning

# Python: format, lint, types, import contracts and tests with the domain coverage gate.
# Use-case, data and API tests run against local Supabase: start it with `just up`.
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

# Workflows: actionlint and zizmor (online audits only when GH_TOKEN is set), plus the
# shell scripts that workflows run. actionlint silently skips its shellcheck pass when
# it finds no shellcheck, so it gets the pinned one by path; `mise which` fails when that
# version is not installed.
check-workflows:
    shellcheck="$(mise which shellcheck)" && actionlint -shellcheck "$shellcheck" && "$shellcheck" .github/scripts/*.sh
    zizmor .

# Terraform: format, validate each root (modules through them) without a backend, and tflint;
# then the tests of the CloudFront Functions.
check-infra:
    if [ -d infra ]; then terraform fmt -check -recursive infra; fi
    for dir in infra/bootstrap infra/stack; do [ -f "$dir/versions.tf" ] || continue; terraform -chdir="$dir" init -backend=false -input=false -lockfile=readonly > /dev/null; terraform -chdir="$dir" validate; done
    if [ -d infra ]; then cd infra && tflint --init && tflint --recursive; fi
    node --test "infra/**/*.test.mjs"

# Build a Lambda zip for arm64 into dist/, named by the hash of its inputs, as CI does.
package app="api":
    uv run --locked python .github/scripts/lambda_package.py build {{app}} dist

# Format and autofix.
fmt:
    uv run --locked ruff format .
    uv run --locked ruff check --fix .
    pnpm -r --if-present run lint --fix

# Run the Python and front tests.
test:
    uv run --locked pytest
    pnpm -r --if-present run test

# Start local Supabase (needs Docker). Twochi uses ports 553xx, apart from other projects.
up:
    supabase start

# Rebuild the local database from the migrations and the seed.
reset:
    supabase db reset

# Who may sign up and the test couple, from supabase/provision.toml (ADR 0007). Local by
# default; `--production` writes to the hosted project, only with the user's explicit OK.
[positional-arguments]
provision *args:
    uv run --locked python scripts/provision.py "$@"

# Stop local Supabase.
down:
    supabase stop
