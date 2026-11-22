# twochi-backup: uploads the database dumps, only from jobs in the `backup` environment,
# which only runs from `main` and needs no approval, so the daily job runs on its own
# (ADR 0010). The deploy's dump before `db push` runs as its own job in that environment.
#
# It only creates objects: no reads, no listing, no deletes. Restoring stays a person's
# job, with their own credentials. The bucket keeps old versions for one day only, so an
# overwrite would destroy a dump within a day: every upload must send If-None-Match: *,
# which S3 refuses when the key already exists. CreateMultipartUpload and UploadPart
# carry no such header, so uploads are single PUTs (`aws s3api put-object
# --if-none-match '*'`, up to 5 GB).

data "aws_iam_policy_document" "backup_put" {
  statement {
    sid       = "CreateDumpsOnly"
    actions   = ["s3:PutObject"]
    resources = ["arn:aws:s3:::${local.backups_bucket}/*"]

    condition {
      test     = "Null"
      variable = "s3:if-none-match"
      values   = ["false"]
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
