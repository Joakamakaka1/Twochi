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
check: check-db check-py check-dump check-web check-workflows check-infra

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

# Dump the local database as the daily job does (pinned image, as twochi_backup), check
# what data.sql leaves out, rebuild without the seed, restore as postgres and compare the
# rows (ADR 0012). Needs `just up`, with nothing else writing to the database meanwhile.
# It ends with `supabase db reset`, which wipes local data outside the seed, so it runs
# after check-py.
check-dump:
    uv run --locked python .github/scripts/check_dump.py

# Front: the client generated from the committed OpenAPI is current (so a change in the
# contract reaches tsc), then lint, types and tests in every pnpm workspace.
check-web:
    pnpm --filter @twochi/api-client run check-generated
    pnpm -r --if-present run lint
    pnpm -r --if-present run typecheck
    pnpm -r --if-present run test

# Workflows: actionlint and zizmor (online audits only when GH_TOKEN is set), plus the
# shell scripts that workflows run. actionlint silently skips its shellcheck pass when
# it finds no shellcheck, so it gets the pinned one by path; `mise which` fails when that
# version is not installed.
check-workflows:
    shellcheck="$(mise which shellcheck)" && actionlint -shellcheck "$shellcheck" && for script in .github/scripts/*.sh; do [ ! -e "$script" ] || "$shellcheck" "$script"; done
    zizmor .

# Terraform: format, validate each root (modules through them) without a backend, and tflint;
# then the tests of the CloudFront Functions.
check-infra:
    if [ -d infra ]; then terraform fmt -check -recursive infra; fi
    for dir in infra/bootstrap infra/stack; do [ -f "$dir/versions.tf" ] || continue; terraform -chdir="$dir" init -backend=false -input=false -lockfile=readonly > /dev/null; terraform -chdir="$dir" validate; done
    if [ -d infra ]; then cd infra && tflint --init && tflint --recursive; fi
    node --test "infra/**/*.test.mjs"

# The draft PR body in FILE as CI's `flujo` will judge it (TWO-26): the files changed
# against the base, fetched from origin, the base's flujo.py and the title, by default
# the last non-merge commit's subject. Run it before `gh pr create`, with the PR's title
# when it differs: `just check-pr-body FILE "TITLE"`. A stacked PR adds `--base BRANCH`.
[positional-arguments]
check-pr-body file *args:
    uv run --locked python scripts/check_pr_body.py "$@"

# Regenerate the OpenAPI document from the API, and the front's types from it. A test in
# check-py fails while the document is stale; check-web fails while the types are.
openapi:
    uv run --locked python scripts/export_openapi.py
    pnpm --filter @twochi/api-client run generate

# Build a Lambda zip for arm64 into dist/, named by the hash of its inputs, as CI does.
package app="api":
    uv run --locked python .github/scripts/lambda_package.py build {{app}} dist

# Post-deploy smoke test through CloudFront: resolves the domain over DoH (dns.google),
# since a local DNS may intercept it, then checks /api/health, the front and an API 404.
# Three GETs without credentials against production; the table is the PR's evidence.
# Only from an allowed country: the WAF blocks the rest, CI's runners included.
smoke-edge:
    uv run --locked python scripts/smoke_edge.py

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

# A work slot for a ticket that runs in parallel with others (TWO-43): the worktree
# .claude/worktrees/slot-N on BRANCH (created from origin/main when new), dependencies
# installed, and its own Supabase `twochi-sN` on ports 553xx + 100·N with CI's services.
# N goes from 1 to 9; the main folder is slot 0. Inside a slot every recipe works as in
# the main folder: the tests read the port from the slot's supabase/config.toml.
[positional-arguments]
slot n branch:
    uv run --locked python scripts/slot.py up "$@"

# Stop slot N's Supabase, delete its data and remove its worktree; the branch stays.
# Never `twochi`, the main folder's. Uncommitted changes or unpushed commits stop it,
# unless `--force` follows the number.
[positional-arguments]
slot-down n *flags:
    uv run --locked python scripts/slot.py down "$@"
