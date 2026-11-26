## Tamaño

Delicado: toca `infra/` (la distribución de producción), el CI y el `justfile`.

## Qué cambia

Tamaño: normal, pero toca `infra/` (la distribución de prod).

Hoy una ruta de la PWA como `/pet` recibe el 403 en XML de S3: la distribución no tiene fallback a `index.html`.

- `infra/stack/functions/web_routes.js` es una CloudFront Function (`cloudfront-js-2.0`) de tipo viewer-request en el comportamiento **por defecto**. Reescribe a `/index.html` toda ruta cuyo último segmento no tenga extensión. Los ficheros con extensión pasan tal cual.
- `/api/*` tiene su propio comportamiento, sin función y sin respuestas de error personalizadas, así que sus `application/problem+json` no cambian. Las respuestas de error personalizadas se descartan porque valen para toda la distribución.
- `/api` sin barra final, o con otra capitalización (`/API/...`), no casa con `/api/*`, que distingue mayúsculas. La función no reescribe esas rutas: un cliente de la API recibe un error, nunca la PWA con un 200.
- `infra/stack/edge.tf` añade `aws_cloudfront_function.web_routes` (`publish = true`) y su `function_association` en `default_cache_behavior`.
- Hay tests con `node:test` en `web_routes.test.mjs`, que corren en `just check-infra`. El job `infra` del CI instala `node` con mise, con la versión fijada en `mise.toml`.
- El plan flat-rate Free incluye CloudFront Functions («Serverless edge compute»), pero no KeyValueStore ni llamadas de red, y la función no usa ninguna de las dos ([AWS](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/flat-rate-pricing-plan.html)).

## Evidencia

- `just check` completo en local, en verde:
  - Python, 103 passed;
  - web, 8 passed;
  - actionlint y zizmor;
  - terraform fmt y validate, y tflint;
  - `node --test`, 3 de 3.
- El test falló primero contra un handler que devolvía la petición sin tocar (`'/' !== '/index.html'`) y después pasó en verde.
- Dos revisiones con subagentes, una de corrección y otra de seguridad, sin hallazgos importantes. De sus detalles, el guard de `/api` y el test del segmento con punto ya están en el PR; el resto va en «Peligro de fusión».
- Producción antes del cambio, por DoH y `curl --resolve`:

```
/pet             403 application/xml   <Error><Code>AccessDenied</Code>…
/api/no-existe   404 application/problem+json   {"type":"about:blank","title":"Request failed","status":404,"code":"not_found"}
/api/health      200 application/json
```

## Revisión

Dos subagentes, uno de corrección y otro de seguridad, sin hallazgos altos ni medios. Sus detalles están arreglados o en «Peligro de fusión».

## Antes y después

- Antes: `/pet` da el 403 en XML de S3.
- Después: `/pet` se pide a S3 como `/index.html` y `/api/no-existe` sigue dando 404 en `problem+json`.
- Plan del CI: `1 to add, 2 to change, 0 to destroy`.
  - `+ aws_cloudfront_function.web_routes`.
  - `~ aws_cloudfront_distribution.edge`: solo la `function_association` nueva en `default_cache_behavior`.
  - `~ aws_s3_bucket_policy.web`: cosmético. `data.aws_iam_policy_document.web` lee el ARN de la distribución, y como la distribución tiene cambios pendientes, Terraform pospone su lectura al apply y marca la política como `known after apply`. Las sentencias de entrada son idénticas (mismo `AWS:SourceArn`, `distribution/EXAMPLEDISTID`), así que el apply escribe la misma política. Pasará lo mismo cada vez que cambie la distribución.

## No comprobado

- El plan del CI, hasta que llegue su comentario a este PR.
- El comportamiento desplegado. Tras el deploy se comprobará así:
  - `aws cloudfront test-function` sobre la etapa LIVE (`/pet` → `/index.html`);
  - la asociación, leída de la distribución;
  - `curl` a `/api/no-existe`, que debe dar 404 en `problem+json`.
- `/pet` seguirá dando el 403 de S3 hasta que se suba el front, porque el bucket está vacío.

## Peligro de fusión

Bajo. Solo toca el comportamiento por defecto (la web), y el bucket está vacío. Para deshacerlo basta con revertir el PR y desplegar. Límites que trae el diseño:

- Ninguna ruta del front puede acabar en un segmento con punto (`/u/john.doe` se pediría a S3). Está anotado en `infra/stack/README.md`.
- Todas las rutas comparten la entrada de caché de `/index.html`. El deploy del front debe darle un `Cache-Control` corto o invalidarla, como ya prevé CI/CD e IaC. Eso ya pasaba con `/`.
- Un cambio solo en `web_routes.test.mjs` también dispara un deploy del stack, con un plan sin cambios.

Linear: TWO-21.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
