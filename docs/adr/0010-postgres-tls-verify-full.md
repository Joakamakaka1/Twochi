# 0010. Postgres en `verify-full` contra la CA de Supabase, que va dentro del paquete

- Estado: aceptada
- Fecha: 2026-11-22
- Modifica Datos y vectores («Conexión desde Lambda»), que pedía SSL en `require`

## Contexto

`twochi_data.sql.connect` pasaba `ssl="require"` a asyncpg. La conexión iba cifrada, pero el cliente aceptaba cualquier certificado y cualquier nombre de host. Alguien en medio podía presentar su propio certificado y retransmitir el inicio de sesión SCRAM. Lo hace la Lambda de la API como `twochi_api` y lo hará `just provision` como `postgres` contra producción.

Supabase recomienda `verify-full` con la CA que se descarga del panel (Database Settings, «SSL Configuration», `prod-ca-2021.crt`) ([Supabase](https://supabase.com/docs/guides/platform/ssl-enforcement)). Lo comprobado el 2026-11-22:

- El pooler de eu-west-1 (`aws-0` y `aws-1`, puertos 6543 y 5432) presenta `*.pooler.supabase.com` y `*.pooler.supabase.co`. Lo firma «Supabase Intermediate 2021 CA», y a esta «Supabase Root 2021 CA».
- Esa raíz es idéntica, byte a byte, a `prod-ca-2021` del CLI oficial de Supabase (`supabase/cli`, `apps/cli/src/command-internal/supabase-ca-templates/prod-ca-2021.ts`). SHA-256: `80:70:25:AD:50:D4:ED:21:9D:2C:9C:7D:29:9C:00:4F:82:4E:B0:0C:F7:F6:5A:FE:F6:07:D0:7B:72:E6:CA:FA`. Caduca el 2031-04-26.
- La cadena pasa el modo estricto de X.509 que Python activa por defecto desde la 3.13, y un handshake real con el contexto nuevo funciona en los cuatro puntos del pooler.
- La conexión directa (`db.<ref>.supabase.co`) solo tiene IPv6 en este plan y no se pudo probar desde aquí. Twochi no la usa: la API y `just provision` van por el pooler.

## Decisión

- Con `require_tls`, `connect` usa un `SSLContext` que solo confía en «Supabase Root 2021 CA» y comprueba el nombre del host del DSN: el `verify-full` de libpq.
- Solo esa raíz, no el almacén del sistema: ninguna CA pública firma un host de Supabase, así que confiar en ellas solo abre puertas.
- El contexto explícito manda sobre el `sslmode` del DSN: un DSN con `sslmode=require` no rebaja la comprobación.
- La CA va como fichero dentro de `twochi_data` (`supabase-root-2021-ca.pem`). Llega a la Lambda en el zip, cuenta en el hash del paquete y no depende del almacén de la imagen.
- Sin `require_tls` nada cambia: solo el Postgres local, que no sirve TLS, lo apaga.

## Alternativas descartadas

- `sslrootcert` y `sslmode=verify-full` en el DSN: el DSN vive en un secreto, así que la seguridad dependería de lo que alguien escriba ahí, y el fichero tendría que existir en la Lambda de todos modos.
- El almacén de certificados del sistema o `certifi`: no contienen la CA de Supabase, y la conexión fallaría.
- Fijar el certificado del pooler (pinning): caduca en 2030 y Supabase puede cambiarlo sin avisar; la raíz es lo que Supabase pide verificar.

## Consecuencias

- Si Supabase cambia de CA o el pooler deja de encadenar a esta raíz, la API responde «no disponible» hasta que se actualice el fichero. Antes de 2031-04-26 hay que sustituirlo por la nueva CA del panel. Los tests de `packages/data/tests/test_tls.py` usan una cadena del pooler guardada y lo dirán al cambiar el fichero.
- Tras desplegar, la prueba de humo confirma que la API sigue conectando a producción.
