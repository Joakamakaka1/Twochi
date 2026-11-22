# Tracker: Linear

Las specs y los tickets viven en Linear, en el equipo Twochi y en un solo proyecto, la v1. Las skills solo traen de serie GitHub, GitLab y ficheros locales, así que este documento describe el flujo con Linear. Las issues de GitHub están desactivadas.

## Spec y tickets

- La spec es un issue padre.
- Los tickets son sus sub-issues, con la etiqueta `ready-for-agent`.
- Los bloqueos son relaciones nativas de Linear («blocked by»), no texto en la descripción.
- `ready-for-human` marca una tarea que solo puede hacer una persona. Bloquea los tickets que dependen de ella y ningún agente la toma.
- Cada issue declara su tamaño (trivial, normal, complejo o delicado) con su motivo.

## Frontera

- La frontera son los sub-issues abiertos, sin bloqueos abiertos y sin empezar.
- Un agente reclama un ticket pasándolo a «In Progress». Asignarlo no distingue nada: en Linear el agente actúa con el usuario de una persona.
- Al terminar, lo cierra con un comentario de lo hecho y de lo que no pudo comprobar.
- Tras tres intentos fallidos sobre el mismo error, el agente para: escribe en el issue lo que probó y lo que descarta, lo marca bloqueado y toma otro ticket. No rebaja un check para salir.

## Frontera en paralelo

El detalle y su prueba están en el [ADR 0013](../adr/0013-parallel-tickets-one-slot-per-agent.md).

- El orquestador lanza hasta tres tickets a la vez, cada uno a un subagente con su hueco: un worktree en `.claude/worktrees/slot-N` y su propia instancia de Supabase.
- Dos tickets van juntos si ninguno bloquea al otro, sus rutas previstas no se cruzan y como mucho uno toca un punto caliente: migraciones, lockfiles, `GLOSSARY.md`, contratos compartidos o `supabase/config.toml`.
- Un ticket fusionado que espera despliegue ya no bloquea a los que dependen de su código: se pueden tomar.
- Cada agente entrega su rama sin empujarla. El orquestador la revisa, abre el PR y, tras cada fusión, hace que las demás ramas traigan `main` y repitan `just check`.

## Quién fusiona

Decidido en el [ADR 0014](../adr/0014-game-first-care-is-v1-and-the-ai-merges.md).

- La IA fusiona los PR, también los de zonas delicadas, con `ci-ok` en verde, `just check` en local sobre la rama con `main` dentro, la revisión de su tamaño sin hallazgos altos ni medios abiertos y, si el cambio se ve, la comprobación en el navegador.
- Espera a una persona el PR que debilita un control: quitar o relajar un check, tocar el ruleset, ampliar permisos de IAM o de un rol de la base, o cambiar cómo se guardan los secretos.
- Siempre squash, de una en una, sin auto-merge y sin la API.

## Cuándo se cierra un ticket

- Un ticket del juego se cierra fusionado y comprobado en local. No espera al despliegue.
- Un ticket del carril de despliegue se cierra cuando la prueba de humo pasa en producción.
- El tope de cinco PR sin desplegar está en suspenso hasta el primer despliegue de migraciones y front. Después cuenta solo los PR desplegables.

## Ramas y PR

- Rama: `<id>-<resumen-corto>`, por ejemplo `two-42-affinity-bonus`.
- Título del PR: `tipo(ámbito): resumen en inglés (ID)`, por ejemplo `feat(domain): add affinity bonus to feeding (TWO-42)`. El prefijo real del identificador lo da Linear.
- Tipos: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci` y `chore`. Un `!` tras el ámbito marca un cambio que rompe un contrato.
- La fusión es siempre squash: el título del PR es el commit que queda en `main`.
- Solo los triviales y los PR de Dependabot van sin identificador. Todo trabajo normal o complejo tiene su issue, aunque sea de una línea; el check `flujo` lo exige en las zonas delicadas.
- Cuerpo del PR: evidencia, prueba de antes y después, y peligro de fusión.
- Antes de abrir el PR, `just check` completo en local.
