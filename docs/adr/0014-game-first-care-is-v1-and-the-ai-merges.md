# 0014. El juego primero: la v1 es el cuidado, la IA fusiona y el despliegue va por su carril

- Estado: aceptada
- Fecha: 2026-11-22
- Cambia Forma de trabajo («Quién fusiona», «Siempre pregunta», «Cerrado es desplegado» y el recorte de alcance) y la pestaña principal («Pantallas de la v1»). Decide lo que el ADR 0013 dejó propuesto sobre el tope de cinco PR

## Contexto

La auditoría del 22 de noviembre midió dónde se iba el tiempo. No era en escribir el juego: en hora y cincuenta minutos salieron cuatro tickets con su revisión. Se iba en tres esperas:

- Cada PR esperaba la fusión de una persona, y el check `flujo` marcaba como delicados once de los últimos doce.
- Los tickets no se cerraban hasta desplegarse, y el despliegue de migraciones y front espera a Bitwarden (TWO-10). El tope de cinco PR sin desplegar ya estaba alcanzado.
- La v1 eran nueve pantallas y solo dos tenían spec.

El juego es cerrado, para dos personas. Lo que tiene valor es que se pueda jugar; lo que lleva tiempo es la infraestructura y el cuidado con que se hace, y ese cuidado se mantiene.

## Decisión

### Qué es la v1

- Como mínimo, todo lo que es cuidar a la mascota: las cinco necesidades, las cuatro habitaciones, las acciones, los gustos reales, las emociones visibles, ponerse triste o enferma y recuperarse, y la mascota en 3D sobre el fondo de cada habitación.
- Después, por este orden y sin bloquear la v1: la conversación con IA, el vínculo de pareja y los extras (tienda, progresión y minijuegos). Lo que no llegue queda para la siguiente versión.
- Bonita y jugable, no perfecta. El pulido de interfaz se hace después, con el juego ya en uso.
- Los GLB y los fondos reales llegan cuando estén localizados. Hasta entonces, una figura y unos fondos de relleno ocupan su sitio detrás de la misma costura.

### El juego primero, el despliegue por su carril

- Un ticket del juego se cierra cuando su PR está fusionado y el cambio se ha comprobado en local: `just check` y, si se ve, la app en el navegador. Ya no espera al despliegue.
- El despliegue es un carril aparte, con sus tickets (TWO-32, TWO-36, TWO-46 y los de la cola humana que lo desbloquean). «Cerrado es desplegado» sigue valiendo dentro de ese carril.
- El tope de cinco PR sin desplegar queda en suspenso hasta que el carril de despliegue lleve las migraciones y el front a producción. Desde entonces cuenta solo los PR desplegables, como proponía el ADR 0013.
- A producción se sigue llegando solo por el pipeline y con el clic de una persona.

### Quién fusiona

La IA fusiona los PR, también los de zonas delicadas, cuando se cumple todo esto:

- `ci-ok` en verde y `just check` completo en local sobre la rama con `main` dentro;
- la revisión que pide su tamaño: un subagente, o dos en zona delicada, sin hallazgos altos ni medios abiertos;
- si el cambio se ve, la comprobación en el navegador;
- el cuerpo del PR dice lo que no se pudo comprobar.

Espera a una persona solo el PR que debilita un control: quitar o relajar un check, tocar el ruleset, ampliar permisos de IAM o de un rol de la base, o cambiar cómo se guardan los secretos. Nadie aprueba que se le quite una barrera.

La fusión es siempre squash, de una en una, y nunca con auto-merge ni por la API.

### Con qué se trabaja

- Opus 5.5 en esfuerzo `high` por defecto, para la sesión y para los subagentes. Otro modelo es una excepción que decide una persona.
- El gasto del plan no limita el paralelismo. Tras el piloto limpio del ADR 0013, el orquestador puede llevar hasta tres tickets a la vez.
- El método no cambia: tamaño declarado, test en rojo en su commit, revisión, evidencia y `/retro`. Grilling, spec y tickets los lanza una persona, porque así lo fija el plugin.

### Lo que sigue pidiendo permiso

Borrar algo fuera del repositorio; gastar o subir un tope; crear, rotar o revocar secretos; tocar producción fuera del pipeline; desplegar; usar datos reales vuestros; y debilitar un control. Lo demás, la IA lo hace y lo cuenta después.

Los secretos se siguen usando sin leerlos. Leer uno sin querer no es un incidente: se dice y se sigue.

## Consecuencias

- La frontera crece de golpe: los tickets del juego dejan de depender de TWO-10 y de TWO-13. El humo en producción y vuestras altas pasan a ser el final del carril de despliegue, no el criterio de hecho de cada rebanada.
- Se acumula trabajo sin desplegar. El primer despliegue del juego será un lote grande: lleva su volcado previo y su resumen, y se prueba antes entero en local.
- Sin la fusión de una persona, la revisión de los subagentes es la única lectura crítica de cada PR. Por eso sus hallazgos altos y medios bloquean la fusión, y el PR deja escrito qué se arregló y qué no.
- El check `flujo` sigue exigiendo issue, evidencia y peligro de fusión en las rutas delicadas. Lo que cambia es quién pulsa el botón.
- Los ajustes de permisos de Claude Code no los cambia la IA: el clasificador del modo auto lo impide, y es una barrera que se respeta. Los cambia una persona.
- La conversación con IA sigue necesitando las claves de desarrollo de Anthropic y de Voyage. Son de la cola humana y solo bloquean ese tramo.
