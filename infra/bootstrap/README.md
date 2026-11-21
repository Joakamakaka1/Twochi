# infra/bootstrap

Lo que debe existir antes de que corra el pipeline: el bucket de estado, la zona `twochi.jcvstro.dev`, el proveedor OIDC de GitHub, los roles `twochi-plan` y `twochi-apply` y el límite de permisos de los roles del stack. Se aplica una vez, a mano, con tu usuario de administración. Es la única carpeta con recursos que no crea el pipeline.

| Recurso | Para qué |
| --- | --- |
| `twochi-tfstate-<cuenta>` | Estado de `bootstrap` y del stack: privado, versionado, cifrado, solo por TLS y con bloqueo nativo de S3. `prevent_destroy` |
| `twochi.jcvstro.dev` en Route 53 | Zona del dominio, delegada desde Cloudflare. `prevent_destroy`. Ver [ADR 0002](../../docs/adr/0002-route53-subzone-delegated-from-cloudflare.md) |
| `twochi-artifacts-<cuenta>` | Zips de las Lambdas, con nombre por hash. Existe antes del stack porque el zip se sube antes del `apply` |
| Proveedor OIDC | GitHub Actions entra sin claves de AWS |
| `twochi-plan` | `ReadOnlyAccess` para `terraform plan` en los PR. Confía en `pull_request` del `sub` inmutable del repositorio |
| `twochi-apply` | Escribe el stack, solo desde el entorno `prod`. Nombres `twochi-*`, roles con el límite obligatorio y sin alcance sobre `bootstrap` |
| `twochi-workload-boundary` | Techo de permisos de cada rol que crea el stack |

Los dos roles de CI comparten tres barreras: solo `eu-west-1`, `us-east-1` y `eu-north-1` (GuardDuty, en todas); sin leer `/twochi/*` de SSM ni descifrar con KMS; y `Deny` de `s3:GetObject` en los buckets de backups y de dataset.

## Primer apply

Con tu usuario de administración, en otra terminal, fuera del alcance de la IA:

1. `aws login`.
2. Estado local la primera vez: el bucket aún no existe. Crea `backend_override.tf` (está en `.gitignore`):

   ```hcl
   terraform {
     backend "local" {}
   }
   ```

3. `terraform init`, `terraform plan -out=bootstrap.tfplan`, lee el plan y `terraform apply bootstrap.tfplan`.
4. Borra `backend_override.tf` y lleva el estado al bucket: `terraform init -migrate-state -backend-config="bucket=$(terraform output -raw state_bucket)"`. Después, borra el `terraform.tfstate` local y `bootstrap.tfplan`.

## Después del apply

- En Cloudflare, los registros `NS` de `twochi` con los valores de `terraform output zone_name_servers` (TWO-14).
- En GitHub, como variables (no son secretos): `AWS_PLAN_ROLE_ARN` y `TF_STATE_BUCKET` en el repositorio, y `AWS_APPLY_ROLE_ARN` en el entorno `prod`.

## Cambios posteriores

Un cambio aquí es un PR de zona delicada y otro `plan` y `apply` tuyos, con `-backend-config="bucket=..."` en el `init`. El pipeline nunca aplica esta carpeta.

Los permisos de `twochi-apply` van por servicio: el primer `apply` del stack dirá qué falta. Se añade en su propio PR, acotado a la cuenta y a `twochi-*`, nunca con `*` como recurso salvo las acciones que no admiten otro.
