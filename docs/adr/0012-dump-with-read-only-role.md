# 0012. El volcado entra con un rol propio de solo lectura y `pg_dump` fijado

- Estado: aceptada
- Fecha: 2026-11-22
- Completa [ADR 0011](0011-backup-role-create-only.md), que dejaba abierta la credencial de la base del job de volcado, y Datos y vectores, «Acceso», que no tenía fila para los volcados

## Contexto

El volcado diario corre en el entorno `backup`, que no pide aprobación para que el job corra solo. Cualquier credencial de la base que viva allí la puede usar cualquier job de `main` que declare ese entorno.

- `supabase db dump` siempre ejecuta `pg_dump --role "postgres"`. Con un rol que no pueda convertirse en `postgres` falla (`permission denied to set role "postgres"`, probado en local el 2026-11-22). Usarlo tal cual obligaría a dejar en `backup` la contraseña de `postgres`, que lo escribe todo.
- `pg_dump` desactiva la seguridad por filas y falla en cualquier tabla cuyas políticas oculten una fila: el rol necesita `BYPASSRLS`.
- Los runners `ubuntu-24.04` traen el cliente de Postgres 16, y `pg_dump` se niega a volcar un servidor más nuevo. Producción es Postgres 17.
- El token `ci-prod` de Bitwarden lee todo `twochi-prod` y es secreto del entorno `prod`, que pide aprobación. El plan gratuito de Bitwarden no deja crear una cuarta machine account.

## Decisión

- Un rol de Postgres propio, `twochi_backup`, por migración: `LOGIN BYPASSRLS`, miembro de `pg_read_all_data` y con `default_transaction_read_only = on`. No es dueño de nada ni tiene otra concesión, así que no puede escribir en ninguna tabla ni crear nada en ningún esquema, aunque la sesión quite el modo de solo lectura. Tres tests contra la base local lo vigilan: lee las filas de todas las parejas, escribir en tablas o esquemas, o cambiar sus propios atributos, da `permission denied`, y no puede ejecutar ninguna función `SECURITY DEFINER`. Lo que sí puede, como cualquier rol, está en las consecuencias.
- Su contraseña no entra en git. En local la pone el seed. En producción la elige una persona: se guarda en Bitwarden (`twochi-prod`) y se copia al secreto `BACKUP_DB_PASSWORD` del entorno `backup`. Es la única credencial de la base en ese entorno.
- La conexión no vive en un secreto. El job entra por Supavisor en modo sesión (puerto 5432, IPv4, como los runners) con el usuario `twochi_backup.<ref>`. El `<ref>` sale de la variable `SUPABASE_URL` y el host, de la variable `SUPABASE_POOLER_HOST`. El job fija `sslmode=verify-full` contra la raíz de Supabase ([ADR 0010](0010-postgres-tls-verify-full.md)): nada de lo que guarde un secreto puede rebajar la comprobación.
- `pg_dump` 17 corre en la imagen oficial `postgres`, fijada por digest. Saca los tres ficheros de `supabase db dump` (roles, esquema y datos con `COPY`) con las mismas opciones y filtros que la CLI 2.122.0, con tres diferencias:
  - sin `--role "postgres"`;
  - sin los datos de los vector buckets de Storage (`storage.buckets_vectors` y `storage.vector_indexes`). `postgres` no puede insertar en esas tablas, así que su `COPY`, aun vacío, aborta la restauración. La guía de Supabase para volcar y restaurar con la CLI ([Supabase](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)) las excluye igual, con `-x`, y Twochi no las usa;
  - sin los datos de las sesiones vivas ni de los códigos de un solo uso de `auth` (`refresh_tokens`, `sessions`, `mfa_amr_claims`, `mfa_challenges`, `one_time_tokens` y `flow_state`). Los refresh tokens se guardan en claro: con un volcado filtrado, alguien entraría en producción como cualquiera de los dos. Restaurar cierra todas las sesiones de todos modos.

  Comprobado en local: los tres ficheros coinciden con los de la CLI línea a línea, salvo los tokens aleatorios de `\restrict` y la versión de `pg_dump`. `data.sql` se restaura como `postgres` sobre una base recién migrada, con `ON_ERROR_STOP` y en una sola transacción, con las mismas filas en las ocho tablas comparadas.
- Los tres ficheros van en un solo objeto `.tar.gz`. La clave es `<tipo>/<AAAAMMDDTHHMMSSZ>-run<run id>-<32 hex aleatorios>.tar.gz`, con `daily` o `pre-deploy` como tipo. La parte aleatoria impide que un job comprometido cree de antemano las claves de los próximos días.
- Tras cada subida, el job prueba la guarda de ADR 0011 en el bucket real, no solo en el primer run:
  - repetir la misma clave con los mismos bytes debe dar 412;
  - una subida sin `If-None-Match` a una clave nueva debe dar 403;
  - una subida con SSE-C debe dar 403.

  Si la guarda funciona, ninguna sonda deja un objeto.
- En cada run, el job lista también las funciones `SECURITY DEFINER` que `twochi_backup` puede ejecutar en producción, y sale en rojo si hay alguna. `pg_read_all_data` abre todos los esquemas, así que una función así, de una extensión activada desde el panel por ejemplo, le dejaría escribir como su dueño. El test local solo ve las migraciones.
- Si falta un secreto o una variable, el job falla en rojo: no hay día sin copia que pase desapercibido. GitHub manda un correo a quien cambió la línea del `cron` por última vez.
- El job vive en un workflow reutilizable (`db-dump.yml`). Lo llama `backup.yml` cada día, y lo llamará `deploy.yml` antes de `db push` (TWO-32).

## Alternativas descartadas

- `supabase db dump` con la contraseña de `postgres`: una credencial con escritura total en un entorno sin aprobación.
- `supabase_read_only_user`, que Supabase ya trae con `BYPASSRLS` y `pg_read_all_data`: lo gestiona Supabase, y ponerle contraseña puede chocar con su uso interno o revertirse.
- El token `ci-prod` en `backup`: abriría todos los secretos de producción a un entorno sin aprobación.
- Un DSN completo como secreto: la seguridad de TLS dependería de lo que alguien escriba en él, el motivo que ya descartó ADR 0010.
- `postgresql-client-17` con `apt` desde PGDG: depende de un repositorio externo en cada run. Una imagen fijada por digest da los mismos bytes siempre.

## Consecuencias

- El rol llega a producción con las migraciones (TWO-32). Hasta que una persona le ponga contraseña y la copie a `backup`, el volcado diario falla en rojo cada día.
- `pg_read_all_data` lee también `auth`: usuarios, identidades, factores TOTP y, más adelante, mensajes y memorias. Es lo que un volcado completo debe llevar, salvo las sesiones vivas. Por eso el bucket solo lo lee una persona con su usuario de administración, y los volcados caducan a los 30 días.
- Como cualquier rol, `twochi_backup` puede crear objetos grandes (`lo_from_bytea`) y tablas temporales, y cambiar su propia contraseña (comprobado en local). Las funciones `lo_*` son de `supabase_admin`, y `postgres` no puede quitarle a `PUBLIC` el permiso de ejecutarlas. Con la contraseña, alguien podría llenar el disco o romper los volcados, que saldrían en rojo. Se acepta: esa misma contraseña ya deja leer toda la base, que es peor, y solo vive en Bitwarden y en el entorno `backup`.
- `just check-dump` (TWO-41) repite en cada PR de Python el ciclo comprobado en local: vuelca la base local con el script y la imagen fijada, como `twochi_backup`, comprueba las exclusiones, restaura `data.sql` como `postgres` sobre una base recién migrada y compara las filas. Una tabla nueva que rompa la restauración sale en rojo en el CI, no el día de restaurar.
- Al actualizar la CLI de Supabase, hay que comparar su `supabase db dump --dry-run` con `.github/scripts/supabase_dump.sh`. Dependabot no ve la imagen, que vive en `db_dump.py`: se actualiza a mano, también en los comandos de [volcados de la base](../operaciones/restaurar-un-volcado.md), y siempre al cambiar Postgres de versión mayor.
- AWS bloquea SSE-C por defecto en los buckets creados desde abril de 2026, y el de backups lo es. El 403 de la sonda puede venir de ese bloqueo y no de la condición de IAM: el resultado es el que se busca (ningún volcado con SSE-C), pero no prueba la condición por sí sola. Si el bucket responde con otro código, el primer run lo dirá en rojo y la sonda se ajusta a ese código.
- Restaurar sigue el procedimiento de [restaurar un volcado](../operaciones/restaurar-un-volcado.md), que contrasta la clave, la hora, el tamaño y el SHA-256 con el log del job, y el commit del run con uno revisado, antes de usar un volcado.
