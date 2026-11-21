import json
from pathlib import Path
from typing import Any

import pytest
from plan_check import main, summary, violations

type Json = dict[str, Any]


def policy(*statements: Json) -> str:
    return json.dumps({"Version": "2012-10-17", "Statement": list(statements)})


def change(
    address: str,
    kind: str,
    actions: list[str],
    *,
    after: Json | None = None,
    unknown: Json | None = None,
    mode: str = "managed",
) -> Json:
    return {
        "address": address,
        "mode": mode,
        "type": kind,
        "name": address.rsplit(".", 1)[-1],
        "change": {
            "actions": actions,
            "after": after or {},
            "after_unknown": unknown or {},
        },
    }


def plan(
    *changes: Json, config: list[Json] | None = None, prior: list[Json] | None = None
) -> Json:
    return {
        "resource_changes": list(changes),
        "configuration": {"root_module": {"resources": config or []}},
        "prior_state": {"values": {"root_module": {"resources": prior or []}}},
    }


def role_policy(text: str, actions: list[str] | None = None) -> Json:
    return change(
        "aws_iam_role_policy.api",
        "aws_iam_role_policy",
        actions or ["create"],
        after={"policy": text},
    )


def test_passes_scoped_allow_and_wide_deny() -> None:
    text = policy(
        {
            "Effect": "Allow",
            "Action": "logs:PutLogEvents",
            "Resource": ["arn:aws:logs:x"],
        },
        {"Effect": "Deny", "Action": "s3:*", "Resource": "*"},
    )
    assert violations(plan(role_policy(text))) == []


@pytest.mark.parametrize(
    "statement",
    [
        {"Effect": "Allow", "Action": "s3:GetObject", "Resource": "*"},
        {"Action": "s3:GetObject", "Resource": ["arn:aws:s3:::a", "*"]},
        {"Effect": "Allow", "Action": "s3:GetObject", "NotResource": "arn:aws:s3:::a"},
    ],
)
def test_fails_allow_on_everything_in_policy_json(statement: Json) -> None:
    found = violations(plan(role_policy(policy(statement))))
    assert len(found) == 1
    assert "aws_iam_role_policy.api" in found[0]


def test_ignores_policies_being_destroyed() -> None:
    text = policy({"Effect": "Allow", "Action": "*", "Resource": "*"})
    assert violations(plan(role_policy(text, ["delete"]))) == []


def test_fails_invalid_policy_json() -> None:
    assert violations(plan(role_policy("{not json")))


def test_fails_wide_allow_in_policy_document_read_during_plan() -> None:
    document = {
        "address": "data.aws_iam_policy_document.api",
        "mode": "data",
        "type": "aws_iam_policy_document",
        "values": {
            "statement": [
                {"sid": "Wide", "effect": "Allow", "resources": ["*"]},
                {"sid": "Narrow", "effect": "Deny", "resources": ["*"]},
            ]
        },
    }
    assert violations(plan(prior=[document])) == [
        "data.aws_iam_policy_document.api: statement Wide allows `*` as resource."
    ]


def test_fails_wide_allow_in_deferred_policy_document() -> None:
    deferred = change(
        "data.aws_iam_policy_document.api",
        "aws_iam_policy_document",
        ["read"],
        mode="data",
        after={
            "statement": [{"sid": "Logs", "effect": None, "resources": [None, "*"]}]
        },
    )
    assert len(violations(plan(deferred))) == 1


def test_fails_wide_allow_in_merged_source_document() -> None:
    document = {
        "address": "data.aws_iam_policy_document.api",
        "mode": "data",
        "type": "aws_iam_policy_document",
        "values": {
            "statement": [],
            "source_policy_documents": [policy({"Effect": "Allow", "Resource": "*"})],
        },
    }
    assert len(violations(plan(prior=[document]))) == 1


def unknown_role_policy(expressions: Json) -> Json:
    config = [{"address": "aws_iam_role_policy.api", "expressions": expressions}]
    unknown = change(
        "aws_iam_role_policy.api",
        "aws_iam_role_policy",
        ["create"],
        unknown={"policy": True},
    )
    return plan(unknown, config=config)


def test_passes_unknown_policy_built_by_a_document() -> None:
    references = [
        "data.aws_iam_policy_document.api.json",
        "data.aws_iam_policy_document.api",
    ]
    assert violations(unknown_role_policy({"policy": {"references": references}})) == []


def test_fails_unknown_policy_built_any_other_way() -> None:
    references = ["aws_cloudwatch_log_group.api.arn", "aws_cloudwatch_log_group.api"]
    found = violations(unknown_role_policy({"policy": {"references": references}}))
    assert len(found) == 1
    assert "cannot be checked" in found[0]


def test_passes_unknown_policy_the_code_does_not_set() -> None:
    assert violations(unknown_role_policy({})) == []


def test_matches_instances_and_modules_to_their_configuration() -> None:
    references = ["data.aws_iam_policy_document.d.json"]
    config = {
        "root_module": {
            "module_calls": {
                "m": {
                    "module": {
                        "resources": [
                            {
                                "address": "aws_iam_policy.p",
                                "expressions": {"policy": {"references": references}},
                            }
                        ]
                    }
                }
            }
        }
    }
    unknown = change(
        'module.m[0].aws_iam_policy.p["a"]',
        "aws_iam_policy",
        ["create"],
        unknown={"policy": True},
    )
    assert violations({"resource_changes": [unknown], "configuration": config}) == []


def test_fails_aws_managed_policy_attachment() -> None:
    attachment = change(
        "aws_iam_role_policy_attachment.admin",
        "aws_iam_role_policy_attachment",
        ["create"],
        after={"policy_arn": "arn:aws:iam::aws:policy/AdministratorAccess"},
    )
    assert len(violations(plan(attachment))) == 1


def test_passes_own_managed_policy_attachment() -> None:
    attachment = change(
        "aws_iam_role_policy_attachment.own",
        "aws_iam_role_policy_attachment",
        ["create"],
        after={"policy_arn": "arn:aws:iam::123456789012:policy/twochi-x"},
    )
    assert violations(plan(attachment)) == []


@pytest.mark.parametrize(
    "actions", [["delete"], ["delete", "create"], ["create", "delete"]]
)
def test_fails_bucket_deletion_or_replacement(actions: list[str]) -> None:
    bucket = change("aws_s3_bucket.web", "aws_s3_bucket", actions)
    assert violations(plan(bucket)) == ["aws_s3_bucket.web: the plan deletes a bucket."]


def test_passes_bucket_update() -> None:
    assert (
        violations(plan(change("aws_s3_bucket.web", "aws_s3_bucket", ["update"]))) == []
    )


def test_summary_counts_like_terraform_and_lists_each_change() -> None:
    text = summary(
        plan(
            change("aws_lambda_function.api", "aws_lambda_function", ["update"]),
            change("aws_s3_bucket.web", "aws_s3_bucket", ["delete", "create"]),
            change("aws_route53_record.edge", "aws_route53_record", ["no-op"]),
            change("data.x.y", "x", ["read"], mode="data"),
        ),
        ["aws_s3_bucket.web: the plan deletes a bucket."],
    )
    assert "**1 to add, 1 to change, 1 to destroy.**" in text
    assert "| `-/+` | `aws_s3_bucket.web` |" in text
    assert "aws_route53_record.edge" not in text
    assert "❌ aws_s3_bucket.web: the plan deletes a bucket." in text


def test_summary_without_changes() -> None:
    text = summary(plan(), [])
    assert "**No changes.**" in text
    assert "✅" in text


def test_main_writes_summary_and_fails_on_violations(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(plan(change("aws_s3_bucket.web", "aws_s3_bucket", ["delete"]))),
        encoding="utf-8",
    )
    summary_path = tmp_path / "summary.md"
    assert main(["plan_check.py", str(plan_path), str(summary_path)]) == 1
    assert "deletes a bucket" in summary_path.read_text(encoding="utf-8")


def test_main_passes_clean_plan(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan()), encoding="utf-8")
    assert main(["plan_check.py", str(plan_path)]) == 0
