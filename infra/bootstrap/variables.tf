variable "alert_email" {
  description = "Address that receives GuardDuty and Access Analyzer findings. Personal, so it stays out of git: set it in terraform.tfvars (ignored) or TF_VAR_alert_email."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$", var.alert_email))
    error_message = "alert_email must be an email address."
  }
}
