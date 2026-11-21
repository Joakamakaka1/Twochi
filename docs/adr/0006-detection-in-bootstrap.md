# 0006. GuardDuty y los avisos de seguridad viven en `bootstrap`

- Estado: aceptada
- Fecha: 2026-11-22
- Se aparta de AWS, «GuardDuty», y del árbol de `infra/` en CI/CD e IaC, que ponían GuardDuty en el stack

## Contexto

El documento activa GuardDuty en todas las regiones desde `infra/stack` y manda sus hallazgos por una regla de EventBridge al tema SNS de las alarmas de CloudWatch. Una revisión de seguridad de `infra/bootstrap` encontró dos problemas en ese diseño:

- Quien escribe GuardDuty puede apagarlo, archivar sus hallazgos o cederlo a otra cuenta. En el stack, esa escritura la tendría `twochi-apply`, de modo que un solo `apply` aprobado podría desactivar la vigilancia que debe detectarlo. El PR #10 ya le niega toda escritura de GuardDuty.
- Los roles de CI solo actúan en `eu-west-1`, `us-east-1` y `eu-north-1`. Para que el stack gestionara GuardDuty y una regla en cada región, ese filtro necesitaba excepciones, y con ellas los roles de CI podían leer los hallazgos de todas las regiones. Como los logs de Actions son públicos, un PR podría publicarlos.

## Decisión

- `infra/bootstrap/detection.tf` crea un detector de GuardDuty en cada región habilitada (data source `aws_regions`; hoy son 18, `eu-south-2` incluida). Solo quedan activos los planes que tienen algo que mirar aquí: S3 y la red de las Lambdas. EKS, Malware Protection para EC2, RDS y Runtime Monitoring se declaran desactivados.
- Los hallazgos de cada región pasan a la región central por EventBridge: una regla `twochi-guardduty-forward` en cada región los envía al bus `default` de `eu-west-1`, con el rol `twochi-findings-forwarder`. EventBridge solo admite buses de eventos como destino en otra región, así que el tema no puede ser el destino directo.
- En `eu-west-1`, dos reglas centrales publican en el tema `twochi-security-alerts`. La primera recoge los hallazgos de GuardDuty de todas las gravedades, porque el uso de las credenciales de root es de gravedad baja. La segunda recoge los hallazgos activos de Access Analyzer. El tema envía el evento completo, sin transformar, a un correo que se pasa en la variable `alert_email` y nunca entra en git.
- El tema solo acepta publicaciones de esas dos reglas. No lleva clave propia: la gestionada `aws/sns` no deja publicar a EventBridge, y una clave propia costaría más que todo lo demás para proteger algo que acaba en un correo en claro.
- `twochi-apply` tiene permisos sobre los temas, reglas y roles `twochi-*`. Por eso un `Deny` le impide tocar este tema, su suscripción y estas reglas, salvo para leerlos, y el rol de reenvío entra en la lista de IAM protegida de `bootstrap`.
- Los roles de CI dejan de leer GuardDuty, y el filtro de regiones ya no tiene excepciones.
- Este tema es solo para la detección. Las alarmas de CloudWatch del stack tendrán un tema propio en el stack.

## Consecuencias

- Cambiar la detección requiere un `apply` de `bootstrap` hecho a mano por una persona, como el resto de esta carpeta. Si se habilita una región nueva, el siguiente `apply` de `bootstrap` la cubre.
- Una ruta más para cada aviso: cuando no llegue un correo, hay que mirar las métricas `FailedInvocations` de la regla de reenvío de la región y de la regla central.
- Coste: GuardDuty da 30 días de prueba por región y después cobra por volumen. Las regiones vacías solo procesan los eventos de los servicios globales. EventBridge cobra cada evento reenviado como evento personalizado, y SNS envía 1.000 correos gratis al mes. En total se esperan céntimos al mes.
- El documento cambia en AWS («Cuenta, créditos e identidad», «Conexiones y permisos» y «GuardDuty») y en el árbol de `infra/` de CI/CD e IaC.
