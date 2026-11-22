# 0009. El motor escribe como `authenticated`, y la mascota se bloquea antes de buscar la clave

- Estado: aceptada
- Fecha: 2026-11-22
- Completa Datos y vectores («Principios del esquema» y «La API y RLS: dos opciones») y la spec TWO-28, que se contradecían

## Contexto

Datos y vectores decía que el cliente no tiene `insert` ni `update` sobre nada. Pero la opción B, la decidida, hace que la API escriba con `set local role authenticated`: el mismo rol del token del navegador. Sin permisos de escritura en `authenticated`, el motor no podría guardar ninguna acción. La spec TWO-28 ya pedía esos permisos, sin que el documento cambiara.

La spec ordenaba además la idempotencia así: buscar la clave y, si no está, bloquear la mascota. Con ese orden, dos toques simultáneos con la misma clave no encuentran nada, esperan al bloqueo y el segundo choca con `unique (pet_id, idempotency_key)`: un 500 en vez del resultado guardado.

## Decisión

- `authenticated` recibe solo lo que escribe el motor:
  - `update` de `asleep` y `sick_since` en `pets`;
  - `update` de `value` y `updated_at` en `pet_needs`;
  - `insert` en `pet_events`.

  Son permisos por columna y con políticas por pareja. Las restrictivas `aal2` que ya existían también los cubren. Nada borra ni toca `couples` o `profiles`.
- La política de `insert` en `pet_events` es más estricta que la de lectura. Exige que el evento sea de la pareja, a nombre de quien llama (`actor_user_id = auth.uid()`) y nunca con `source = 'system'`.
- `pet_events.created_at` lo pone el caso de uso con su `now`, para que la ventana de una hora de las caricias efectivas use el mismo reloj que el motor.
- `apply_care_action` primero bloquea la mascota con `for update` y después busca la clave. Así un duplicado espera al primero y encuentra su evento.
- Una clave solo repite la misma acción de la misma persona. Si ya nombra otra acción, a otra persona o un evento que no es de cuidado, la API responde 422 `idempotency_key_reused`, como propone el borrador del IETF sobre la cabecera `Idempotency-Key`.

## Alternativas descartadas

- Un rol propio para la API con políticas de escritura: rompería la opción B, en la que las mismas políticas protegen navegador y API.
- Escribir con una función `security definer`: se salta RLS justo en las escrituras, que es donde más importa.

## Consecuencias

- El token del navegador tiene en teoría esos permisos, pero no puede usarlos: `app` no está expuesto en la Data API ni en GraphQL. Exponer `app` algún día obliga a revisar esta decisión.
- Las políticas no exigen ser el cuidador: lo decide el motor. Exigirlo en RLS haría que `for update` ocultara la mascota a la persona representada, y su acción daría un 404 en vez del rechazo `not_caretaker` que pide la spec.
- La propiedad «la media nunca sube entre dos acciones» de la spec es falsa en un caso límite. Si la mascota duerme y las necesidades que bajan llegan a 0, la energía sigue subiendo 12 por hora y la media sube. Las reglas no cambian. El test acota la propiedad y documenta la excepción con un ejemplo. Decidido contigo el 2026-11-22.
