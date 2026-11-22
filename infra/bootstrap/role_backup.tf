# twochi-backup: uploads the database dumps, only from jobs in the `backup` environment,
# which only runs from `main` and needs no approval, so the daily job runs on its own
# (ADR 0011). The deploy's dump before `db push` runs as its own job in that environment.
# Create that environment, with its branch policy, before applying: GitHub creates an
# environment a job names on the fly, with no policy, so any branch could use the role.
#
# It only creates objects: no reads, no listing, no deletes. Restoring stays a person's
# job, with their own credentials. The bucket keeps old versions for one day only, so an
# overwrite would destroy a dump within a day: every upload must send If-None-Match: *,
# which S3 refuses when the key already exists. CreateMultipartUpload and UploadPart
# carry no such header, so uploads are single PUTs from a file (`aws s3api put-object
# --if-none-match '*'`, up to 5 GB); `aws s3 cp` sends no such header and is denied.
# Customer-provided keys and cold storage classes are refused too: either would leave
# a dump a person cannot restore at once.

data "aws_iam_policy_document" "backup_put" {
  statement {
    sid       = "CreateDumpsOnly"
    actions   = ["s3:PutObject"]
    resources = ["arn:aws:s3:::${local.backups_bucket}/*"]

    # An absent header fails StringEquals, so the policy fails closed.
    condition {
      test     = "StringEquals"
      variable = "s3:if-none-match"
      values   = ["*"]
    }

    condition {
      test     = "Null"
      variable = "s3:x-amz-server-side-encryption-customer-algorithm"
      values   = ["true"]
    }

    condition {
      test     = "StringEqualsIfExists"
      variable = "s3:x-amz-storage-class"
      values   = ["STANDARD"]
    }
  }
}

resource "aws_iam_role" "backup" {
  name                 = "twochi-backup"
  description          = "Uploads Twochi database dumps, from the backup environment."
  assume_role_policy   = data.aws_iam_policy_document.github_trust["backup"].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "backup_put" {
  name   = "twochi-backup-put"
  role   = aws_iam_role.backup.id
  policy = data.aws_iam_policy_document.backup_put.json
}
