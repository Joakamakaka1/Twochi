"""Guards and summary for a `terraform plan` in JSON (`terraform show -json`).

CI/CD e IaC, «Plan y apply»: the plan fails if it brings `*` as the resource of an
IAM policy or deletes a bucket. Deny statements may use `*`: they only narrow. An
Allow on `*` is also what most AWS managed policies grant, so attaching one fails too.

A policy the plan cannot know until apply (it depends on an ARN still to be created)
passes only when it comes from an `aws_iam_policy_document`, whose statements the plan
does show and this script checks.

Usage: python plan_check.py PLAN_JSON [SUMMARY_MD]
"""

import json
import re
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any, cast

type Json = dict[str, Any]

POLICY_DOCUMENT = "aws_iam_policy_document"
AWS_MANAGED_POLICY = "arn:aws:iam::aws:policy/"
BUCKET_TYPES = frozenset({"aws_s3_bucket", "aws_s3_directory_bucket"})
ATTACHMENT_TYPES = frozenset(
    {
        "aws_iam_role_policy_attachment",
        "aws_iam_user_policy_attachment",
        "aws_iam_group_policy_attachment",
        "aws_iam_policy_attachment",
    }
)
INDEX = re.compile(r"\[[^\]]*\]")
DOCUMENT_REFERENCE = re.compile(rf"^data\.{POLICY_DOCUMENT}\.[A-Za-z0-9_-]+")


def _as_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return cast("list[object]", value)
    return [value]


def _allows_everything(
    effect: object, resources: object, not_resources: object
) -> bool:
    if str(effect or "Allow").casefold() != "allow":
        return False
    return "*" in _as_list(resources) or bool(_as_list(not_resources))


def json_policy_violations(address: str, text: str) -> list[str]:
    """Allow statements on `*`, or on everything but a list, in a policy JSON."""
    try:
        document = cast("Json", json.loads(text))
    except json.JSONDecodeError:
        return [f"{address}: its policy is not valid JSON, so it cannot be checked."]
    statements = cast("list[Json]", _as_list(document.get("Statement")))
    return [
        f"{address}: statement {statement.get('Sid') or index} allows `*` as resource."
        for index, statement in enumerate(statements)
        if _allows_everything(
            statement.get("Effect"),
            statement.get("Resource"),
            statement.get("NotResource"),
        )
    ]


def document_violations(address: str, values: Mapping[str, Any]) -> list[str]:
    """Allow statements on `*` in an `aws_iam_policy_document` data source."""
    statements = cast("list[Json]", _as_list(values.get("statement")))
    found = [
        f"{address}: statement {statement.get('sid') or index} allows `*` as resource."
        for index, statement in enumerate(statements)
        if _allows_everything(
            statement.get("effect"),
            statement.get("resources"),
            statement.get("not_resources"),
        )
    ]
    # Documents merged in as JSON; an unknown one is another document, checked apart.
    for field in ("source_policy_documents", "override_policy_documents"):
        for text in _as_list(values.get(field)):
            if isinstance(text, str):
                found.extend(json_policy_violations(address, text))
    return found


def _config_resources(module: Json, prefix: str = "") -> Iterator[tuple[str, Json]]:
    for resource in cast("list[Json]", module.get("resources", [])):
        yield prefix + str(resource["address"]), resource
    for name, call in cast("dict[str, Json]", module.get("module_calls", {})).items():
        child = cast("Json", call.get("module", {}))
        yield from _config_resources(child, f"{prefix}module.{name}.")


def _state_resources(module: Json) -> Iterator[Json]:
    yield from cast("list[Json]", module.get("resources", []))
    for child in cast("list[Json]", module.get("child_modules", [])):
        yield from _state_resources(child)


def _config_address(change: Json) -> str:
    """The address in `configuration`: no instance keys, module path included."""
    return INDEX.sub("", str(change["address"]))


def _unknown_policy_is_checked(
    config_address: str, attribute: str, config: Mapping[str, Json]
) -> bool:
    """An unknown policy passes if the code does not set it or a document builds it.

    Not set: the provider computes it (the deprecated `policy` of `aws_s3_bucket`).
    """
    expressions = cast("Json", config.get(config_address, {}).get("expressions", {}))
    if attribute not in expressions:
        return True
    expression = cast("Json", expressions[attribute])
    references = [str(ref) for ref in _as_list(expression.get("references"))]
    return bool(references) and all(DOCUMENT_REFERENCE.match(ref) for ref in references)


def _policy_violations(change: Json, config: Mapping[str, Json]) -> Iterator[str]:
    address = str(change["address"])
    after = cast("Json", change["change"].get("after") or {})
    unknown = cast("Json", change["change"].get("after_unknown") or {})
    config_address = _config_address(change)
    if isinstance(after.get("policy"), str):
        yield from json_policy_violations(address, after["policy"])
    elif unknown.get("policy") is True and not _unknown_policy_is_checked(
        config_address, "policy", config
    ):
        yield (
            f"{address}: its policy is only known at apply and does not come from an "
            f"{POLICY_DOCUMENT}, so it cannot be checked."
        )
    for inline in cast("list[Json]", _as_list(after.get("inline_policy"))):
        if isinstance(inline.get("policy"), str):
            yield from json_policy_violations(address, inline["policy"])
    arns = [after.get("policy_arn"), *_as_list(after.get("managed_policy_arns"))]
    for arn in arns:
        if isinstance(arn, str) and arn.startswith(AWS_MANAGED_POLICY):
            yield f"{address}: attaches the AWS managed policy {arn}, which allows `*`."


def violations(plan: Json) -> list[str]:
    """Every broken guard in the plan, one message each; empty when it passes."""
    config = dict(
        _config_resources(plan.get("configuration", {}).get("root_module", {}))
    )
    found: list[str] = []
    for change in cast("list[Json]", plan.get("resource_changes", [])):
        actions = cast("list[str]", change["change"]["actions"])
        kind = str(change["type"])
        if change["mode"] == "data":
            if kind == POLICY_DOCUMENT:
                after = cast("Json", change["change"].get("after") or {})
                found.extend(document_violations(str(change["address"]), after))
            continue
        if kind in BUCKET_TYPES and "delete" in actions:
            found.append(f"{change['address']}: the plan deletes a bucket.")
        if "create" in actions or "update" in actions:
            found.extend(_policy_violations(change, config))
    # Documents read during the plan are in the prior state, not among the changes.
    prior = plan.get("prior_state", {}).get("values", {}).get("root_module", {})
    for resource in _state_resources(prior):
        if resource.get("mode") == "data" and resource.get("type") == POLICY_DOCUMENT:
            values = cast("Json", resource.get("values") or {})
            found.extend(document_violations(str(resource["address"]), values))
    return sorted(set(found))


SYMBOLS = {
    ("create",): "+",
    ("update",): "~",
    ("delete",): "-",
    ("delete", "create"): "-/+",
    ("create", "delete"): "+/-",
}


def summary(plan: Json, broken: list[str]) -> str:
    """Markdown for the PR: totals, each change with its symbol and the guards."""
    rows: list[tuple[str, str]] = []
    add = change = destroy = 0
    for entry in cast("list[Json]", plan.get("resource_changes", [])):
        actions = tuple(cast("list[str]", entry["change"]["actions"]))
        if entry["mode"] != "managed" or actions not in SYMBOLS:
            continue
        add += "create" in actions
        change += actions == ("update",)
        destroy += "delete" in actions
        rows.append((SYMBOLS[actions], str(entry["address"])))
    lines = ["### `terraform plan` · infra/stack", ""]
    if rows:
        lines += [f"**{add} to add, {change} to change, {destroy} to destroy.**", ""]
        lines += ["| | Resource |", "| --- | --- |"]
        lines += [f"| `{symbol}` | `{address}` |" for symbol, address in rows]
    else:
        lines.append("**No changes.**")
    lines += ["", "#### Guards", ""]
    if broken:
        lines += [f"- ❌ {message}" for message in broken]
    else:
        lines.append("- ✅ No `*` allowed as an IAM resource and no bucket deleted.")
    return "\n".join(lines) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        sys.stderr.write("usage: plan_check.py PLAN_JSON [SUMMARY_MD]\n")
        return 2
    plan = cast("Json", json.loads(Path(argv[1]).read_text(encoding="utf-8")))
    broken = violations(plan)
    if len(argv) == 3:
        Path(argv[2]).write_text(summary(plan, broken), encoding="utf-8")
    for message in broken:
        sys.stdout.write(f"::error title=plan guard::{message}\n")
    if not broken:
        sys.stdout.write("plan guards: OK\n")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
