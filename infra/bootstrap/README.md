# infra/bootstrap

Lo que debe existir antes de que corra el pipeline y lo que no debe estar al alcance del stack: los buckets de larga vida, la zona `twochi.jcvstro.dev`, el proveedor OIDC de GitHub, los roles `twochi-plan` y `twochi-apply`, el límite de permisos de los roles del stack y dos protecciones de cuenta. Se aplica a mano, con tu usuario de administración. El pipeline nunca aplica esta carpeta.

| Recurso | Para qué |
| --- | --- |
| `twochi-tfstate-<cuenta>` | Estado de `bootstrap` y del stack, con bloqueo nativo de S3. Nunca guarda secretos ([ADR 0003](../../docs/adr/0003-secrets-out-of-terraform-state.md)) |
| `twochi-artifacts-<cuenta>` | Zips de las Lambdas, con nombre por hash. Existe antes del stack porque el zip se sube antes del `apply` |
| `twochi-backups-<cuenta>` | Volcados diarios de la base, caducan a los 30 días |
| `twochi-dataset-<cuenta>` | Dataset dorado y muestras de estilo: datos reales, nunca en git |
| `twochi.jcvstro.dev` en Route 53 | Zona del dominio, con un CAA que autoriza a ACM, delegada desde Cloudflare. Ver [ADR 0002](../../docs/adr/0002-route53-subzone-delegated-from-cloudflare.md) |
| Proveedor OIDC | GitHub Actions entra sin claves de AWS |
| `twochi-plan` | `ReadOnlyAccess` para `terraform plan` en los PR. Confía en `pull_request` del `sub` inmutable del repositorio |
| `twochi-apply` | Escribe el stack, solo desde el entorno `prod` (tu aprobación, solo desde `main`) |
| `twochi-workload-boundary` | Techo de permisos de cada rol que crea el stack |
| Bloqueo de acceso público de la cuenta | Ningún bucket puede hacerse público, diga lo que diga una política |
| `twochi-external-access` | Access Analyzer: avisa si una política abre algo a otra cuenta |

Los cuatro buckets usan el módulo `infra/modules/private_bucket`: privados, cifrados, solo por TLS y con `prevent_destroy`.

## Qué no pueden hacer los roles de CI

Los logs de Actions son públicos y un `plan` ejecuta el código del PR, así que lo que estos roles puedan leer puede acabar publicado.

- Los dos: solo `eu-west-1`, `us-east-1` y `eu-north-1` (GuardDuty, en todas); ningún parámetro de SSM, secreto ni `kms:Decrypt`; ningún objeto fuera de los buckets de estado y de artefactos; ni líneas de log ni mensajes de SQS.
- `twochi-apply`, además: no asume ningún rol, no toca `bootstrap` ni la configuración de sus buckets, no escribe el estado de `bootstrap` ni los datos, no purga versiones y no borra la zona, GuardDuty ni Access Analyzer. Los roles que crea llevan el límite de permisos.
- El control de verdad es tu aprobación en `prod`: quien aplica cambia lo que corre en producción.

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
- En GitHub, como secretos, para que los logs públicos los enmascaren (llevan el ID de la cuenta): `AWS_PLAN_ROLE_ARN`, `TF_STATE_BUCKET` y `TF_ARTIFACTS_BUCKET` en el repositorio, y `AWS_APPLY_ROLE_ARN` en el entorno `prod`.

## Cambios posteriores

Un cambio aquí es un PR de zona delicada y otro `plan` y `apply` tuyos, con `-backend-config="bucket=..."` en el `init`.

Los permisos de `twochi-apply` van por servicio: el primer `apply` del stack dirá qué falta. Se añade en su propio PR, acotado a la cuenta y a `twochi-*`, nunca con `*` como recurso salvo las acciones que no admiten otro.
