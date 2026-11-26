# 0015. Los gustos los oculta la API, no RLS

- Estado: aceptada
- Fecha: 2026-11-26
- Completa Datos y vectores («Privacidad entre los dos: políticas por persona» y la tabla `item_affinities`)

## Contexto

Cada mascota tiene una afinidad de −2 a 2 con cada comida y cada actividad del catálogo. La pone la persona a la que representa, desde la app. Quien cuida la mascota no ve esa lista: descubre cada gusto al darlo, por la reacción, y el quiz «¿Cuánto me conoces?» vive de eso.

Lo natural sería una política por persona, como las de conversaciones y memorias: solo la persona representada lee sus afinidades. Pero el motor escribe como `authenticated` con el JWT de quien llama ([ADR 0009](0009-engine-writes-as-authenticated.md)). Cuando el cuidador da de comer, el motor necesita la afinidad de esa comida con los permisos del cuidador, y esa política se la ocultaría.

## Decisión

- `item_affinities` lleva la política de pareja: la leen las dos personas.
- Solo escribe la persona representada: el `insert` y el `update` exigen que la mascota la represente a ella.
- La API es la que oculta. Devuelve la lista de gustos solo a la persona representada; al cuidador le llega lo que ve jugando, la reacción de cada comida o actividad que da.

## Alternativas descartadas

- Una política por persona y una función `security definer` que dé al motor la afinidad de un objeto: añade una función con privilegios, zona delicada, para proteger solo los gustos que aún no se han descubierto.
- Un rol aparte para que el motor lea las afinidades: rompe el rol único con RLS del ADR 0009.

## Consecuencias

- La frontera entre las dos personas, en los gustos, la pone el código de la API, no la base. Un fallo en una consulta podría enseñar al cuidador gustos sin descubrir, pero nunca los de otra pareja.
- Lo que se pierde es poco: cada reacción descubierta ya queda en `pet_events`, que la pareja lee para la señal de Realtime, y el esquema `app` no está expuesto, así que la API es el único camino a la tabla.
- Si `app` se expone algún día o los gustos pasan a ser privados de verdad, esta decisión se revisa con la de 0009.
