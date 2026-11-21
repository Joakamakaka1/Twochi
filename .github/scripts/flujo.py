"""The `flujo` check: PR title and, in sensitive paths, Linear link and evidence.

Rules from Forma de trabajo («Cómo se fuerza el flujo») and Arquitectura y
convenciones («Git y pull requests»). The PR text is read from the event file,
never interpolated into a shell command.

Usage: python flujo.py CHANGED_FILES  (NUL-separated; reads GITHUB_EVENT_PATH)
"""

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

TYPES = ("feat", "fix", "refactor", "perf", "test", "docs", "build", "ci", "chore")
TITLE = re.compile(rf"^(?:{'|'.join(TYPES)})(?:\([a-z0-9-]+\))?!?: \S.*$")
LINEAR_ID = re.compile(r"\(TWO-\d+\)$")
# Something that tries to be an id at the end of the title, in any spelling.
ID_LIKE = re.compile(r"\(\s*two[\s_-]*\d+\s*\)$", re.IGNORECASE)

# Paths whose PRs a person merges. Extend this list when a sensitive module gets its own
# path (login and aal2, privacy filter, usage caps, turn contract, memory ingest).
SENSITIVE_PREFIXES = (
    ".github/",
    ".claude/",
    "infra/",
    "supabase/",
)
# Files that can weaken a check without touching the check itself.
SENSITIVE_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "CODING_STANDARDS.md",
    "justfile",
    "mise.toml",
    "pyproject.toml",
    ".pre-commit-config.yaml",
    "apps/web/eslint.config.js",
)

REQUIRED_SECTIONS = ("Evidencia", "Peligro de fusión")
HEADING = re.compile(r"^#{1,3}\s+(.+?)\s*$", re.MULTILINE)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
DEPENDABOT = "dependabot[bot]"


@dataclass(frozen=True, slots=True)
class PullRequest:
    title: str
    body: str
    author: str
    changed_files: tuple[str, ...]


def is_sensitive(path: str) -> bool:
    """Tell whether a changed path belongs to a sensitive zone."""
    return path in SENSITIVE_FILES or path.startswith(SENSITIVE_PREFIXES)


def has_section(body: str, name: str) -> bool:
    """Tell whether a level 1 to 3 heading with that name has content of its own.

    Template hints are HTML comments, so an untouched template does not pass.
    """
    headings = list(HEADING.finditer(body))
    for index, heading in enumerate(headings):
        if heading.group(1).casefold() != name.casefold():
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(body)
        content = HTML_COMMENT.sub("", body[heading.end() : end])
        if content.strip():
            return True
    return False


def check(pr: PullRequest) -> list[str]:
    """Return the broken rules, one message each; empty when the PR passes."""
    errors: list[str] = []
    title = pr.title.strip()
    if not TITLE.match(title):
        errors.append(
            "The title must follow Conventional Commits: "
            f"type(scope): summary (TWO-n), with type one of {', '.join(TYPES)}."
        )
    elif ID_LIKE.search(title) and not LINEAR_ID.search(title):
        errors.append("The Linear id at the end of the title must read (TWO-n).")
    if pr.author == DEPENDABOT:
        return errors

    sensitive = sorted(path for path in pr.changed_files if is_sensitive(path))
    if not sensitive:
        return errors
    touched = ", ".join(sensitive[:5]) + (" …" if len(sensitive) > 5 else "")
    if not LINEAR_ID.search(title):
        errors.append(
            f"Sensitive paths ({touched}) need the Linear id at the end of the title."
        )
    errors.extend(
        f"Sensitive paths need a «{section}» section with content in the PR body."
        for section in REQUIRED_SECTIONS
        if not has_section(pr.body, section)
    )
    return errors


def load(event_path: Path, changed_path: Path) -> PullRequest:
    """Build the PR from the GitHub event file and the list of changed files."""
    event = cast("dict[str, Any]", json.loads(event_path.read_text(encoding="utf-8")))
    pull = cast("dict[str, Any]", event["pull_request"])
    # NUL-separated, as `git diff --name-only -z` writes it: names may hold spaces.
    changed = [
        name for name in changed_path.read_text(encoding="utf-8").split(chr(0)) if name
    ]
    return PullRequest(
        title=str(pull["title"]),
        body=str(pull.get("body") or ""),
        author=str(pull["user"]["login"]),
        changed_files=tuple(changed),
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: flujo.py CHANGED_FILES_LIST\n")
        return 2
    pr = load(Path(os.environ["GITHUB_EVENT_PATH"]), Path(argv[1]))
    errors = check(pr)
    for error in errors:
        sys.stdout.write(f"::error title=flujo::{error}\n")
    if not errors:
        sys.stdout.write("flujo: OK\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
