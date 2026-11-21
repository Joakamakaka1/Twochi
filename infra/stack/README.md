# infra/stack

El stack de `prod`. Hoy: el borde (CloudFront, WAF, certificado y registros DNS), la Lambda `api` con su Function URL y el bucket del front. Lo aplica solo el pipeline, desde el entorno `prod` y con `twochi-apply`; nunca a mano.

- Decisiones: [ADR 0004](../../docs/adr/0004-edge-function-url-with-oac-and-plan-b.md) para el borde y su plan B, y [ADR 0003](../../docs/adr/0003-secrets-out-of-terraform-state.md) para lo que el estado no puede guardar.
- Variables que da el pipeline: `api_package_key` (el zip ya subido al bucket de artefactos) y `supabase_url`, que sale de la variable de repositorio `SUPABASE_URL`: es pública, el front también la lleva.
- Backend: `terraform init -backend-config="bucket=<bucket de estado>"`.

## Pipeline

- En cada PR que toque `infra/` o el código de las Lambdas, el job `plan` de `ci.yml` corre `terraform plan -lock=false` con `twochi-plan`, deja el resumen en un comentario del PR y falla si el plan trae `*` como recurso de un `Allow` de IAM, una política gestionada de AWS o el borrado de un bucket (`.github/scripts/plan_check.py`).
- En `main`, `deploy.yml` construye el zip arm64 de `api` sin rol de AWS, lo sube al bucket de artefactos con el hash de sus entradas como nombre, recalcula el plan con `-out`, pasa las mismas guardas y aplica ese fichero desde el entorno `prod`, que espera tu aprobación. Termina con `/api/health` por `aws lambda invoke`, sin cruzar el borde.
- Solo despliega si algo que lee el stack cambió desde el último despliegue con éxito en `prod`; `workflow_dispatch` despliega igualmente.
- Sin los secretos `AWS_PLAN_ROLE_ARN`, `TF_STATE_BUCKET` y `TF_ARTIFACTS_BUCKET`, el secreto de entorno `AWS_APPLY_ROLE_ARN` y la variable `SUPABASE_URL`, los dos jobs se saltan con un aviso.
- En local, `just package api` deja el mismo zip en `dist/`.
- La distribución está suscrita al plan flat-rate Free desde el 2026-11-21 (TWO-15). La suscripción se hizo a mano porque el recurso de Terraform aún no existe. Ese plan no admite clases de precio, así que `price_class` es `PriceClass_All`: si Terraform pidiera otra, revertiría lo que puso la suscripción.
- Enlaces profundos de la PWA: la CloudFront Function `twochi-web-routes` (`functions/web_routes.js`), en el comportamiento por defecto, sirve `index.html` a toda ruta cuyo último segmento no tenga extensión; los ficheros pasan tal cual. Por eso ninguna ruta del front puede acabar en un segmento con punto (`/u/john.doe` se pediría a S3), y `/api` sin barra final o con otra capitalización tampoco se reescribe: un cliente de la API recibe un error, nunca la PWA. No se usan respuestas de error personalizadas porque valen para toda la distribución y reescribirían los `problem+json` de `/api/*`. El plan Free admite CloudFront Functions, pero sin KeyValueStore ni llamadas de red. Sus tests corren con `node --test` en `just check-infra`.
- Cada rol que se cree aquí lleva `permissions_boundary = local.workload_boundary_arn`; sin él, `twochi-apply` no puede crearlo.
