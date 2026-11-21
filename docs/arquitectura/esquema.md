# Esquema de datos

Postgres guarda todo en un esquema privado con `couple_id` en cada fila. La memoria vectorial son frases atómicas extraídas de las conversaciones, no trozos de chat.


> Exportado el 2026-11-21 desde el documento de diseño de Twochi. Desde la exportación, manda lo que hay en `main`: una decisión cambia por PR, con su ADR.

## Principios del esquema

Doce reglas que evitan rehacer el esquema más adelante.
- Esquema `app`, no expuesto. El front no lee ni escribe tablas por la Data API; pasa por tu API. Desde 2026 las tablas nuevas de `public` ya no se exponen solas y requieren `grant` explícito ([Supabase](https://supabase.com/changelog/45329-breaking-change-tables-not-exposed-to-data-and-graphql-api-automatically)).
- `couple_id` en casi todas las filas, aunque sea redundante. Las políticas RLS quedan en una línea y los índices son simples.
- Solo el motor escribe estado de juego. El cliente no tiene `insert` ni `update` sobre nada.
- Estado más eventos. `pet_needs` guarda el estado actual; `pet_events` es el registro inmutable del que salen diario, rachas, álbum y tiempo real.
- Idempotencia por clave única: `client_message_id` en mensajes, `idempotency_key` en eventos, `dedupe_key` en avisos. Reintentar nunca duplica. La clave se reserva antes de llamar al modelo: el mensaje del usuario se inserta como pendiente en la primera transacción, y un duplicado en vuelo recibe un 409 o la respuesta ya guardada.
- Concurrencia explícita. Los dos podéis actuar a la vez sobre la misma mascota: bloquea sus necesidades con `select … for update` dentro de la transacción de la acción.
- `timestamptz` siempre, y la zona horaria de la pareja en `couples.timezone` para “hoy”, las rachas y las horas de silencio.
- Enumerados como `text` con `check`, no como tipos `enum` nativos: añadir un valor es una migración trivial.
- Borrado lógico (`deleted_at`) en lo que alguien pueda querer olvidar; un job borra de verdad pasado un plazo.
- Catálogo y reglas en el repo, como datos versionados, con `rules_version` en cada evento. Cambiar una tasa de decaimiento no reescribe la historia.
- Claves: `uuid` para entidades y `bigint identity` para registros de mucho volumen, como mensajes y eventos.
- Un solo idioma en los identificadores. El documento original mezclaba `user_id` con `ultimo_valor`. Todas las pestañas usan inglés en tablas y columnas; los valores de dominio pueden seguir en español.

## Mapa de tablas

*Diagrama: mapa de tablas · 6 dominios, 18 tablas (en el documento original).*

Las dependencias van en un solo sentido: Memoria lee de Conversación, y Avisos lee de Mascota y juego. El dibujo muestra dieciocho de las veintiséis tablas: las quince del núcleo y tres de avisos y recados; las otras ocho están en la tabla de pareja, avisos y progresión.

## Tablas del núcleo: juego, chat y memoria

Quince tablas bastan para jugar, chatear y recordar.

| Tabla | Columnas clave | Para qué |
| --- | --- | --- |
| `couples` | `id`, `timezone`, `created_at` | La unidad de aislamiento: todo cuelga de aquí |
| `profiles` | `user_id` (PK, a `auth.users`), `couple_id`, `display_name`, `quiet_hours_start`, `quiet_hours_end` | Una fila por persona, con sus horas de silencio |
| `pets` | `id`, `couple_id`, `represents_user_id`, `caretaker_user_id`, `name`, `model_key`, `level`, `xp` | Una mascota por persona representada; la cuida la otra |
| `pet_needs` | `pet_id`, `need`, `value` (0–100), `updated_at`; PK (`pet_id`, `need`) | Último valor y su fecha; el valor actual se calcula al leer |
| `pet_events` | `id`, `couple_id`, `pet_id`, `actor_user_id`, `source` (ui, chat, system), `action`, `payload`, `deltas`, `rules_version`, `idempotency_key` único, `created_at` | Registro inmutable de todo lo que ocurre |
| `persona_traits` | `id`, `couple_id`, `pet_id`, `author_user_id`, `perspective` (self, partner), `category`, `content`, `is_active` | Rasgos atómicos, cada uno con su autor |
| `style_samples` | `id`, `pet_id`, `author_user_id`, `content`, `is_active` | Mensajes reales como ejemplo de voz |
| `persona_versions` | `id`, `pet_id`, `version`, `rendered`, `content_hash`, `token_count` | Ficha renderizada e inmutable; cada mensaje apunta a la suya |
| `conversations` | `id`, `couple_id`, `pet_id`, `user_id`, `started_at`, `last_message_at`, `summary`, `summary_through_message_id`, `memory_extracted_at`, `extraction_version` | Sesión de chat, su resumen rodante y la marca de si ya se extrajeron sus memorias |
| `messages` | `id`, `couple_id`, `conversation_id`, `user_id`, `role`, `content`, `status` (pending, done, failed), `emotion`, `animation`, `proposed_actions`, `client_message_id` único, `persona_version_id`, `prompt_version`, `model`, tokens de entrada, salida y caché, `cost_usd`, `latency_ms`, `stop_reason`, `trace_id`, `forgotten_at` | Cada turno con lo necesario para reproducirlo y costearlo |
| `feedback` | `id`, `couple_id`, `message_id`, `user_id`, `verdict` (not_me, love_it), `note`; único (`message_id`, `user_id`) | El botón “Eso no lo diría yo” |
| `usage_daily` | `user_id`, `day`, `turns`, `input_tokens`, `output_tokens`, `cost_usd`, `minute_start`, `minute_turns`; PK (`user_id`, `day`) | Topes por minuto, por día y de gasto, comprobados y sumados en una sola sentencia |
| `memories` | Ver su sección más abajo | Memoria a largo plazo |
| `memory_retrievals` | `message_id`, `memory_id`, `rank`, `score` | Qué recuerdos vio el modelo en cada turno; base de los criterios 9, 10 y 14 |
| `diary_entries` | `pet_id`, `day`, `content`, `visibility`; PK (`pet_id`, `day`) | Un resumen por día |

Las tasas de decaimiento no están en ninguna tabla a propósito: viven en el código del motor, versionadas.

Modo espejo (decidido): añade `conversations.mode` con los valores `normal` y `mirror`, y `feedback.source` con `chat` y `mirror`. Las conversaciones espejo no pasan por la extracción de memorias ni generan eventos de juego.

## Tablas de pareja, avisos y progresión

Once tablas más; ninguna obliga a cambiar las del núcleo.

| Tabla | Columnas clave | Nota |
| --- | --- | --- |
| `push_subscriptions` | `id`, `user_id`, `endpoint` único, `p256dh`, `auth`, `last_ok_at`, `revoked_at` | Una fila por dispositivo; se revoca cuando el envío falla de forma definitiva |
| `scheduled_notifications` | `id`, `couple_id`, `pet_id`, `kind`, `due_at`, `schedule_name`, `status`, `dedupe_key` único | Permite cancelar un aviso y no enviarlo dos veces |
| `errands` | `id`, `couple_id`, `from_user_id`, `to_user_id`, `via_pet_id`, `original_text`, `delivered_text`, `status`, `delivered_at` | Recados: texto original y versión con la voz de la mascota |
| `coin_ledger` | `id`, `couple_id`, `user_id`, `delta`, `reason`, `ref_type`, `ref_id`, `created_at` | Libro de movimientos; el saldo es la suma, nunca un campo que se edita |
| `inventory` | `couple_id`, `user_id`, `item_key`, `qty` | Lo comprado y aún no consumido |
| `item_affinities` | `pet_id`, `item_key`, `affinity` (−2 a 2) | Los gustos reales aplicados al catálogo |
| `couple_streaks` | `couple_id`, `current`, `best`, `last_day` | Caché derivada de `pet_events`; siempre se puede recalcular |
| `achievements` | `couple_id`, `user_id`, `key`, `unlocked_at` | Logros desbloqueados |
| `quiz_attempts` | `id`, `couple_id`, `pet_id`, `trait_id`, `asked_user_id`, `answer`, `is_correct` | El quiz pregunta sobre rasgos reales del perfil |
| `minigame_scores` | `id`, `user_id`, `game`, `score`, `created_at` | Puntuaciones comparadas |
| `album_entries` | `id`, `couple_id`, `kind`, `message_id` o `event_id`, `caption` | Recuerdos destacados |

Regalos, visitas y misiones no necesitan tabla propia al principio: son eventos en `pet_events` con su `action`.

## Acceso: roles, RLS y Realtime

RLS solo es una red de seguridad real si la API no entra con un rol que se la salta. Hay seis caminos a la base de datos y cada uno merece su rol.

| Quién | Cómo entra | Rol de Postgres | Qué puede |
| --- | --- | --- | --- |
| Front (PWA) | `supabase-js` con clave publicable; login con Google y TOTP, JWT con aal2 | `authenticated` | Login y Realtime. `select` en `pet_needs` y `pet_events` de su pareja, solo para autorizar la señal de Realtime; el contenido lo pide a la API |
| API (Lambda) | Postgres por el pooler, modo transacción | `twochi_api`, propio | Leer y escribir en `app`, con RLS aplicada |
| Worker (Lambda) | Igual | `twochi_worker`, propio | Barridos entre parejas, memorias, resumen de sesión y diario, con políticas propias en las tablas que usa y sin `BYPASSRLS` |
| Migraciones (CI) | Conexión de sesión | `postgres` | Cambios de esquema |
| Tú, como admin | Supabase Studio | `postgres` | Todo |
| MCP de administración, en tu PC | Postgres por el pooler, modo transacción | twochi_admin, propio | Solo lectura sobre app, con contenido. Exige la aceptación expresa de tu pareja |

### La API y RLS: dos opciones
- A, autorización solo en código. El rol de la API se salta RLS. Cada función del repositorio recibe el `couple_id` del JWT verificado y un test comprueba que ninguna consulta lo omite. Es lo que implica hoy el documento.
- B, RLS también para la API (decidida). Al abrir cada transacción, la API hace `set local role authenticated` y carga los claims del JWT con `set_config('request.jwt.claims', …, true)`. Las mismas políticas protegen front y API, y un fallo en una consulta no cruza parejas.

La opción B son unas diez líneas en el gestor de transacciones. Como todo es `local`, es compatible con el pooler en modo transacción; confírmalo con un test de dos parejas antes de darlo por bueno.

### Privacidad entre los dos: políticas por persona

Decidido el 21 nov. Con una sola pareja real, la política por `couple_id` no separa nada: la frontera que importa es persona a persona. Cinco tablas guardan contenido privado y llevan además una política por persona.

| Tabla | Quién puede leer la fila |
| --- | --- |
| `conversations` | Quien conversa: `user_id` |
| `messages` | Quien conversa: `user_id` |
| `memories` | Quien lo contó, o cualquiera de los dos si `visibility = 'couple'` |
| `memory_retrievals` | Quien envió el mensaje al que pertenece |
| `feedback` | Quien lo marcó: `user_id` |

```
create policy speaker_read on app.memories
  as restrictive for select to authenticated
  using (visibility = 'couple'
         or speaker_user_id = (select auth.uid()));

```
- Restrictiva, como la de `aal2`: se suma a la política por pareja en vez de sustituirla.
- Test por tabla: dos personas de la misma pareja; una no lee lo privado de la otra, ni por la API ni con su propio token.
- Trabajos de sistema: el worker abre `db.transaction(SystemActor(job))` con el rol `twochi_worker`, que tiene políticas propias solo en las tablas que usa. Ningún rol lleva `BYPASSRLS`, y `twochi_api` no tiene políticas propias: sin `set local role` no lee nada.
- Tu lectura como admin, en Studio y en el MCP, sigue siendo la excepción aceptada.

### Forma de las políticas
```
create policy couple_read on app.pet_events
  for select to authenticated
  using (couple_id = (select app.current_couple_id()));

create index on app.pet_events (couple_id, created_at desc);

```
- `couple_id` en el JWT: un Custom Access Token Hook de Supabase lo añade como claim al emitir el token, y `current_couple_id()` lo lee de `auth.jwt()` ([Supabase](https://supabase.com/docs/guides/auth/auth-hooks/custom-access-token-hook)).
- Envuelve la función en `select`: Postgres la evalúa una vez por consulta y no por fila ([Supabase](https://supabase.com/docs/guides/troubleshooting/rls-performance-and-best-practices-Z5Jjwv)).
- Indica el rol con `to authenticated` e indexa la columna de la política.
- Prueba las políticas: dos parejas de ejemplo y un test por tabla que confirme que una no ve a la otra.

### Realtime
- Postgres Changes como señal (decidido el 21 nov): añade `pet_needs` y `pet_events` a la publicación `supabase_realtime`; cada evento se autoriza contra RLS por suscriptor ([Supabase](https://supabase.com/docs/guides/realtime/postgres-changes)). El front se suscribe con `select` de `id`, `pet_id` y `created_at`, y al llegar un evento refresca por la API. Por defecto Realtime enviaría la fila entera, con `payload` y `actor_user_id`, a los dos.
- Los eventos `DELETE` no pasan por RLS. No borres filas en las tablas publicadas; `pet_events` ya es de solo inserción.
- Tablas en esquema privado: necesitan `grant select` al rol `authenticated` además de la política.
- Necesidades en el front: la API devuelve por necesidad `value`, `updated_at` y `rate_per_hour`, ya con el estado aplicado (despierta o dormida). El front interpola en línea recta y no copia ninguna regla del motor.
- Vuelta del segundo plano: el front refresca todo por la API; los eventos perdidos no se reenvían.

### Conexión desde Lambda
- Pooler compartido en modo transacción, puerto 6543, que es IPv4 en todos los planes ([Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres)).
- Sin prepared statements: en `asyncpg`, `statement_cache_size=0`.
- SSL en `require` y una sola conexión por contenedor de Lambda, abierta en el primer uso.
- Claves nuevas: usa la publicable y la secreta; `anon` y `service_role` se retiran a finales de 2026 ([Supabase](https://supabase.com/docs/guides/getting-started/migrating-to-new-api-keys)).
- Backups: con una base tan pequeña, haz el volcado a S3 cada día, no cada semana. El bucket caduca los volcados a los 30 días, también las versiones antiguas: es lo que hace que «olvidar» se cumpla.

## Tabla `memories` y embeddings

La tabla guarda la frase, su vector y todo lo necesario para corregirla, olvidarla o migrar de modelo.
```
create table app.memories (
  id                 uuid primary key default gen_random_uuid(),
  couple_id          uuid not null references app.couples,
  pet_id             uuid not null references app.pets,
  subject_user_id    uuid references app.profiles,   -- de quién habla
  speaker_user_id    uuid references app.profiles,   -- quién lo contó
  visibility         text not null default 'speaker'
                     check (visibility in ('speaker', 'couple')),
  kind               text not null check (kind in
                     ('fact','preference','event','plan','joke','episode')),
  content            text not null,
  content_hash       text not null,
  importance         smallint not null check (importance between 1 and 10),
  occurred_at        timestamptz,
  source_conversation_id uuid references app.conversations,
  source_message_ids bigint[] not null default '{}',
  embedding          extensions.vector(1024) not null,
  embedding_model    text not null,
  extraction_version text not null,
  fts                tsvector generated always as
                     (to_tsvector('spanish', content)) stored,
  last_accessed_at   timestamptz,
  access_count       integer not null default 0,
  superseded_by      uuid references app.memories,
  deleted_at         timestamptz,
  created_at         timestamptz not null default now(),
  unique (pet_id, content_hash)
);

create index memories_active on app.memories (pet_id)
  where superseded_by is null and deleted_at is null;
create index memories_fts on app.memories using gin (fts);

```

| Decisión | Elección | Motivo |
| --- | --- | --- |
| Modelo | `voyage-4-large` para documentos y consultas | La mejor calidad multilingüe de la serie; unos 100.000 tokens al mes caben de sobra en los 200 millones gratuitos ([Voyage](https://docs.voyageai.com/docs/embeddings)) |
| Si la consulta tarda | Consultas con `voyage-4-lite` | Toda la serie 4 comparte espacio vectorial: no hay que re-embeber nada |
| Dimensiones | 1.024, el valor por defecto | También admite 256, 512 y 2.048; a este volumen no hay nada que optimizar |
| `input_type` | `document` al guardar, `query` al buscar | Voyage antepone una instrucción distinta a cada uno |
| Tipo de columna | `vector(1024)` | `halfvec` ocupa la mitad; no hace falta con miles de filas |
| Índice vectorial | Ninguno al empezar | Búsqueda exacta filtrada por mascota: 100% de recall en milisegundos |
| Distancia | Coseno, operador `<=>` | Funciona igual estén o no normalizados los vectores |
| `visibility` | Por defecto `speaker` | Decidido: lo contado es privado y solo se comparte lo que se marque |
| Privacidad | Revisar en Atlas el uso de datos para entrenamiento | MongoDB puede usar lo enviado a la API para mejorar los modelos; se gestiona por organización ([MongoDB](https://www.mongodb.com/docs/voyageai/management/model-training-data/)) |

