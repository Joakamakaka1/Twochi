variable "api_package_key" {
  description = "Key of the api zip in the artifacts bucket, named by the hash of uv.lock and the source."
  type        = string
}

variable "supabase_url" {
  description = "Supabase project URL, such as https://<ref>.supabase.co. Public: the front ships it too."
  type        = string

  validation {
    condition     = can(regex("^https://[a-z0-9]+\\.supabase\\.co$", var.supabase_url))
    error_message = "supabase_url must look like https://<ref>.supabase.co, without a trailing slash."
  }
}

variable "allowed_countries" {
  description = "Countries the WAF lets in (AWS, «Acceso por país»). Adding one is a change here and an apply."
  type        = list(string)
  default     = ["ES", "PL"]
}

variable "requests_per_ip_per_5_minutes" {
  description = "WAF rate limit per IP, in five-minute windows. A starting point: tune it with real traffic."
  type        = number
  default     = 300
}
