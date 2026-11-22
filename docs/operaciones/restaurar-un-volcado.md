# Volcados de la base: puesta en marcha y restauración

El workflow `backup` vuelca la base de producción cada día a las 03:17 UTC en `twochi-backups-<cuenta>`. Los volcados caducan a los 30 días. Por qué y cómo, en [ADR 0011](../adr/0011-backup-role-create-only.md) y [ADR 0012](../adr/0012-dump-with-read-only-role.md).

## Puesta en marcha

Una sola vez, cuando la migración `20261122000600_add_backup_role.sql` ya esté en producción (TWO-32). Hasta entonces, el volcado diario falla en rojo cada día.

1. Tú: crea en Bitwarden, en `twochi-prod`, el secreto `BACKUP_DB_PASSWORD` con una contraseña generada.
2. Tú: ponla en la base. Conéctate como `postgres` y usa `\password`, que calcula el hash en tu máquina: la contraseña no queda en el historial del editor SQL de Supabase ni en los logs de Postgres. El host del pooler sale del panel (Connect, «Session pooler»), y `psql` te pide la contraseña de `postgres` y después la nueva dos veces.

   ```powershell
   docker run --rm -it -v "${PWD}/packages/data/src/twochi_data:/ca:ro" postgres:17.12-trixie@sha256:223efeb196329b55b3b9a13db144956411dbc18e727e59f681c3e0aede6475cf psql "host=<pooler> port=5432 dbname=postgres user=postgres.<ref> sslmode=verify-full sslrootcert=/ca/supabase-root-2021-ca.pem" -c "\password twochi_backup"
   ```

3. Tú: cópiala al entorno `backup`. `gh` la pide sin mostrarla:

   ```powershell
   gh secret set BACKUP_DB_PASSWORD --env backup --repo Joakamakaka1/Twochi
   ```

4. La variable `SUPABASE_POOLER_HOST` del repositorio, con el host del paso 2. No es secreta: la puede poner la IA con tu visto bueno.
5. Lanza un volcado (`gh workflow run backup.yml`) y comprueba el log:
   - una línea `Dump uploaded:` con la clave, la hora, el tamaño y el SHA-256;
   - la línea `Guard holds: repeat 412, no If-None-Match 403, SSE-C 403. twochi_backup runs no SECURITY DEFINER function.`

   Es la comprobación real de la guarda de ADR 0011, que el simulador de IAM no puede hacer. Cada volcado la repite.

## Si falla

El run sale en rojo y GitHub manda un correo a quien cambió la línea del `cron` por última vez. El log dice qué pasó:

- `Missing in the backup environment`: falta un secreto o una variable.
- `pg_dump failed`: conexión, contraseña o TLS. El error de `pg_dump` va justo antes.
- `The upload of … failed`: el código de S3 y el mensaje de la CLI de AWS van en la misma línea.
- `412`: la clave ya existía. Su parte aleatoria hace imposible que pase por azar: alguien la creó antes. Trátalo como un incidente: revisa los workflows de `main` y el bucket.
- `backup guard`: alguna sonda no dio lo que debía, así que la política de `twochi-backup` no protege lo que dice, o `twochi_backup` puede ejecutar una función `SECURITY DEFINER` en producción, y con ella escribir. El volcado de ese día sí se subió, pero hay que corregirlo antes del siguiente: revisar el rol de IAM, o quitar a `PUBLIC` el permiso de ejecutar esa función. Si su dueño es un rol `supabase_*`, `postgres` no puede hacerlo: se consulta con Supabase. Si dice que la lista no se pudo sacar, el error de `psql` va justo antes.

GitHub desactiva los workflows programados tras 60 días sin actividad en un repositorio público. Si pasa, actívalo de nuevo desde la pestaña Actions.

## Restaurar

Restaurar es cosa tuya, con tu usuario de administración (`aws login`): ningún rol de CI ni el usuario de la IA leen el bucket.

### 1. Elige el volcado por el log, no por el bucket

No tomes «la clave más reciente». Un job comprometido en `main` podría subir un volcado falso con una clave posterior.

1. En Actions, abre el workflow `backup` (o `deploy`, para el volcado previo a `db push`) y elige el run del día que quieres. Si sospechas que `main` se comprometió, elige uno de antes. Debe ser un run de `main`: de `backup`, por su `schedule` o por un `workflow_dispatch` tuyo; de `deploy`, por un `push` a `main` o por un `workflow_dispatch` tuyo.
2. Copia su línea `Dump uploaded:`, con la clave, la hora, los bytes y el SHA-256. El `run<id>` de la clave debe ser el id de ese run.
3. Comprueba el código que corrió: el log solo vale si lo escribió el código revisado. Toma el commit del run (`gh run view <id> --json headSha`) y mira que el job de volcado no cambió desde un commit que revisaste: `git diff <revisado> <headSha> -- .github/workflows/db-dump.yml .github/workflows/backup.yml .github/workflows/deploy.yml .github/scripts/db_dump.py .github/scripts/supabase_dump.sh` debe salir vacío, o con cambios que reconozcas de PR fusionados. Un commit malicioso en `main` corre dentro del mismo run programado y podría escribir una línea `Dump uploaded:` que cuadre con un volcado falso.
4. Lista el bucket alrededor de esa fecha:

   ```powershell
   aws s3api list-objects-v2 --bucket twochi-backups-<cuenta> --prefix daily/2026 --query "Contents[].[Key,LastModified,Size]" --output table
   ```

   Una clave que no salga en el log de ningún run es una alarma, igual que cualquier objeto bajo `probes/`.

### 2. Comprueba que es ese volcado

```powershell
aws s3api head-object --bucket twochi-backups-<cuenta> --key <clave>
aws s3api get-object --bucket twochi-backups-<cuenta> --key <clave> dump.tar.gz
(Get-FileHash dump.tar.gz -Algorithm SHA256).Hash.ToLower()
```

`ContentLength` debe coincidir con los bytes del log, `LastModified` con su hora (como mucho, un minuto después) y el hash con su SHA-256. Si algo no cuadra, no lo uses. Después, `tar -xzf dump.tar.gz` deja `roles.sql`, `schema.sql` y `data.sql`.

### 3. Restaura en un proyecto nuevo

Primero, siempre, en un proyecto de prueba de Supabase (el plan gratuito admite dos). Es la guía de Supabase ([restaurar con la CLI](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)), con TLS comprobado. Lánzalo desde la carpeta de los tres ficheros, con `<repo>` como la ruta de tu copia de Twochi. `psql` pide la contraseña de `postgres` del proyecto nuevo:

```powershell
docker run --rm -it -v "${PWD}:/dump:ro" -v "<repo>/packages/data/src/twochi_data:/ca:ro" postgres:17.12-trixie@sha256:223efeb196329b55b3b9a13db144956411dbc18e727e59f681c3e0aede6475cf psql "host=<pooler> port=5432 dbname=postgres user=postgres.<ref nuevo> sslmode=verify-full sslrootcert=/ca/supabase-root-2021-ca.pem" --single-transaction --variable ON_ERROR_STOP=1 --file /dump/roles.sql --file /dump/schema.sql --command "SET session_replication_role = replica" --file /dump/data.sql
```

Comprueba las filas de `app.couples`, `app.pets` y `auth.users` contra lo que esperas.

Si `psql` para en una línea de `roles.sql` o `schema.sql` que habla de `supabase_admin` o de `cli_login_postgres`, la guía de Supabase indica comentarla y repetir: son errores conocidos de ese camino.

### 4. Lo que el volcado no lleva

Si producción pasa al proyecto restaurado, hay que rehacer a mano:

- La configuración de Auth: el proveedor de Google, TOTP, los dos hooks y las altas cerradas (TWO-13, TWO-37). Las claves de API y el secreto de los JWT son nuevos, así que todas las sesiones se cierran.
- Las contraseñas de `twochi_api` y `twochi_backup`: `roles.sql` va sin contraseñas. Genera unas nuevas en Bitwarden.
- El historial de migraciones: `supabase_migrations` no va en el volcado. Antes del siguiente `db push`, marca como aplicadas las migraciones que existían en el commit del run (`supabase migration repair --status applied <versión>`), o `db push` intentará repetirlas todas.
- Las tablas de la publicación `supabase_realtime`, cuando las haya (el documento prevé `pet_needs` y `pet_events`): `schema.sql` no la toca. Añádelas de nuevo desde el panel o con SQL.
- `SUPABASE_URL`, `SUPABASE_POOLER_HOST` y los secretos que apuntan al proyecto.
- Las sesiones y los códigos de un solo uso de `auth`: no van en el volcado, así que cada persona inicia sesión de nuevo.
- Los ficheros de Storage y los datos de sus vector buckets. Twochi no los usa.

### 5. Borra las copias locales

Al terminar, borra `dump.tar.gz` y los tres `.sql` de tu disco. El bucket los olvida a los 30 días; tu disco, no.
