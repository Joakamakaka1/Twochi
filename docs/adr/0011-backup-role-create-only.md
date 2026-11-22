# 0011. El rol de backups solo crea volcados, desde el entorno `backup`

- Estado: aceptada
- Fecha: 2026-11-22
- Completa AWS, «Conexiones y permisos», y CI/CD e IaC, «Base de datos»: el documento pide un volcado diario y otro justo antes de `db push`, pero no dice con qué rol se suben

## Contexto

Ningún rol podía escribir los volcados: `twochi-plan` solo lee, y `twochi-apply` tiene denegada la escritura en el bucket de backups para que un `apply` aprobado no toque datos reales.

Dos detalles pesan en el diseño:

- Un `sub` de OIDC por rama (`ref:refs/heads/main`) lo comparte cualquier job que corra en `main`: el CI de cada `push`, cualquier `workflow_dispatch` y los workflows que vengan después.
- El bucket de backups es versionado, pero borra las versiones antiguas al día siguiente, para que «olvidar» se cumpla en 30 días. Un rol con `s3:PutObject` a secas que conozca la clave de un volcado lo destruye con una sola subida.

## Decisión

- Un rol `twochi-backup` en `bootstrap` confía en un solo `sub`: `environment:backup`. En GitHub, ese entorno solo admite la rama `main` y no pide revisores, para que el job diario corra solo. El volcado previo a `db push` del despliegue es un job propio con ese entorno, antes del job de `prod`.
- Su única política permite `s3:PutObject` en `twochi-backups-<cuenta>/*` solo cuando la petición lleva `If-None-Match: *` (`StringEquals` sobre `s3:if-none-match`). Con esa cabecera, S3 rechaza la subida si la clave ya existe, así que el rol crea volcados pero nunca pisa uno.
- La misma política rechaza las claves de cifrado del cliente (SSE-C) y cualquier clase de almacenamiento que no sea `STANDARD`: con cualquiera de las dos, una persona no podría restaurar el volcado al momento.
- Sin lectura, sin listado y sin borrado. Restaurar es cosa de una persona con su usuario de administración.
- `twochi-backup` entra en la lista de IAM protegida de `bootstrap`: `twochi-apply` no puede cambiar su confianza ni sus políticas.

## Consecuencias

- Las subidas son un solo `PUT` desde un fichero (`aws s3api put-object --if-none-match '*'`), con un límite de 5 GB que esta base no se acerca a tocar. `CreateMultipartUpload` y `UploadPart` no llevan la cabecera, así que una subida por partes falla con `AccessDenied`, también un `pg_dump` por tubería a `aws s3 cp -`.
- Cada volcado necesita una clave nueva, con fecha y hora. Repetir una clave el mismo día falla con `412 Precondition Failed`, que es lo que se quiere.
- Si IAM no evaluara la clave de condición, la política no permitiría nada: el primer volcado fallaría a la vista, nunca en silencio. El simulador de políticas no lo demuestra, porque solo evalúa las claves que se le pasan. Lo demuestra el primer job de volcado: una subida sin cabecera da 403 y repetir la misma clave da 412.
- El entorno `backup` se crea antes del `apply`: GitHub crea al vuelo, sin política de rama, el entorno que nombra un job, y en ese hueco cualquier rama podría asumir el rol. Sus secretos (`AWS_BACKUP_ROLE_ARN` y `BACKUPS_BUCKET`) llegan después del `apply`.
- El rol ata a un entorno, no a un workflow: cualquier job de `main` que declare `backup` lo asume. Solo lo declaran los jobs de volcado, y la revisión de cada PR lo vigila.
- Queda abierto para el job de volcado: la credencial de la base que necesita `pg_dump` vive en el entorno `backup`, que no pide aprobación. Debe ser de solo lectura y se decide en TWO-39, con TWO-10.
