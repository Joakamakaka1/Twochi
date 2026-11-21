# infra/bootstrap

Lo que debe existir antes de que corra el pipeline y lo que no debe estar al alcance del stack: los buckets de larga vida, la zona `twochi.jcvstro.dev`, el proveedor OIDC de GitHub, los roles `twochi-plan` y `twochi-apply`, el límite de permisos de los roles del stack, dos protecciones de cuenta y la detección de amenazas con sus avisos. Se aplica a mano, con tu usuario de administración. El pipeline nunca aplica esta carpeta.

| Recurso | Para qué |
| --- | --- |
| `twochi-tfstate-<cuenta>` | Estado de `bootstrap` y del stack, con bloqueo nativo de S3. Nunca guarda secretos ([ADR 0003](../../docs/adr/0003-secrets-out-of-terraform-state.md)) |
| `twochi-artifacts-<cuenta>` | Zips de las Lambdas, con nombre por hash. Existe antes del stack porque el zip se sube antes del `apply` |
| `twochi-backups-<cuenta>` | Volcados diarios de la base, caducan a los 30 días |
| `twochi-dataset-<cuenta>` | Dataset dorado y muestras de estilo: datos reales, nunca en git |
| `twochi.jcvstro.dev` en Route 53 | Zona del dominio, con un CAA que autoriza a ACM, delegada desde Cloudflare. Ver [ADR 0002](../../docs/adr/0002-route53-subzone-delegated-from-cloudflare.md) |
| Proveedor OIDC | GitHub Actions entra sin claves de AWS |
| `twochi-ci-read` | Lecturas de los servicios del stack, y nada más. Sustituye a `ReadOnlyAccess`, que también lee contacto, impuestos, pagos, facturas y CloudTrail de la cuenta |
| `twochi-plan` | `twochi-ci-read` para `terraform plan -lock=false` en los PR. Confía en `pull_request` del `sub` inmutable del repositorio |
| `twochi-apply` | Escribe el stack, solo desde el entorno `prod` (tu aprobación, solo desde `main`) |
| `twochi-workload-boundary` | Techo de permisos de cada rol que crea el stack |
| Bloqueo de acceso público de la cuenta | Ningún bucket puede hacerse público, diga lo que diga una política |
| `ExternalAccess-6KkUmMA8mfdV` | Access Analyzer: detecta si una política abre algo a otra cuenta. AWS admite uno por cuenta y región; este quedó de un proyecto anterior y `bootstrap` lo adopta con un `import`, con su nombre, porque renombrarlo lo recrea |
| GuardDuty | Un detector en cada región habilitada, con S3 y la red de las Lambdas; el resto de planes, desactivados ([ADR 0006](../../docs/adr/0006-detection-in-bootstrap.md)) |
| `twochi-guardduty-forward` y `twochi-findings-forwarder` | Regla en cada región salvo `eu-west-1` y su rol: llevan los hallazgos al bus `default` de `eu-west-1` |
| `twochi-guardduty-findings`, `twochi-access-analyzer-findings` y `twochi-security-alerts` | Reglas centrales y tema: los hallazgos de GuardDuty y los activos de Access Analyzer llegan a tu correo |

Los cuatro buckets usan el módulo `infra/modules/private_bucket`: privados, cifrados, solo por TLS y con `prevent_destroy`.

## Qué no pueden hacer los roles de CI

Los logs de Actions son públicos y un `plan` ejecuta el código del PR, así que lo que estos roles puedan leer puede acabar publicado.

- Los dos: solo leen los servicios del stack, y GuardDuty no está entre ellos; solo `eu-west-1`, `us-east-1` y `eu-north-1`; ni el estado de `bootstrap` ni quién recibe los avisos de seguridad; ningún parámetro de SSM ni secreto, y `kms:Decrypt` solo cuando Lambda descifra el environment de una función `twochi-*`, que nunca lleva secretos ([ADR 0005](../../docs/adr/0005-ci-reads-lambda-environment.md)); ningún objeto fuera de los buckets de estado y de artefactos, y ni siquiera la lista de claves de backups y dataset; ni líneas de log, anomalías, mensajes de SQS ni el informe de credenciales.
- `twochi-apply`, además:
  - no asume ningún rol ni toca el IAM de `bootstrap`, salvo para leerlo;
  - en los buckets de `bootstrap` solo lee, escribe y borra objetos (nunca en `bootstrap/*` ni en los de datos) y lista;
  - no escribe nada de GuardDuty, no toca el tema ni las reglas de los avisos de seguridad (solo los lee) y no borra la zona ni Access Analyzer;
  - no crea Function URL públicas, no da permiso de invocación a nada que no sea CloudFront, EventBridge, Scheduler o SNS, no saca logs a otra cuenta, no abre colas ni temas a otras cuentas y solo suscribe correos;
  - no cambia los registros CAA, NS ni DS de la zona.
- Los roles que crea el stack llevan el límite de permisos: solo el código que corre en una Lambda lee parámetros u objetos. Un rol cuya confianza se abriera a otra cuenta no obtendría eso, y Access Analyzer lo detecta.
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
- En GitHub, como secretos, para que los logs públicos los enmascaren (llevan el ID de la cuenta): `AWS_PLAN_ROLE_ARN`, `TF_STATE_BUCKET` y `TF_ARTIFACTS_BUCKET` en el repositorio, y `AWS_APPLY_ROLE_ARN` en el entorno `prod`. Con ellos y la variable `SUPABASE_URL` (ver `infra/stack`), el `plan` de los PR y el despliegue en `main` dejan de saltarse.

## Cambios posteriores

Un cambio aquí es un PR de zona delicada y otro `plan` y `apply` tuyos, con `-backend-config="bucket=..."` en el `init`.

El `plan` pide `alert_email`, el correo de los avisos de seguridad. Es personal y no entra en git: ponlo en `terraform.tfvars` (ignorado) como `alert_email = "..."` o en `TF_VAR_alert_email`. Tras el primer `apply` con él, AWS envía un correo de confirmación: hasta que lo confirmes, no llega ningún aviso.

No pulses el enlace del correo. Una suscripción confirmada así se puede dar de baja sin credenciales, con solo su ARN, y el `Deny` de `twochi-apply` no lo impide. Confírmala con tu admin, pasando el `Token` que va en la URL del enlace:

```sh
aws sns confirm-subscription --region eu-west-1 --topic-arn <ARN de twochi-security-alerts> --token <token> --authenticate-on-unsubscribe true
aws sns get-subscription-attributes --region eu-west-1 --subscription-arn <ARN devuelto>   # ConfirmationWasAuthenticated = true
```

Si algo confirma antes por el enlace, como un escáner de correo, borra la suscripción y vuelve a aplicar.

Para comprobar el camino entero, crea hallazgos de muestra con `aws guardduty create-sample-findings` en `eu-west-1`, en otra región por defecto y en `eu-south-2`, que es opt-in. Si no llega un correo, mira `FailedInvocations` de la regla de reenvío de esa región y de la central. Los hallazgos de Access Analyzer que ya estaban activos antes del `apply` no generan evento: revísalos una vez en la consola.

Los permisos de `twochi-apply` van por servicio: el primer `apply` del stack dirá qué falta. Se añade en su propio PR, acotado a la cuenta y a `twochi-*`, nunca con `*` como recurso salvo las acciones que no admiten otro.
