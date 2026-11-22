# Normas de código

Destilado de [Arquitectura y convenciones](docs/arquitectura/arquitectura-y-convenciones.md): solo lo que exige criterio. Lo que fuerza un check (ruff, pyright, import-linter, ESLint, tsc, cobertura) no se repite aquí. Si una norma se incumple dos veces, pasa a check.

## Nombres

- Casos de uso con verbo: `take_turn`, `apply_care_action`. [→](docs/arquitectura/arquitectura-y-convenciones.md#convenciones-de-python)
- Puertos con nombre de papel (`PetVoice`); adaptadores con tecnología y papel (`PydanticAiPetVoice`, `SqsJobQueue`). [→](docs/arquitectura/arquitectura-y-convenciones.md#puertos)
- Sin `utils.py` ni `helpers.py`: cada módulo se llama como su tema. [→](docs/arquitectura/arquitectura-y-convenciones.md#convenciones-de-python)
- Los términos del juego salen de [GLOSSARY.md](GLOSSARY.md); un término nuevo entra allí antes que en el código. [→](docs/arquitectura/arquitectura-y-convenciones.md#qué-cambia-en-las-demás-pestañas)
- Tablas en plural, en inglés y en `snake_case` (las rutas en plural ya las comprueba un test de `apps/api`). [→](docs/arquitectura/arquitectura-y-convenciones.md#convenciones-de-api-y-base-de-datos)
- Front: componentes con exportación con nombre y fichero en `PascalCase`; hooks `useX`. [→](docs/arquitectura/arquitectura-y-convenciones.md#convenciones-del-front)

## Cuándo se crea un puerto

- Solo si al otro lado hay red, dinero o azar; si no, es una función normal. [→](docs/arquitectura/arquitectura-y-convenciones.md#puertos)
- Su PR dice qué hay al otro lado y qué doble lo sustituye en los tests. [→](docs/arquitectura/arquitectura-y-convenciones.md#puertos)
- Cada puerto lleva su doble escrito a mano en `twochi_application.testing`; sin `unittest.mock.patch` en aplicación. [→](docs/arquitectura/arquitectura-y-convenciones.md#puertos)
- No son puertos FastAPI, Pydantic, la configuración, el logging ni las trazas. [→](docs/arquitectura/arquitectura-y-convenciones.md#puertos)

## Qué es regla de dominio

- Lo que es regla va al dominio aunque hable de IA: función pura con tests, no frase del prompt. [→](docs/arquitectura/arquitectura-y-convenciones.md#capas-y-paquetes)
- El modelo propone y el código decide: ninguna regla de juego, privacidad o gasto vive solo en un prompt. [→](docs/arquitectura/arquitectura-y-convenciones.md#principios)
- El dominio es determinista: el reloj y el azar entran por parámetro. [→](docs/arquitectura/arquitectura-y-convenciones.md#principios)
- El dominio solo importa los módulos de la librería estándar listados en el contrato de `pyproject.toml` (sin E/S, reloj ni azar). Añadir uno es una línea en ese contrato con su motivo en el PR.
- Lo esperable es un valor de retorno (`Rejected(reason)`); lo inesperado, una excepción que hereda de `TwochiError`. [→](docs/arquitectura/arquitectura-y-convenciones.md#convenciones-de-python)
- Se valida en el borde y se confía dentro: la entrada se convierte una vez a tipos del dominio. [→](docs/arquitectura/arquitectura-y-convenciones.md#principios)
- Una ruta, un caso de uso: la ruta traduce, llama y traduce, sin lógica propia. [→](docs/arquitectura/arquitectura-y-convenciones.md#capas-y-paquetes)
- El front no copia reglas del motor: interpola con lo que da la API. [→](docs/arquitectura/arquitectura-y-convenciones.md#convenciones-del-front)

## Patrones

- Entran seis, en su forma más corta: puertos y adaptadores, núcleo funcional con borde imperativo, repositorio, unidad de trabajo, agregado en espíritu y objeto de valor. [→](docs/arquitectura/arquitectura-y-convenciones.md#se-usan)
- Eventos de dominio, CQRS, mediador, contenedor de dependencias, ORM y clases base quedan fuera; añadir uno pide ADR con la señal que lo justifica. [→](docs/arquitectura/arquitectura-y-convenciones.md#se-dejan-fuera)
- Funciones antes que clases: una clase aparece cuando hay estado que mantener o un puerto que implementar. [→](docs/arquitectura/arquitectura-y-convenciones.md#convenciones-de-python)
- Ninguna capa, puerto o abstracción entra sin un segundo uso real; una clase base, a la tercera repetición idéntica. [→](docs/arquitectura/arquitectura-y-convenciones.md#principios)
- Nunca una transacción abierta mientras responde el modelo; se relee con bloqueo antes de decidir. [→](docs/arquitectura/arquitectura-y-convenciones.md#un-caso-de-uso-de-principio-a-fin)
- Pydantic solo en los bordes, con la función que mapea a tipos del dominio junto al esquema. [→](docs/arquitectura/arquitectura-y-convenciones.md#convenciones-de-python)

## Trabajo diario

- Un PR, una rebanada: un refactor y una funcionalidad van en PR distintos, primero el refactor. [→](docs/arquitectura/arquitectura-y-convenciones.md#git-y-pull-requests)
- Un bug llega con su test, primero en rojo. [→](docs/arquitectura/arquitectura-y-convenciones.md#tests)
- Los tests pasan por la costura pública: caso de uso o función del motor, nunca un detalle interno. [→](docs/arquitectura/arquitectura-y-convenciones.md#tests)
- Los logs nunca llevan el texto de un mensaje, de una memoria o de la ficha. [→](docs/arquitectura/arquitectura-y-convenciones.md#convenciones-de-python)
- Comentarios y docstrings solo donde explican un porqué. [→](docs/arquitectura/arquitectura-y-convenciones.md#convenciones-de-python)

## Roles de la base

- Un rol de solo lectura se comprueba contra lo que `PUBLIC` concede por defecto: `TEMP`, objetos grandes, cambiar su propia contraseña y las funciones `SECURITY DEFINER`. Lo que no se pueda cerrar se dice en su ADR. [→](docs/adr/0012-dump-with-read-only-role.md)
