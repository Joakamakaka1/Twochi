# 0005. Los roles de CI leen el environment de las Lambdas

- Estado: aceptada
- Fecha: 2026-11-21
- Modifica en parte el punto 3 de [ADR 0003](0003-secrets-out-of-terraform-state.md)

## Contexto

ADR 0003 niega `kms:Decrypt` a `twochi-plan` y `twochi-apply`. Lambda cifra el environment de cada función con la clave `aws/lambda` y, cuando alguien llama a `GetFunction`, lo descifra en su nombre: la llamada a KMS lleva la identidad de quien pregunta, así que el `Deny` la alcanza. CloudTrail lo muestra en el plan del PR #11 (run 44936071968): `kms:Decrypt` invocado por `lambda.amazonaws.com` para `twochi-plan`, `AccessDenied` por una denegación explícita en una política de identidad.

Lambda devuelve entonces el environment sin variables y el proveedor de AWS lo lee como «la función no tiene ninguna». Cada plan de CI propone añadirlas de nuevo en `aws_lambda_function.api`, el plan nunca llega a `No changes`, cada deploy re-aplica la misma configuración y un cambio real de variables queda escondido entre ese ruido.

## Decisión

Los roles de CI pueden usar `kms:Decrypt` solo si se cumplen las dos condiciones, cada una en su propio `Deny` de `ci_guardrails`:

- la llamada llega a través de Lambda (`kms:ViaService` = `lambda.eu-west-1.amazonaws.com`);
- el contexto de cifrado es el de una función propia (`kms:EncryptionContext:aws:lambda:FunctionArn` como `arn:aws:lambda:eu-west-1:<cuenta>:function:twochi-*`).

Una llamada directa a KMS no lleva `kms:ViaService` y sigue denegada, aunque la política de la clave `aws/lambda` permita descifrar a cualquier principal de la cuenta con ese contexto. No hace falta ningún `Allow` en IAM: la política de la clave ya lo concede vía Lambda.

La excepción se apoya en el punto 2 de ADR 0003: el environment de una Lambda nunca lleva secretos. Sus valores ya salen en cada plan, y por tanto en los logs públicos de Actions, así que leerlos no publica nada nuevo.

## Consecuencias

- El plan de CI vuelve a mostrar el environment real y a detectar un cambio de variables o una deriva hecha a mano.
- Si una variable de entorno llevara un secreto, ahora la leería un PR. La revisión de un PR del stack ya busca secretos en el estado (ADR 0003); un secreto en el environment es un fallo de esa misma revisión, no algo que este `Deny` deba tapar.
- Si una Lambda cambia a una clave KMS propia, la clave debe permitir el descifrado vía Lambda para estos roles o el ruido vuelve.
