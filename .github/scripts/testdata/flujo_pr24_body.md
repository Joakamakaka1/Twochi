## Qué cambia

Tamaño: normal, en rutas delicadas (CI y `justfile`). Va encima del PR del refactor (`run_dump_script`); cuando ese se fusione, este pasa a apuntar a `main`.

`just check-dump` repite sobre la base local el ciclo que en TWO-39 se hizo tres veces a mano:

1. Cuenta las filas y calcula un hash de cada tabla de `app` y de `auth.users`.
2. Ejecuta `.github/scripts/supabase_dump.sh` en la imagen fijada, como `twochi_backup` y por la red de Docker de Supabase, con la misma llamada que el job diario.
3. Comprueba que `data.sql` no trae `COPY` de las 11 tablas excluidas (ADR 0012), con comillas o sin ellas. Si `data.sql` no copia `auth.users`, sale en rojo: así el check no puede pasar sin haber comprobado nada.
4. Ejecuta `supabase db reset --no-seed` y restaura `data.sql` como `postgres`, con `--single-transaction` y `ON_ERROR_STOP`.
5. Compara las filas y los hashes con los de antes.
6. Siempre, también si algo falla, termina con `supabase db reset`: la restauración no trae las contraseñas de los roles, y los tests las necesitan.

El job `python` del CI lo ejecuta después de `check-py`, y `just check` lo incluye. Solo usa contraseñas de desarrollo: la del seed para `twochi_backup` y la de la pila local para `postgres`. La ADR 0012 gana una línea en sus consecuencias.

## Evidencia

- `just check` completo en local, en verde: 339 tests de Python (9 nuevos para `exclusion_problems` y `row_differences`), `check-dump` incluido.
- `just check-dump` en verde con Supabase arrancado igual que en el CI (`-x realtime,storage-api,…`). Ahí las 75 migraciones de storage se aplican al iniciar la base, así que `storage.buckets_vectors` existe también en el CI, y `db reset` funciona con esos servicios excluidos.
- Dos mutaciones salen en rojo:
  - sin la exclusión de `storage.buckets_vectors` en el script: `data.sql copies storage.buckets_vectors, which the dump must leave out`;
  - sin ella también en la lista del check, la restauración aborta: `psql:/dump/data.sql:271: ERROR: permission denied for table buckets_vectors`. Es el fallo que encontró TWO-39.
- Tras el check, la suite de Python pasa entera: las contraseñas del seed vuelven.
- Revisiones: dos ejes, estándares y spec (un subagente); `/code-review` xhigh; revisor de seguridad. Arreglados: el regex de `COPY` solo veía identificadores entre comillas; el `reset` final no corría ante una excepción inesperada (ahora va en un `finally`); el refactor iba en el mismo PR (ahora va aparte).
- `gitleaks` y la guarda de IDs de Supabase sobre los commits de la rama: limpios.

## Antes y después

- Antes: una CLI de Supabase o una imagen `postgres` nueva podía añadir una tabla que rompiera la restauración, y nadie lo vería hasta el día de restaurar.
- Después: cualquier PR que toque Python, `.github/scripts`, `supabase/`, `mise.toml` o los workflows vuelca y restaura la base local, y sale en rojo si la restauración falla o si una tabla excluida vuelve al volcado.

## No comprobado

- La primera ejecución en el runner de GitHub. En local, con los servicios del CI, sí pasa.
- Si Docker Hub limita la descarga de la imagen `postgres` en los runners: ahora cada PR de Python la descarga.
- La restauración de `roles.sql` y `schema.sql`. El ticket pide solo `data.sql` sobre una base recién migrada.

Cada `just check` local deja la base como tras `just reset`: borra lo que no esté en el seed.

## Peligro de fusión

Puerta de dos sentidos: solo añade un paso al CI y una receta. Ni producción ni sus secretos entran: el job `python` no tiene entorno ni secretos. Se deshace revirtiendo el commit. Lo peor que puede pasar es que el job `python` salga en rojo por una causa ajena al PR (Docker Hub, por ejemplo) y bloquee `ci-ok` hasta revertirlo o arreglarlo.

Closes TWO-41

🤖 Generated with [Claude Code](https://claude.com/claude-code)
