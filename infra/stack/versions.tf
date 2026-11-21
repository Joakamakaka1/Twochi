# The prod stack: edge, api and what follows. Applied only by the pipeline, from the
# `prod` environment with twochi-apply. It holds no secret in its state (ADR 0003).

terraform {
  required_version = "1.17.2"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.73.0"
    }
  }

  # Partial configuration: the bucket comes from -backend-config, out of the repository.
  backend "s3" {
    key          = "stack/terraform.tfstate"
    region       = "eu-west-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "eu-west-1"

  default_tags {
    tags = {
      Project   = "twochi"
      ManagedBy = "terraform/stack"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  account_id       = data.aws_caller_identity.current.account_id
  domain           = "twochi.jcvstro.dev"
  artifacts_bucket = "twochi-artifacts-${local.account_id}"

  # Created by infra/bootstrap. Built here rather than read: bootstrap's IAM is
  # off-limits to twochi-apply.
  workload_boundary_arn = "arn:aws:iam::${local.account_id}:policy/twochi-workload-boundary"
}

# Created by infra/bootstrap.
data "aws_route53_zone" "twochi" {
  name = local.domain
}
