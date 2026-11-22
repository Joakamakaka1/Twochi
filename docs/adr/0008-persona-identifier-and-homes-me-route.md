# 0008. La ficha es `Persona` y Casa se pide en `/api/homes/me`

- Estado: aceptada
- Fecha: 2026-11-22
- Cambia la tabla de identificadores de Arquitectura y convenciones («Qué cambia en las demás pestañas») y la ruta de Casa que fijaba la spec TWO-28

## Contexto

La revisión de TWO-29, la primera migración del núcleo, encontró dos choques de nombre. Los dos son caros de deshacer después, porque las migraciones y la API solo cambian de forma aditiva:

- El glosario daba a la ficha el identificador `Profile`, pero el esquema llama `profiles` a la tabla con una fila por persona de la pareja (pareja, nombre visible y horas de silencio).
- La spec fijaba `GET /api/home`, en singular, y las normas piden sustantivos en plural bajo `/api`.

## Decisión

- La ficha pasa a llamarse `Persona` en el código, igual que sus tablas `persona_traits` y `persona_versions`. La tabla `profiles` conserva su nombre y su sentido: las personas de la pareja.
- Casa se pide en `GET /api/homes/me`: el sustantivo de colección queda en plural y `me` es la vista única de quien llama.

## Consecuencias

- Renombrar `profiles` habría exigido tocar esquema.md y, después del primer despliegue, dos migraciones en dos despliegues. Cambiar el identificador del glosario no toca nada desplegado.
- Las rutas futuras de una sola vista por persona siguen la misma forma: `/api/<colección>/me`.
