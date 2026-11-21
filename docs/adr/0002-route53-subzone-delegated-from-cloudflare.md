# 0002. Subzona `twochi.jcvstro.dev` en Route 53, delegada desde Cloudflare

- Estado: aceptada
- Fecha: 2026-11-21

## Contexto

CI/CD e IaC da por hecho que la zona del dominio ya está en Route 53 y que Terraform crea el registro y valida el certificado de ACM sin pasos manuales. No es así: `jcvstro.dev` se sirve desde Cloudflare (sus NS son `*.ns.cloudflare.com`, comprobado el 21 de noviembre de 2026). Otros dos hechos del mismo día pesan en la decisión:

- `jcvstro.dev` tiene registros CAA en Cloudflare que autorizan a Comodo, DigiCert, Let's Encrypt, Google y SSL.com, pero no a Amazon. Una búsqueda CAA se detiene en el nombre más cercano que tenga alguno, así que, sin un CAA propio en `twochi.jcvstro.dev`, ACM no puede emitir su certificado ([AWS](https://docs.aws.amazon.com/acm/latest/userguide/setup-caa.html)).
- `jcvstro.dev` no publica registro DS: no hay DNSSEC que encadenar.

## Decisión

Una zona alojada `twochi.jcvstro.dev` en Route 53, delegada desde Cloudflare con cuatro registros `NS`.

- La zona se declara en `infra/bootstrap`, con `prevent_destroy`, y no en el stack. Sus servidores NS se copian a mano en Cloudflare: una zona recreada recibiría otros y rompería la delegación. El stack la lee por nombre y crea en ella sus registros: el alias a CloudFront y la validación del certificado.
- La misma carpeta crea el CAA de la subzona: `issue` para `amazon.com`, `amazontrust.com`, `awstrust.com` y `amazonaws.com`, y `issuewild ";"`, porque no hace falta ningún certificado comodín.
- En Cloudflare, los cuatro `NS` con nombre `twochi`, sin proxy. Es un paso manual de una sola vez (TWO-14), tras el primer `apply` del arranque.
- La zona se adjunta al plan flat-rate de CloudFront al suscribirlo, como ya pide AWS, para que su coste quede dentro del plan.

## Alternativas descartadas

- Mover `jcvstro.dev` entero a Route 53: cambia el DNS de todo el dominio por un subdominio, y el resto del dominio no es de Twochi.
- Registros de Twochi directamente en Cloudflare: el certificado y el alias se crearían a mano en cada cambio, o el pipeline necesitaría un token de la API de Cloudflare, un secreto más con escritura sobre todo el dominio.

## Consecuencias

- Terraform crea los registros y valida el certificado sin pasos manuales, como pedía el documento, una vez hecha la delegación.
- La delegación es el único paso manual y no se repite. Si se borrara la zona (no se puede sin quitar `prevent_destroy`), habría que copiar los NS nuevos.
- La subzona queda sin DNSSEC, como el dominio padre. Firmarla exigiría un DS en Cloudflare y una clave KMS en `us-east-1`; no aporta nada mientras el padre no firme.
- Coste: 0,50 $ al mes por la zona alojada más IVA, salvo que quede cubierta por el plan flat-rate al adjuntarla. Las consultas a registros alias de CloudFront no se cobran ([AWS](https://aws.amazon.com/route53/pricing/)).
