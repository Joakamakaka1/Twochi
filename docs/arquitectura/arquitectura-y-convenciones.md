# Arquitectura y convenciones

> Exportado el 2026-11-21 desde el documento de diseño de Twochi. Desde la exportación, manda lo que hay en `main`: una decisión cambia por PR, con su ADR.

Twochi sigue una hexagonal pragmática sobre un monolito modular: dominio puro, casos de uso y adaptadores, con puertos solo donde hay red, dinero o azar. El código va en inglés; lo que leéis vosotros y lo que dice la mascota, en español.

Decidido el 20 de noviembre de 2026 con tus ocho respuestas, recogidas al final. Esta pestaña manda en nombres, capas y convenciones; `CODING_STANDARDS.md` es su destilado dentro del repositorio.

## La forma

*Diagrama: capas de Twochi · 3 entradas, núcleo y 4 adaptadores (en el documento original).*

Las flechas son imports. Las apps reciben la petición y llaman a un caso de uso; los adaptadores implementan los puertos que ese caso de uso declara. Solo las apps conocen los dos lados: crean los adaptadores al arrancar y los pasan por parámetro.

## Capas y paquetes

Cuatro capas, de dentro afuera. Cada paquete Python es de nivel superior y lleva el prefijo `twochi_`, para que las reglas de import se escriban sin excepciones.

| Capa | Paquete | Qué contiene | Qué puede importar |
| --- | --- | --- | --- |
| Dominio | `packages/domain` → `twochi_domain` | Tipos y reglas del juego: necesidades, acciones, afinidades, visibilidad y puntuación de memorias | Solo la librería estándar |
| Aplicación | `packages/application` → `twochi_application` | Casos de uso, puertos y el doble de prueba de cada puerto | El dominio |
| Adaptadores | `packages/agent`, `data`, `guardrails` y `messaging` | Una familia de tecnología por paquete, implementando puertos: `agent` reúne el modelo y los embeddings | Aplicación, dominio y su librería externa. Nunca otro adaptador |
| Apps | `apps/api`, `worker` y `mcp` | Entrada, autenticación y composición: crean los adaptadores y se los pasan a los casos de uso | Todo lo anterior |

- Dos paquetes nuevos respecto al monorepo de la pestaña principal: `application`, que faltaba, y `messaging`, para SQS, Scheduler y Web Push, que hoy no tienen sitio.
- Una ruta, un caso de uso. Las rutas de FastAPI y los handlers del worker traducen la entrada, llaman a una función de aplicación y traducen la salida. Sin lógica propia.
- Lo que es regla va al dominio aunque hable de IA. Qué puede ver cada persona (criterio 16) y cómo se puntúan las memorias son funciones puras con tests, no frases del prompt.
- `evals` queda fuera de las capas. Es una herramienta de desarrollo y nada de producción la importa, salvo el juez online, que entra como un adaptador más.
- Composición a mano. Cada app tiene un `wiring.py` que construye los adaptadores una vez por arranque de Lambda. Sin contenedor de dependencias; `Depends` de FastAPI solo en el borde de la ruta.

## Puertos

Diez puertos, todos `typing.Protocol` definidos en `twochi_application`. Un puerto existe solo si al otro lado hay red, dinero o azar.

| Puerto | Para qué | Adaptador real | En los tests |
| --- | --- | --- | --- |
| `PetVoice` | Generar el turno de la mascota | `agent`: Pydantic AI con Sonnet 5.5 | Doble que devuelve un turno fijo |
| `MemoryExtractor` | Sacar memorias de una conversación | `agent`: Haiku 5.5 | Doble |
| `Embedder` | Vectorizar texto | `agent`: Voyage | Doble determinista |
| `TurnJudge` | Puntuar una muestra de turnos | `evals`: Haiku 5.5 como alarma | Doble |
| `InputScreen` | Cribar el mensaje en modo sombra | `guardrails`: Bedrock | Doble |
| `JobQueue` | Encolar trabajo para el worker | `messaging`: SQS | Doble en memoria; emulador en integración |
| `Scheduler` | Programar avisos | `messaging`: EventBridge Scheduler | Doble en memoria; emulador en integración |
| `PushSender` | Enviar notificaciones | `messaging`: Web Push | Doble |
| `Clock` | Dar la hora | Reloj del sistema | Reloj fijo |
| `Database` | Abrir una transacción con sus repositorios | `data`: asyncpg | Ninguno: Postgres local real |

- Nombre de papel, no de tecnología. El puerto es `PetVoice`; el adaptador, `PydanticAiPetVoice`. Cambiar de proveedor toca un fichero, como ya pedía la pestaña principal.
- `Database` es una unidad de trabajo mínima. `db.transaction(actor)` abre la transacción, fija el rol y los claims del JWT para RLS y entrega los repositorios atados a ella. Un trabajo del worker pasa un `SystemActor(job)`, que usa el rol `twochi_worker` y sus políticas.
- Los dobles viven junto a los puertos, en `twochi_application.testing`: uno por puerto, escrito a mano. Sin `unittest.mock.patch` en los tests de aplicación.
- No son puertos: FastAPI, Pydantic, la configuración, el logging y las trazas de OpenTelemetry. Son librerías sin red o detalles que monta cada app.
- Un puerto nuevo se justifica en su PR: qué hay al otro lado y qué doble lo sustituye. Si no hay respuesta, es una función normal.

## Un caso de uso de principio a fin

El turno de chat enseña todas las reglas a la vez: transacciones cortas, el modelo fuera de ellas y el dominio decidiendo. Es un boceto de la forma, no código final.
```
# twochi_application/take_turn.py
async def take_turn(
    cmd: TakeTurn, *, db: Database, embedder: Embedder,
    voice: PetVoice, queue: JobQueue, clock: Clock,
) -> TurnResult:
    deadline = clock.now() + TURN_BUDGET                 # 25 s para todo el turno

    async with db.transaction(cmd.actor) as tx:          # 1. reservar y leer, con RLS
        claim = await tx.conversations.claim(cmd)        # único por client_message_id
        if claim.duplicate:
            return claim.stored or TurnInProgress()
        await tx.usage.count_turn(cmd.actor)             # topes, en la misma transacción
        pet = await tx.pets.get(cmd.pet_id)
        history = await tx.conversations.recent(pet.id)

    query = await embedder.embed(cmd.message, timeout=2) # red; None si falla
    candidates = []
    if query is not None:
        async with db.transaction(cmd.actor) as tx:
            candidates = await tx.memories.nearest(pet.id, query, viewer=cmd.actor)

    now = clock.now()
    memories = rank(candidates, now)[:8]                 # dominio puro
    turn = await voice.reply(                            # 2. modelo, sin transacción
        build_context(pet, memories, history, now), cmd.message,
        deadline=deadline, max_calls=2)

    async with db.transaction(cmd.actor) as tx:          # 3. decidir y guardar
        pet = await tx.pets.get_for_update(cmd.pet_id)
        outcome = apply_proposals(pet, turn.proposed_actions, clock.now())
        await tx.pets.save(outcome.pet)
        await tx.conversations.complete(claim, turn)     # pendiente -> hecho

    await queue.enqueue_or_skip(TurnRecorded(pet.id, cmd.conversation_id))  # 4. lo lento
    return TurnResult(turn, outcome.applied, outcome.rejected)

```
- Nunca una transacción abierta mientras responde el modelo. La llamada dura segundos; el pooler va en modo transacción y `for update` bloquea la mascota a tu pareja.
- Se relee antes de decidir. El estado pudo cambiar durante la llamada, así que el paso 3 bloquea, relee y deja que el motor valide contra lo que hay ahora.
- Las dependencias entran por parámetro, con nombre y tipo de puerto. El caso de uso no importa asyncpg, Pydantic AI ni boto3.
- Un rechazo del motor es un resultado, no una excepción. `outcome.rejected` viaja al front, que puede animar la negativa.
- La ruta que lo llama cabe en diez líneas: valida el JWT `aal2`, construye `TakeTurn`, llama y devuelve el esquema Pydantic de respuesta.
- La clave se reserva antes del modelo. El mensaje del usuario entra como pendiente en la primera transacción; un duplicado en vuelo recibe la respuesta guardada o un 409, y no paga otra llamada.
- Un plazo, dos llamadas. El turno tiene 25 s y el puerto `PetVoice` hace dos llamadas al modelo como máximo, sea cual sea el fallo.
- Sin memorias antes que sin respuesta. Si Voyage falla o tarda más de 2 s, el turno sigue sin recuerdos.
- El encolado no tumba el turno. Si SQS falla tras guardar, se responde igual y el barrido recoge el trabajo.

## Patrones: los que se usan y los que no

Seis patrones entran, cada uno en su forma más corta. Seis se quedan fuera con nombre y con la señal que los traería, para que añadirlos sea una decisión y no una deriva.

### Se usan

| Patrón | Cómo queda aquí |
| --- | --- |
| Puertos y adaptadores | Los diez puertos de arriba y un adaptador por tecnología |
| Núcleo funcional, borde imperativo | El motor recibe estado y `now`, y devuelve estado nuevo y efectos. No hace E/S ni lee el reloj |
| Repositorio | Uno por tabla raíz en `data`, con SQL a mano, que devuelve tipos del dominio |
| Unidad de trabajo | `db.transaction(actor)`, sin seguimiento automático de cambios: se guarda lo que el caso de uso pide guardar |
| Agregado | En espíritu: la mascota con sus necesidades se carga, se bloquea y se guarda entera. Sin clases base |
| Objeto de valor | `dataclass` congelada, `StrEnum` e identificadores con `NewType` (`PetId`, `CoupleId`, `UserId`) |

### Se dejan fuera

| Patrón | En su lugar | Entraría si |
| --- | --- | --- |
| Eventos de dominio y bus | El motor devuelve los efectos en su resultado y el caso de uso los ejecuta | Un mismo hecho necesita tres o más reacciones independientes |
| CQRS | Las lecturas son funciones de aplicación normales | Las pantallas piden vistas muy distintas del modelo de escritura |
| Mediador o bus de comandos | La ruta llama a una función | Hace falta el mismo tratamiento transversal en todos los casos de uso |
| Contenedor de dependencias | `wiring.py` a mano en cada app | La composición deja de caber en una pantalla |
| ORM | SQL explícito, por RLS, pgvector y los bloqueos | El esquema crece hasta que el mapeo a mano cuesta más que la magia |
| Clases base y repositorio genérico | Código repetido dos veces | Aparece la tercera repetición idéntica |

Añadir uno de los seis de abajo es una desviación del documento: lleva ADR con la señal que lo justifica.

## Convenciones de Python

Tipado estricto, dominio sin dependencias y efectos solo en los bordes. Casi todo lo comprueban `ruff`, `pyright` y los contratos de import; lo que no, lo mira `/code-review`.
- Tipos del dominio: `@dataclass(frozen=True, slots=True)`, `StrEnum` y `NewType` para identificadores. Cambiar algo devuelve una copia con `replace`.
- Pydantic solo en los bordes: esquemas de la API, salida del agente y configuración. Cada borde mapea a tipos del dominio en una función junto al esquema.
- Tiempo: siempre `datetime` con zona UTC. El dominio recibe `now` por parámetro y nunca lee el reloj; solo lo hace el adaptador de `Clock`.
- Errores: lo esperable es un valor de retorno, como `Rejected(reason)`. Lo inesperado es una excepción que hereda de `TwochiError`. Los adaptadores traducen las excepciones del proveedor a las de aplicación.
- Asíncrono en la E/S, síncrono en el dominio. Ninguna función `async` en `twochi_domain`.
- Configuración: `pydantic-settings` en las apps. Los paquetes reciben valores por parámetro; nada lee `os.environ` fuera de `wiring.py`.
- Tipado: `pyright` en modo estricto. Sin `Any` en dominio ni aplicación; un `# type: ignore` lleva su código y su motivo.
- Lint y formato: `ruff format` y `ruff check` con las familias `E`, `F`, `I`, `B`, `UP`, `SIM`, `N`, `S`, `DTZ`, `ASYNC`, `PT`, `T20`, `TID` y `RUF`.
- Nombres: casos de uso con verbo (`take_turn`, `apply_care_action`); puertos con nombre de papel; adaptadores con tecnología y papel (`SqsJobQueue`). Sin `utils.py` ni `helpers.py`: cada módulo se llama como su tema.
- Funciones antes que clases. Una clase aparece cuando hay estado que mantener o un puerto que implementar.
- Logs: estructurados con Powertools y con el identificador del turno. Nunca el texto de un mensaje, de una memoria o de la ficha.
- Comentarios y docstrings en inglés, y solo donde explican un porqué. Cada función pública de dominio y de aplicación lleva una línea de docstring.

## Convenciones de API y base de datos

El contrato es el OpenAPI que genera FastAPI, y los cambios de API y de esquema son siempre aditivos. Las doce reglas del esquema siguen en Datos y vectores; aquí va lo que toca al código.

### API
- Rutas: bajo `/api`, con sustantivos en plural y en inglés: `POST /api/pets/{pet_id}/turns`, `POST /api/pets/{pet_id}/care-actions`.
- JSON en `snake_case` de punta a punta. Es lo que emite Pydantic y lo que llega por Realtime, así que el front no mantiene dos estilos.
- Errores: `application/problem+json` (RFC 9457) con un `code` estable, como `limit_exceeded`. El paso de excepción a HTTP vive en un único fichero de `apps/api`.
- Idempotencia: toda escritura lleva su clave (`client_message_id`, `idempotency_key`), como ya fija Datos y vectores. Reintentar devuelve la respuesta original, o un 409 si la primera petición sigue en curso.
- Sin `/v1`. Front y API se despliegan juntos, pero la PWA instalada puede servir un bundle antiguo. Un campo o una ruta se retira en un despliegue posterior al que deja de usarlo.
- El contrato del turno va en inglés: `emotion`, `animation`, `text` y `proposed_actions`, en ese orden por el SSE.

### Base de datos
- Todo el SQL vive en `twochi_data`. Parámetros `$1`, nunca cadenas formateadas. Columnas explícitas, sin `select *`. Una función por consulta.
- Toda consulta corre dentro de `db.transaction(actor)`. No existe una conexión suelta que se salte RLS. Los trabajos del worker pasan un actor de sistema y usan las políticas de `twochi_worker`.
- El repositorio devuelve tipos del dominio. El paso de fila a `dataclass` es una función junto a la consulta.
- Plantilla de tabla: `couple_id`, RLS por pareja, política restrictiva `aal2`, `created_at` y su test de dos parejas. Si guarda contenido privado, además política por persona y test de dos personas de la misma pareja. Una tabla nueva que la sigue es un cambio normal, no delicado.
- Migraciones: aditivas, un fichero por cambio, con verbo y objeto en el nombre (`…_add_pet_events.sql`). Retirar algo son dos migraciones en dos despliegues.
- Nombres: tablas en plural, en inglés y en `snake_case`. Los estados son `text` con `check`, como ya hace `memories`, no tipos `enum` de Postgres.

## Convenciones del front

Carpetas por funcionalidad, el 3D aparte y el estado del servidor en un solo sitio.
```
apps/web/src/
  app/        # arranque, rutas, providers
  features/   # auth, care, chat, couple, shop
  scene/      # R3F: mascota, clips, cámara
  shared/     # api (cliente generado), ui, lib

```
- Dirección de imports: `app` → `features` → `scene` → `shared`. Una funcionalidad no importa de otra: lo común baja a `shared` o lo compone `app`.
- Cada carpeta exporta por su `index.ts`. Importar un fichero interno de otra carpeta lo prohíbe ESLint.
- Estado del servidor: solo TanStack Query. Nada del servidor se copia a Zustand. Un evento de Realtime solo invalida la caché de Query: es una señal, no trae datos.
- Zustand: solo estado de interfaz y de escena, en stores pequeños por tema. La escena expone `play(animation)`; las funcionalidades no tocan Three.js.
- React Three Fiber: nada de `setState` dentro de `useFrame`; se mutan refs. Un solo `Canvas`, GLB precargados con `useGLTF.preload` y recursos liberados al desmontar.
- Red: solo el cliente generado, en `shared/api`. Ningún `fetch` en componentes; `supabase-js` solo en `features/auth` y en el módulo de tiempo real.
- TypeScript: `strict` y `noUncheckedIndexedAccess`. Sin `any` ni `enum`: uniones de literales, que ya salen del OpenAPI.
- Componentes: funciones con exportación con nombre, fichero en `PascalCase` y hooks `useX`. La lógica va en hooks; el componente pinta.
- Textos de interfaz en un módulo, no repartidos por los componentes: cambiarlos o traducirlos es tocar un fichero.
- Estilo: CSS Modules por componente y un único fichero de tokens, `shared/ui/tokens.css`. Ningún otro CSS escribe a mano un color, un radio o un espacio; lo comprueba un test. La app sirve sus fuentes, con la licencia al lado, sin CDN. Solo modo claro, y `prefers-reduced-motion` apaga las transiciones de la interfaz.
- Accesibilidad mínima: todo lo que se toca es un `button` con nombre, también lo que flota sobre el `Canvas`. El foco siempre se ve.
- Necesidades: el front interpola con `value`, `updated_at` y `rate_per_hour` que da la API. No copia reglas del motor.

## Convenciones de prompts, Terraform y workflows

Tres sitios donde un cambio pequeño tiene un efecto grande; cada uno con su regla corta.
- Prompts: ficheros en `packages/agent/prompts/`, en español y con el hash como versión. Lo que puede decidir el código no se le pide al prompt. Ficha y memorias entran delimitadas como datos.
- Un cambio de prompt, de esquema o de modelo pasa por las evals. No se fusiona porque «suena mejor».
- Terraform: nombres `twochi-<pieza>`, un rol de IAM por Lambda con lo mínimo y ningún recurso creado a mano fuera de `infra/bootstrap`. Un módulo aparece a la segunda copia, no antes.
- Workflows: valen las reglas de CI/CD e IaC, sin añadidos: acciones fijadas a un commit, sin `pull_request_target` y sin texto del PR dentro de un `run`.

## Tests

Cada capa se prueba donde su fallo sale más barato. Los casos de uso van contra Postgres local real, como decidiste; solo se doblan los puertos de red o de pago.

| Capa | Qué se prueba | Con qué |
| --- | --- | --- |
| Dominio | Reglas e invariantes del motor | `pytest` sin red, en milisegundos. Hypothesis para invariantes: una necesidad nunca sale de su rango y el paso del tiempo nunca la sube |
| Aplicación | Cada caso de uso de principio a fin | Supabase local con RLS real; dobles para modelo, Voyage, Bedrock, cola y push |
| `data` | RLS y consultas | El test de dos parejas y uno por consulta no trivial |
| `agent` | Prompt renderizado, esquema de salida y rechazos | El modelo falso de Pydantic AI. Llamadas reales solo en evals y en el humo |
| `messaging` | SQS y Scheduler | El emulador de AWS, como ya fija CI/CD e IaC |
| `api` y `worker` | Autenticación `aal2`, paso de errores a HTTP y forma de la respuesta | La app montada con dobles. Pocos tests, porque ahí no hay lógica |
| Front | Hooks y lógica de cada funcionalidad | `vitest`. Sin snapshots del 3D: la escena se prueba en el móvil |

- Aislamiento por pareja. Cada test crea su propia pareja y no limpia tablas. El `couple_id` que aísla a los usuarios aísla también los tests y deja correrlos en paralelo.
- TDD por la costura pública. El test llama al caso de uso o a la función del motor, nunca a un detalle interno. Refactorizar no debe romper tests.
- Sin umbral global de cobertura. Solo en `twochi_domain`: 90 % de ramas, porque es puro y barato de cubrir.
- Un bug llega con su test. Primero el test que lo reproduce, en rojo; después el arreglo.

## Git y pull requests

Un PR es un commit en `main` y un solo `git revert`: squash y Conventional Commits, como decidiste.
- Título del PR: `tipo(ámbito): resumen en inglés (ID)`. Por ejemplo, `feat(domain): add affinity bonus to feeding (TWO-42)`. El prefijo real del identificador lo da Linear. Un trivial y un PR de Dependabot van sin identificador.
- Tipos: `feat`, `fix`, `refactor`, `perf`, `test`, `docs`, `build`, `ci` y `chore`. Un `!` tras el ámbito marca un cambio que rompe un contrato.
- Ámbito: el paquete o la app que más cambia: `domain`, `application`, `agent`, `data`, `api`, `worker`, `web` o `infra`.
- Rama: `<id>-<resumen-corto>`, por ejemplo `two-42-affinity-bonus`.
- Solo squash activado en el repositorio. Los commits de la rama son libres; el título del PR es el mensaje que queda en `main`.
- Un PR, una rebanada. Si el diff mezcla un refactor con una funcionalidad, son dos PR: primero el refactor, sin cambio de comportamiento.
- Cuerpo del PR: las secciones que ya pide Forma de trabajo: evidencia, prueba de antes y después, y peligro de fusión.
- Antes de abrir el PR, `just check` completo en local: los mismos pasos que el CI. Un PR no se abre para descubrir si pasa.

## Principios

Ocho principios para lo que las reglas no deciden. Si dos chocan, gana el que está más arriba.
1. Las dependencias apuntan hacia dentro. Lo que cambia a menudo depende de lo que cambia poco, nunca al revés.
2. El modelo propone, el código decide. Ninguna regla del juego, de privacidad o de gasto vive solo en un prompt.
3. Privado por defecto. Lo que cuenta una persona no llega a la otra salvo que una regla del dominio lo permita.
4. El dominio es determinista. Mismo estado y mismo `now`, mismo resultado. El azar y el reloj entran por parámetro.
5. Se valida en el borde y se confía dentro. Lo que entra se convierte una vez a tipos del dominio; dentro no se vuelve a comprobar.
6. Todo lo que reintenta es idempotente. Un doble toque, un reintento de SQS o una recarga no duplican nada.
7. La opción más simple que funcione. Ninguna capa, puerto o abstracción entra sin un segundo uso real.
8. Lo que puede forzar un check, lo fuerza un check. Lo demás va a `CODING_STANDARDS.md`, en una línea.

## Cómo se fuerza

Siete checks cubren las reglas mecánicas. Todos corren en `just check` y en CI, dentro de `ci-ok`.

| Regla | Check |
| --- | --- |
| Capas del backend y adaptadores que no se importan entre sí | `import-linter`, contrato `layers` |
| Dominio sin librerías externas | `import-linter`, contrato `forbidden` sobre `twochi_domain` |
| Tipos | `pyright` estricto y `tsc` con `strict` |
| Estilo, tiempo con zona, SQL sin formatear y `print` | `ruff`, con las familias de la sección de Python |
| Capas del front e imports internos | ESLint: `no-restricted-imports` por carpeta; `eslint-plugin-boundaries` si se queda corto |
| Título y cuerpo del PR | Un paso del check `flujo` valida Conventional Commits y el identificador; el identificador no se exige en triviales ni en PR de Dependabot. Con identificador, el cuerpo declara su tamaño, que no puede ser trivial ni normal en zona delicada, y su revisión si no es trivial. Avisa sin fallar si cambia código de `apps/` o `packages/` sin ningún test |
| Cobertura del dominio | `pytest --cov` con umbral solo en `twochi_domain` |

El contrato de capas, tal como iría en `pyproject.toml`. En `import-linter`, `|` separa hermanos independientes: están en la misma capa y no pueden importarse entre sí ([Import Linter](https://import-linter.readthedocs.io/en/stable/contract_types/layers/)).
```
[tool.importlinter]
root_packages = [
  "twochi_domain", "twochi_application",
  "twochi_agent", "twochi_data", "twochi_guardrails", "twochi_messaging",
  "twochi_api", "twochi_worker", "twochi_mcp",
]

[[tool.importlinter.contracts]]
name = "Las dependencias apuntan hacia dentro"
type = "layers"
layers = [
  "twochi_api | twochi_worker | twochi_mcp",
  "twochi_agent | twochi_data | twochi_guardrails | twochi_messaging",
  "twochi_application",
  "twochi_domain",
]

```
- A validar al montarlo: que `import-linter` resuelve los paquetes del workspace de uv como `root_packages`.
- `CODING_STANDARDS.md` recoge solo lo que exige criterio: nombres, cuándo crear un puerto y qué es regla de dominio. Una línea por norma, con enlace a esta página ya exportada.
- Una norma que se incumple dos veces pasa a check, como ya hace `/retro`.

## Qué cambia en las demás pestañas

Los cinco puntos quedaron alineados el 21 de noviembre, salvo el glosario, que nace con el repositorio. En nombres y capas sigue mandando esta pestaña.

| Dónde | Qué cambia |
| --- | --- |
| Pestaña principal, Monorepo | Entran `packages/application` y `packages/messaging`. Ya aplicado allí |
| IA y calidad, y Salida estructurada en la principal | `Turno` pasa a `Turn`, con `emotion`, `animation`, `text` y `proposed_actions`; `Accion` pasa a `Action`. Ya aplicado |
| Front móvil y 3D | Los clips del GLB se nombran en inglés: `idle`, `happy`, `sad`, `eat`, `sleep`, `angry` y `surprised`. Ya aplicado |
| Forma de trabajo | `CODING_STANDARDS.md` se destila de esta pestaña y `just check` incluye los contratos de import. Ya aplicado allí |
| `GLOSSARY.md` | Cada término gana su identificador: mascota es `Pet`; pareja, `Couple`; ficha, `Persona` (la tabla `profiles` es otra cosa: una fila por persona de la pareja); turno, `Turn`; recado, `Errand` |

El español se queda donde lo lee una persona o el modelo: prompts, textos de la app, documentación, ADR y glosario.

## Decisiones tomadas el 20 de noviembre

Las ocho preguntas quedaron resueltas con tus respuestas.

| Pregunta | Decisión | Consecuencia |
| --- | --- | --- |
| ¿Para qué la arquitectura? | Mantenible por ti y la IA, escaparate público y aprender hexagonal y DDD | Cada patrón lleva su nombre, y los que no entran dicen cuándo entrarían |
| ¿Qué nivel de hexagonal? | Pragmática | Puertos solo en fronteras externas; sin CQRS, eventos ni contenedor |
| ¿En qué idioma va el código? | Inglés en identificadores, tablas y commits | El contrato del turno y los clips se renombran |
| ¿Cómo se prueban los casos de uso? | Contra Postgres local real | Dobles solo para red y pago; RLS entra en esos tests |
| ¿Cómo se accede a Postgres? | SQL a mano con asyncpg | Sin ORM; todo el SQL en `twochi_data` |
| ¿Con qué se definen los tipos del dominio? | `dataclasses` estándar | Pydantic solo en los bordes, con un mapeo en cada uno |
| ¿Cómo se organiza el front? | Por funcionalidad, ligera | `app`, `features`, `scene` y `shared` |
| ¿Qué convención de commits y fusión? | Squash y Conventional Commits | Un PR es un commit y un `git revert` |

Lo demás de esta pestaña son valores por defecto que derivan de esas ocho: nombres de puertos, familias de `ruff`, el umbral de cobertura y los dos paquetes nuevos. Se cambian con decirlo.

## Fuentes

Consultada el 20 de noviembre de 2026. El resto de la pestaña sale de las demás pestañas y de práctica establecida, sin cifras externas.
- [Import Linter — contrato de capas](https://import-linter.readthedocs.io/en/stable/contract_types/layers/)
