# 0004. Borde: Function URL con OAC, con API Gateway REST como plan B

- Estado: aceptada; la opción 1 queda pendiente de validar desplegada (TWO-8)
- Fecha: 2026-11-21

## Contexto

AWS, «Borde», decide la opción 1 (Function URL con OAC) con medio día de caja y deja la opción 2 (API Gateway REST en modo streaming) como plan B. La opción 1 tiene tres requisitos que la documentación de AWS no menciona y que Cronista ya resolvió en esta misma cuenta: el POST necesita el hash del cuerpo, el JWT no puede ir en `Authorization`, y la política de petición al origen debe dejar pasar las cabeceras del navegador salvo `Host`. Dos dudas solo se resuelven desplegando: que el plan flat-rate Free admita un origen Function URL y que la regla de país pueda escribirse como «todo salvo dos países».

## Decisión: opción 1

| Pieza | Cómo queda | Dónde |
| --- | --- | --- |
| Function URL | `AuthType: AWS_IAM`, modo `BUFFERED` hasta que entre el SSE | `infra/stack/api.tf` |
| Permisos de invocación | `lambda:InvokeFunctionUrl` y `lambda:InvokeFunction` (`invoked_via_function_url`), los dos condicionados al ARN de la distribución | `infra/stack/api.tf` |
| OAC | Tipo `lambda`, firma siempre con SigV4 | `infra/stack/edge.tf` |
| `/api/*` | Caché desactivada (`Managed-CachingDisabled`) y `Managed-AllViewerExceptHostHeader` | `infra/stack/edge.tf` |
| Hash del cuerpo | El navegador envía el SHA-256 en `x-amz-content-sha256`, calculado con `crypto.subtle` | `apps/web/src/shared/api/signedFetch.ts` |
| JWT | En `X-Twochi-Auth`; CloudFront firma en `Authorization` y el envoltorio de `fetch` borra cualquier `Authorization` | El mismo fichero y `apps/api/src/twochi_api/auth.py` |
| Verificación | La API comprueba firma con el JWKS en caché, emisor, audiencia, caducidad, `sub` y `aal2`. El `user_id` sale siempre de ahí | `apps/api/src/twochi_api/auth.py` |
| Sonda | `POST /api/pings` autenticado devuelve el `user_id` y el `nonce`; `GET /api/health` sin token | `apps/api/src/twochi_api/app.py` |

Todo lo de `/api/*` usa solo políticas gestionadas, porque el plan Free no admite políticas propias de caché ni de petición al origen.

## Cómo se valida (TWO-8)

Medio día de caja desde el primer despliegue, desde España o Polonia:

1. `POST /api/pings` desde el navegador, con cuerpo y JWT `aal2`: 200 con el `user_id`.
2. El mismo POST sin `x-amz-content-sha256`, o con un hash que no cuadra: lo rechaza Lambda, no la API.
3. La Function URL llamada directamente: 403.
4. Al suscribir el plan flat-rate (TWO-15): ¿admite el origen Function URL y la regla «todo salvo ES y PL»?

Síntoma típico si algo falta: GET funciona y POST devuelve 403. Se diagnostica con los logs de la Lambda (con el usuario de solo lectura, TWO-12) y la respuesta de CloudFront.

## Plan B: API Gateway REST en modo `STREAM`

Entra sin más discusión si en medio día no pasa el punto 1, o si el plan flat-rate rechaza el origen Function URL.

| Pieza | Cambio |
| --- | --- |
| Entrada | Una API REST regional con integración proxy a `twochi-api` en modo de respuesta `STREAM`, una etapa `prod` y unas 60 líneas de Terraform. HTTP API no sirve: no hace streaming |
| Function URL | Se borra, junto con sus dos permisos y su OAC. Lambda se invoca desde API Gateway con un permiso condicionado al ARN de la API |
| CloudFront | `/api/*` apunta a la API como origen propio. Conserva el dominio, el WAF y el filtro por país |
| JWT | Vuelve a `Authorization: Bearer`. En la API cambia la constante `AUTH_HEADER`, y la verificación acepta ya el prefijo `Bearer` |
| Hash del cuerpo | Sobra: el envoltorio de `fetch` deja de calcularlo |
| Saltarse el borde | CloudFront añade una cabecera de origen con un valor secreto, y la API rechaza lo que no la traiga |

Lo que el plan B obliga a decidir: esa cabecera vive en la configuración de la distribución, y por tanto en el estado, que el ADR 0003 quiere sin secretos. Su valor solo protege el WAF (el JWT sigue decidiendo quién entra), así que se acepta en el estado si entra el plan B, se rota escribiéndolo de nuevo y se registra en este ADR. Alternativa si eso no convence: la política de recursos de la API REST limitada a las IP de origen de CloudFront, a cambio de mantener esa lista.

Límites que no cambian: 30 s entre paquetes en CloudFront, y Lambda Web Adapter detrás de API Gateway en modo `STREAM` queda por validar.

## Consecuencias

- Mientras la opción 1 no esté validada, el contrato de `fetch` (hash y cabecera propia) es provisional; ningún componente llama a `fetch` directamente, así que cambiarlo es tocar un fichero.
- La sonda `/api/pings` se queda: es la ruta autenticada de la prueba de humo.
