Closes TWO-21 once deployed and verified.

## What

- `infra/stack/functions/web_routes.js`: a viewer-request CloudFront Function (`cloudfront-js-2.0`) on the **default** behavior. It rewrites any path whose last segment has no extension to `/index.html`, so PWA deep links such as `/pet` load the app instead of S3's 403 XML. Files with an extension pass unchanged.
- `/api/*` keeps its own behavior, with no function and no custom error responses, so its `application/problem+json` errors are untouched. Custom error responses were ruled out because they apply to the whole distribution.
- `/api` without a trailing slash, or in another case (`/API/...`), misses the case-sensitive `/api/*` pattern. The function leaves those paths alone, so an API client never gets the PWA with a 200.
- `infra/stack/edge.tf`: `aws_cloudfront_function.web_routes` (`publish = true`) and its `function_association` on `default_cache_behavior`.
- Tests: `node:test` in `web_routes.test.mjs`, run by `just check-infra`. The CI `infra` job now installs `node` through mise, pinned in `mise.toml`.
- Flat-rate Free plan: CloudFront Functions are included ("Serverless edge compute"), but KeyValueStore and network calls from functions are not, and this function uses neither ([AWS docs](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/flat-rate-pricing-plan.html)).

## Evidence

- `just check` passes locally: Python 103 passed, web 8 passed, actionlint, zizmor, terraform fmt/validate, tflint, and `node --test` 3/3.
- The test was red first against an identity handler (`'/' !== '/index.html'`), then green.
- Two subagent reviews, one for correctness and one for security, found nothing important. Their nits are addressed (`/api` guard and the dotted-segment test) or listed below.

**Before** (prod today, through DoH and `curl --resolve`):

```
/pet             403 application/xml   <Error><Code>AccessDenied</Code>…
/api/no-existe   404 application/problem+json   {"type":"about:blank","title":"Request failed","status":404,"code":"not_found"}
/api/health      200 application/json
```

**Expected plan:** 1 to add (`aws_cloudfront_function.web_routes`), 1 to change in place (`aws_cloudfront_distribution.edge`, the new `function_association` only), 0 to destroy. The `plan` job's comment is checked against this.

**After the deploy:** `aws cloudfront test-function` on the LIVE stage (`/pet` → `/index.html`), the association read from the distribution, and curl: `/api/no-existe` → 404 problem+json. `/pet` still gets S3's 403 until the front is uploaded, because the bucket is empty.

## Merge risk

Low. The change only touches the default (web) behavior, and the bucket is empty today. Limits that come with the design:

- A front route cannot end in a segment with a dot (`/u/john.doe` goes to S3). This is recorded in `infra/stack/README.md`.
- Every deep link shares the cached `/index.html`. The front deploy must set a short `Cache-Control` on `index.html` or invalidate it, as CI/CD e IaC already plans. That was already true for `/`.
- A change to `web_routes.test.mjs` alone also triggers a stack deploy, with a no-op plan.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
