# 0003. Secretos y datos fuera del estado de Terraform y del alcance de CI

- Estado: aceptada
- Fecha: 2026-11-21

## Contexto

CI/CD e IaC ya decide que los secretos no pasan por Terraform: el código concede permisos sobre `/twochi/prod/` de SSM y los valores los escribe el job que lee Bitwarden. Deja abiertas tres cosas, y una revisión de seguridad de `infra/bootstrap` las hizo concretas:

- Quién crea los parámetros. Si el stack los declarara con `aws_ssm_parameter`, su valor acabaría en el estado, o el `plan` fallaría al no poder descifrarlos. Crearlos a mano choca con «ningún recurso creado a mano fuera de `infra/bootstrap`».
- Qué lee el estado. `twochi-plan` lo lee por necesidad, y un PR puede añadir un paso que lo vuelque en los logs de Actions, que son públicos. Hoy el estado no guarda secretos; bastaría un solo recurso descuidado para que los guardara.
- Dónde viven los buckets de datos. En el stack, `twochi-apply` podría cambiar su política o leerlos con un rol nuevo en un solo `apply`.

## Decisión

1. Los parámetros de SSM los crea y actualiza el workflow manual Bitwarden→SSM con `put-parameter` (`SecureString`, clave `aws/ssm`). Terraform no declara ningún parámetro: solo da a cada rol de Lambda `ssm:GetParameter` sobre sus propias rutas.
2. El estado nunca guarda un secreto. En el stack no entran `aws_ssm_parameter` con valor, `random_password`, secretos en variables de entorno de Lambda ni cabeceras secretas de origen. Si algún día hiciera falta, se usan argumentos write-only, que no se guardan en el estado.
3. Los roles de CI no leen secretos ni datos: ningún parámetro de SSM, secreto ni `kms:Decrypt`; ningún objeto fuera de los buckets de estado y de artefactos; ni líneas de log ni mensajes de SQS.
4. Los buckets de larga vida (estado, artefactos, backups y dataset) viven en `infra/bootstrap`, no en el stack. `twochi-apply` no puede cambiar su configuración, purgar versiones ni escribir en los de datos.
5. Los ARN de los roles y los nombres de los buckets van a GitHub como secretos, no como variables: llevan el ID de la cuenta y GitHub solo enmascara los secretos en los logs.

## Consecuencias

- Un parámetro nuevo se añade en dos sitios: el permiso en el stack y el valor en Bitwarden, que el workflow manual lleva a SSM. Si la Lambda arranca antes de que exista, falla al leerlo y se ve en sus logs.
- Una revisión de un PR del stack busca recursos que guarden secretos en el estado, igual que busca `*` en IAM.
- `twochi-apply` necesita `s3:GetObject` en el bucket de artefactos, porque Lambda comprueba ese permiso de quien despliega el zip.
- El plan B del borde necesitaría una cabecera secreta de CloudFront en el estado. Si entra, el ADR del borde decide cómo se trata.
- Se aparta de CI/CD e IaC en un punto: el stack ya no crea el bucket de backups ni el de dataset.
