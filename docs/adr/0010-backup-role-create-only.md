# 0010. El rol de backups solo crea volcados, desde el entorno `backup`

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
- Su única política permite `s3:PutObject` en `twochi-backups-<cuenta>/*` solo cuando la petición lleva `If-None-Match` (condición `Null` sobre `s3:if-none-match` a `false`). Con `If-None-Match: *`, S3 rechaza la subida si la clave ya existe, así que el rol crea volcados pero nunca pisa uno.
- Sin lectura, sin listado y sin borrado. Restaurar es cosa de una persona con su usuario de administración.
- `twochi-backup` entra en la lista de IAM protegida de `bootstrap`: `twochi-apply` no puede cambiar su confianza ni sus políticas.

## Consecuencias

- Las subidas son un solo `PUT` (`aws s3api put-object --if-none-match '*'`), con un límite de 5 GB que esta base no se acerca a tocar. `CreateMultipartUpload` y `UploadPart` no llevan la cabecera, así que una subida por partes falla con `AccessDenied`.
- Cada volcado necesita una clave nueva, con fecha y hora. Repetir una clave el mismo día falla con `412 Precondition Failed`, que es lo que se quiere.
- Si IAM no evaluara la clave de condición, la política no permitiría nada: el primer volcado fallaría a la vista, nunca en silencio. Tras el `apply`, el simulador de políticas de IAM lo comprueba sin tocar el bucket.
- Crear el entorno `backup` y sus secretos (`AWS_BACKUP_ROLE_ARN` y `BACKUPS_BUCKET`) es un paso posterior al `apply` de `bootstrap`.
