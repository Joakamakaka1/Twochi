# 0013. Tickets en paralelo: un hueco por agente, con su worktree y su base local

- Estado: propuesta (la acepta la fusión de su PR)
- Fecha: 2026-11-22
- Cierra el «a validar» de Forma de trabajo, «Subagentes en paralelo sobre la misma base local y el mismo emulador», y cambia «Quién arranca cada ticket»: el orquestador deja de llevar un solo ticket a la vez

## Contexto

Hasta hoy el orquestador tomaba un ticket, esperaba su PR y su fusión, y solo entonces tomaba el siguiente. Los doce PR del 21 y 22 de noviembre (#13 a #24) tardaron entre 8 y 111 minutos del primer commit a la fusión, uno detrás de otro.

Tres cosas impedían ir en paralelo:

- **La base local es una.** `just check` termina con `supabase db reset` (`check-dump`), y los tests escriben en ella. Dos agentes en la misma instancia se borran los datos entre sí.
- **`/implement-spec` no sirve aquí.** Integra todos los tickets en una rama y un PR, y choca con «un PR, una rebanada».
- **Hay ficheros que casi todos los tickets tocan**: las migraciones, los lockfiles, `GLOSSARY.md`, el `justfile`.

## Decisión

### Un hueco por agente

Un hueco es un `git worktree` en `.claude/worktrees/slot-N`, en la rama del ticket, con su propia instancia de Supabase:

- `supabase/config.toml` del hueco lleva `project_id = "twochi-sN"` y los puertos desplazados cien por hueco (la carpeta principal usa 553xx; el hueco 1, 554xx; el 2, 555xx).
- Ese fichero se marca con `git update-index --skip-worktree`: el cambio no entra en ningún commit.
- La instancia arranca con los mismos servicios que el CI (`db`, `auth` y `kong`).
- Los tests reciben sus tres direcciones por `TWOCHI_TEST_ADMIN_URL`, `TWOCHI_TEST_DATABASE_URL` y `TWOCHI_TEST_BACKUP_URL`, que `conftest.py` ya leía.
- Los servidores de desarrollo usan puertos propios del hueco.

La carpeta principal es el hueco 0 y es del orquestador. Los huecos se montan hoy a mano; `just slot` los automatiza en TWO-43.

### Qué puede ir a la vez

Dos tickets van en paralelo si cumplen las tres condiciones:

1. Ninguno bloquea al otro en Linear, ni directa ni indirectamente.
2. Sus zonas no se cruzan. Antes de lanzarlos, el orquestador escribe para cada ticket la lista de rutas que espera tocar (del texto del ticket y de `git log --stat` de tickets parecidos) y comprueba que no comparten ninguna fuera de los puntos calientes de abajo.
3. Como mucho uno de los dos toca un punto caliente de dueño único.

Un ticket ya fusionado sigue «In Progress» hasta que se despliega, porque cerrado es desplegado. Para la frontera cuenta como hecho: lo que depende de su código se puede tomar, y lo que depende de que esté en producción (el humo, por ejemplo) sigue esperando.

Al terminar cada agente, el orquestador compara lo previsto con `git diff --name-only origin/main...rama` de cada rama. Una ruta en dos ramas que no estaba prevista se resuelve antes de abrir el segundo PR.

### Puntos calientes

| Punto caliente | Regla |
| --- | --- |
| Migraciones (`supabase/migrations/`) | Un solo ticket con migración a la vez. Su número lo da el orquestador al lanzarlo. Si otro PR con migración se fusiona antes, la migración se renumera al hacer el rebase |
| `supabase/config.toml` | Solo en el hueco 0, en serie: en los demás está reescrito y fuera del índice |
| Lockfiles (`uv.lock`, `pnpm-lock.yaml`) y los `package.json` y `pyproject.toml` | Un dueño por lockfile y por tanda. Tras fusionar, los demás regeneran el suyo en el rebase, nunca resuelven el conflicto a mano |
| `GLOSSARY.md` | Los términos nuevos los escribe el orquestador antes de lanzar la tanda, en el PR del primer ticket que los usa |
| Contratos compartidos: el OpenAPI y su cliente generado, el contrato del turno, los puertos de `twochi_application` | Un dueño por tanda. Quien consume un contrato que otro ticket de la tanda cambia espera a su fusión |
| `justfile` y `.github/` | Cada ticket añade solo sus líneas, sin reordenar ni reformatear. Dos tickets que cambian la misma receta van en serie |

### Orden de fusión

- Se fusiona de uno en uno, primero el PR que más tickets desbloquea y, a igualdad, el más pequeño.
- Tras cada fusión, cada rama abierta trae `origin/main` con un `merge` (nunca `push --force`, como ya hacen las ramas apiladas), repite `just check` entero en su hueco y solo entonces su PR vuelve a ser candidato.
- Si dos PR chocan, gana el que ya está fusionado. El otro agente resuelve en su hueco; si el choque es de diseño y no de texto, el segundo ticket vuelve a la frontera con un comentario y pasa a depender del primero en Linear.
- Los PR de zonas delicadas avanzan igual en paralelo: lo único que espera es su fusión, que es de una persona.

### Concurrencia

- Dos agentes a la vez. Se sube a tres o cuatro solo tras una tanda limpia: ningún choque fuera de lo previsto, ningún test que falle por datos de otro y `just check` en verde en todos los huecos.
- Cada instancia con los servicios del CI ocupa unos cientos de megas; este PC tiene 32 GB. El límite real es el uso del plan Max: cada agente gasta como una sesión, y la revisión de un PR delicado añade dos subagentes.
- El orquestador no implementa mientras hay agentes trabajando: prepara la tanda siguiente, revisa y atiende la cola.

### El tope de cinco PR sin desplegar

El tope existe para que un lote se revierta fácil. Con paralelismo se alcanza antes, y hoy se alcanza por otro motivo: las migraciones todavía no se despliegan (TWO-32), así que cada PR con migración se queda sin desplegar.

Propuesta, que decide una persona porque cambia un control:

- Contar solo los PR **desplegables**: los que cambian lo que `deploy.yml` lleva a producción. Los de documentos, tests, CI y herramientas locales no cuentan.
- Mantener el cinco para los desplegables.
- Al llegar a cuatro, el orquestador deja en la cola el resumen del despliegue ya escrito (PR que entran, zonas delicadas, migraciones y plan), para que el clic no espere a que alguien lo prepare.

Hasta que se decida, el tope sigue como está.

## Prueba

Ejecutada el 22 de noviembre de 2026 en este PC, con la carpeta principal en `main` (9088fe4) y un worktree en el mismo commit:

| Qué | Carpeta principal, 553xx | Hueco 1, 554xx |
| --- | --- | --- |
| `supabase start` del hueco, servicios del CI | — | 32 s |
| `check-db` y `check-py` lanzados a la vez | 339 tests en verde, 50,5 s | 339 tests en verde, 50,4 s |
| `supabase db reset` y `check-dump` lanzados a la vez | volcado restaurado, 98 s | volcado restaurado, 69 s |
| Filas en `auth.users` al acabar | 2, las del seed | 2, las del seed |

`check-dump` reconstruye la base entera dos veces. Que las dos instancias acaben con su seed y con el volcado comparado fila a fila dice que ninguna tocó a la otra.

Lo que la prueba no cubre:

- El emulador de AWS, que el repositorio todavía no usa. Cuando entre, cada hueco necesitará su instancia o sus prefijos, y se prueba entonces.
- `check-web` y `check-infra` en paralelo: no comparten estado fuera del worktree, y no se midieron.
- Más de dos instancias a la vez.

## Consecuencias

- Un agente que olvide exportar las tres variables prueba contra la base de la carpeta principal. Hasta TWO-43, el encargo de cada agente las lleva escritas, y el orquestador comprueba el seed de la carpeta principal al cerrar la tanda.
- Un ticket que necesita cambiar `supabase/config.toml` no puede ir en un hueco: va en serie, en la carpeta principal.
- `skip-worktree` esconde también un cambio legítimo de ese fichero que llegue de `main`: un `merge` que lo toque falla con un aviso, y el hueco se rehace.
- Las instancias de los huecos quedan arrancadas hasta que alguien las para. El orquestador las para al cerrar la sesión.
- La cola de fusión de una persona crece más deprisa: con dos agentes, el tiempo de espera de sus PR pasa a ser lo que más pesa en el plazo.
