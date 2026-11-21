# infra/stack

El stack de `prod`. Hoy: el borde (CloudFront, WAF, certificado y registros DNS), la Lambda `api` con su Function URL y el bucket del front. Lo aplica solo el pipeline, desde el entorno `prod` y con `twochi-apply`; nunca a mano.

- Decisiones: [ADR 0004](../../docs/adr/0004-edge-function-url-with-oac-and-plan-b.md) para el borde y su plan B, y [ADR 0003](../../docs/adr/0003-secrets-out-of-terraform-state.md) para lo que el estado no puede guardar.
- Variables que da el pipeline: `api_package_key` (el zip ya subido al bucket de artefactos) y `supabase_url`.
- Backend: `terraform init -backend-config="bucket=<bucket de estado>"`.
- Tras el primer `apply`, la suscripción al plan flat-rate Free es manual (TWO-15): el recurso de Terraform aún no existe.
- Cada rol que se cree aquí lleva `permissions_boundary = data.aws_iam_policy.workload_boundary.arn`; sin él, `twochi-apply` no puede crearlo.
