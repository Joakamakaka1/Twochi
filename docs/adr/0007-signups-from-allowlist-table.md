# 0007. Las altas salen de una tabla que rellena un script local

- Estado: aceptada
- Fecha: 2026-11-22
- Completa Datos y vectores, «Inicio de sesión: Google y doble factor», que no decía dónde vive la lista de dos correos ni cómo nacen la pareja, los perfiles y las mascotas

## Contexto

El hook de altas (Before User Created Hook) rechaza cualquier correo que no sea de la pareja. El documento pone su función en las migraciones, pero el repositorio es público: escribir los correos en la función los publicaría. Además, nada decía cómo se crean la pareja, los perfiles y las mascotas, ni cómo tiene el usuario de humo una mascota que cuidar.

## Decisión

- La lista vive en la tabla `app.signup_allowlist`, con el correo, la pareja y el nombre visible. La migración crea la tabla y el hook; ninguna fila entra en git.
- La receta `just provision` rellena la tabla desde un fichero local ignorado por git. Crea las parejas, sus filas en la lista y los nombres y modelos de las mascotas. Es idempotente y la lanza la IA con tu aprobación cuando escribe en producción.
- El hook acepta un alta solo si el correo está en la lista. Un trigger sobre el alta crea el perfil en su pareja y, cuando llega la segunda persona, las dos mascotas: cada una representa a una persona y la cuida la otra.
- La pareja de prueba tiene al usuario de humo y a un segundo usuario de prueba sin contraseña que nunca entra. Los crea `just provision` con la API de administración, así que existen aunque las altas estén cerradas.
- El trigger es `security definer`, del dueño `postgres` y con `search_path` vacío, y nadie puede llamarlo. El nacimiento lo hace el sistema y no una persona, así que no hay políticas de nadie que aplicar. La alternativa era dar a `supabase_auth_admin` inserts permanentes en cuatro tablas del juego. ADR 0009 descarta `security definer` solo para las escrituras del motor, que sí son de una persona.
- Cada fila de la lista guarda cómo se registra esa persona: la pareja, solo con Google; la pareja de prueba, con correo. El hook solo deja pasar altas con Google: la API de administración no pasa por él, y es como `provision` crea la pareja de prueba, así que nadie legítimo se registra con contraseña. El trigger repite la regla del proveedor para el tiempo anterior a activar el hook. En producción, TWO-13 debería además cerrar el alta por correo (el login con contraseña del humo sigue funcionando) y activar el hook antes de lanzar `provision`.
- Una pareja son dos personas. El trigger rechaza un tercer alta y un nacimiento en el que alguna de las dos ya no está en la lista, en vez de dejar a la pareja sin mascotas sin avisar.
- El fichero es la lista entera: `provision` borra las filas de quien ya no está en él. Un perfil ya creado se queda; la lista solo decide las altas nuevas.
- `just provision` genera la contraseña del usuario de humo, enrola su TOTP y lo verifica. Escribe la contraseña y el secreto en `supabase/.provision/<destino>.smoke.env`, que git ignora, y nunca los imprime. Supabase genera el secreto TOTP y no deja elegirlo. Mientras no exista el proyecto `twochi-dev` de Bitwarden, ese fichero es su único sitio. Decidido contigo el 2026-11-22.

## Alternativas descartadas

- Correos en la función del hook: los publicaría en el repositorio.
- Insertar a mano en Studio: no se repite igual en local, en CI ni para la pareja de prueba.
- Alta en la app con código de invitación: añade una pantalla y un flujo que el documento no pide, para dos personas que ya se conocen.

## Consecuencias

- Hasta que se ejecute `just provision`, el hook rechaza a todo el mundo, también a vosotros dos. El orden es este: migración, `provision`, vuestras altas con Google y TOTP, y después se cierran las altas (TWO-13).
- Cambiar la pareja o añadir una persona es editar el fichero local y volver a lanzar `provision`, no hacer una migración.
- Si se pierde el fichero de credenciales del humo, `provision` no rota nada a ciegas: se para y pide `just provision --rotate-smoke`. Esa opción da al mismo usuario una contraseña y un TOTP nuevos. Borrarlo no sirve, porque su mascota lo impide y un usuario nuevo no vería otro nacimiento.
