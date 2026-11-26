# Twochi

Juego de mascota virtual para una pareja: cada mascota es una caricatura cariñosa de una de las dos personas y la cuida la otra. Cada término lleva entre paréntesis su identificador en el código.

## Personas

**Pareja** (`Couple`):
Las dos personas que juegan juntas. Es la unidad de aislamiento: nada de una pareja llega a otra.
_Evitar_: grupo, cuenta

**Persona representada** (`represents_user`):
La persona de la pareja a la que caricaturiza una mascota.

**Cuidador** (`caretaker`):
La persona que cuida una mascota: siempre la pareja de la persona representada.
_Evitar_: dueño

**Ficha** (`Persona`):
Lo que el juego sabe de una persona para que su mascota hable como ella: rasgos, gustos y ejemplos de voz.
_Evitar_: perfil, persona

**Rasgo** (`PersonaTrait`):
Un dato atómico de la ficha, con su autor y su perspectiva: lo dice la propia persona o su pareja.

**Lista de altas** (`signup_allowlist`):
Los correos que pueden registrarse, cada uno con su pareja, su nombre visible y la mascota que lo representará. La rellena `just provision` desde un fichero local; fuera de ella nadie se registra.
_Evitar_: lista blanca, invitación

**Pareja de prueba** (`test_couple`):
La pareja ficticia del usuario de humo y de un segundo usuario que nunca entra. Existe para que el humo tenga una mascota que cuidar sin tocar el juego de la pareja real.

**Usuario de humo** (`smoke`):
La única cuenta con contraseña: entra con contraseña y TOTP para la prueba de humo en producción.

## Mascota y cuidado

**Casa** (`Home`):
La pantalla donde vive la mascota que cuidas, con cuatro habitaciones: cocina, baño, dormitorio y salón.

**Mascota** (`Pet`):
El avatar 3D de una persona de la pareja, con sus necesidades, su nivel y su voz.
_Evitar_: avatar, personaje

**Necesidad** (`Need`):
Una de las cinco medidas de 0 a 100 que bajan con el tiempo real: hambre (`hunger`), energía (`energy`), higiene (`hygiene`), diversión (`fun`) y cariño (`affection`).
_Evitar_: stat, barra

**Despierta / dormida** (`asleep`):
El estado de la mascota que decide a qué ritmo cambia cada necesidad. Solo su cuidador la duerme y la despierta; nunca se despierta sola.

**Ánimo** (`Mood`):
El estado visible de la mascota, sacado de la media de sus necesidades: feliz, normal, triste o enferma. Una necesidad muy baja la deja como mucho triste.
_Evitar_: humor, felicidad

**Enferma** (`sick`):
El ánimo más bajo. Empieza cuando la media de las necesidades cae muy abajo y dura hasta que el cuidador devuelve todas a un nivel aceptable, aunque la media ya haya subido. Ponerse enferma (`fell_sick`) y curarse (`healed`) quedan anotados en el evento de la acción que lo provocó. Estar enferma no cambia ninguna regla: solo cómo se ve y lo que dice.

**Bocadillo** (`Bubble`):
Una frase corta que dice la mascota en Casa sin pasar por el chat, según su ánimo, lo que pide y lo que acaba de pasar. Es genérica: la voz de su persona la pone el chat.
_Evitar_: mensaje, turno

**Cosquillas** (`tickle`):
La reacción a muchos toques seguidos sobre la mascota. Solo se ve: no cambia ninguna necesidad.

**Acción de cuidado** (`CareAction`):
Lo que hace el cuidador desde la interfaz para cambiar las necesidades: dar de comer una comida, jugar a una actividad, acariciar, bañar, dormir o despertar.
_Evitar_: interacción

**Rechazo** (`Rejection`):
Por qué el motor no aplica una acción de cuidado: no eres el cuidador (`not_caretaker`), está dormida (`asleep`), ya duerme (`already_asleep`), ya está despierta (`already_awake`) o está demasiado cansada para jugar (`too_tired`). No es un error: la mascota lo anima.

**Caricia efectiva** (`effective`):
Una caricia que sube el cariño. Con tres caricias efectivas en la última hora, la siguiente se acepta pero no sube nada y no cuenta como efectiva.

**Acción** (`Action`):
Un cambio de estado que el motor valida y aplica, venga de la interfaz o propuesto en el chat.

**Catálogo** (`catalog`):
Las comidas y las actividades que el cuidador puede elegir, las mismas para las dos mascotas y versionadas con las reglas del juego. En la v1 todas son gratis e ilimitadas.
_Evitar_: tienda, inventario

**Comida** (`food`):
Un objeto del catálogo que se da en la cocina y sube el hambre.

**Actividad** (`activity`):
Un objeto del catálogo con el que se juega en el salón y sube la diversión.
_Evitar_: juego (es el juego entero)

**Afinidad** (`affinity`):
Cuánto le gusta a una mascota una comida o una actividad, de −2 a 2. La pone la persona a la que representa; lo que no ha puntuado vale 0. Cuanto más le gusta, más sube la necesidad, y lo que le encanta también le da cariño.
_Evitar_: preferencia, valoración

**Tus gustos** (`tastes`):
La pantalla donde cada persona puntúa, con cinco caras, la afinidad de la mascota que la representa con cada objeto del catálogo. Se abre desde la cabecera y solo enseña los gustos propios: los de la mascota que cuidas se descubren cuidándola.

**Gusto descubierto** (`discovered`):
Una comida o una actividad que el cuidador ya ha dado a su mascota, con la reacción que vio entonces. El cuidador no ve la afinidad: la descubre cuidando.

**Asco** (`disgust`):
Lo que hace la mascota con una comida o una actividad que odia (afinidad −2): la acepta, le sube poco la necesidad y lo muestra con una reacción cómica. No es un rechazo: el motor sí aplica la acción.
_Evitar_: rechazo cómico

**Petición** (`asks`):
Cuando una necesidad baja de 30, la mascota la pide en Casa. Ocurre dentro de la app; no es un aviso.

**Evento** (`PetEvent`):
El registro inmutable de algo que ocurrió a una mascota, del que salen el diario, las rachas y el álbum.

**Nacimiento** (`birth`):
El momento en que nacen las dos mascotas de una pareja: cuando se registra su segunda persona. Nacen despiertas, con las cinco necesidades a 80, y es el primer evento de cada una.

## Conversación y memoria

**Conversación** (`Conversation`):
Una sesión de chat de una persona con una mascota.
_Evitar_: hilo, sesión

**Turno** (`Turn`):
Una respuesta de la mascota en el chat: emoción, animación, texto y acciones propuestas.
_Evitar_: mensaje de la IA

**Acción propuesta** (`proposed_actions`):
Una acción que la mascota sugiere en su turno y que el motor puede aplicar o rechazar.

**Memoria** (`Memory`):
Una frase atómica que la mascota recuerda de lo que le contaron, con quién la contó y quién puede verla.
_Evitar_: recuerdo (reservado al álbum), contexto

**Visibilidad** (`visibility`):
Quién puede ver una memoria: solo quien la contó (`speaker`) o los dos (`couple`).

**Modo espejo** (`mirror`):
Chatear con tu propia mascota para comprobar que suena a ti. No escribe memorias ni cambia el juego.

**Diario** (`DiaryEntry`):
El resumen corto del día de una mascota, sin lo privado de quien lo contó.

## Vínculo de pareja

**Recado** (`Errand`):
Un mensaje que una persona pide a su mascota que lleve a la de su pareja, entregado con la voz de la mascota.
_Evitar_: mensaje, nota

**Regalo**:
Un objeto de la tienda que una persona envía a la mascota de su pareja.

**Racha** (`streak`):
Días seguidos en que los dos han cuidado a su mascota.

**Monedas** (`coins`):
La moneda del juego, que se gana cuidando, jugando y con misiones.

**Aviso** (`notification`):
Una notificación push programada, por ejemplo cuando una necesidad cruza un umbral.

**Álbum** (`album`):
Momentos destacados guardados: frases graciosas, primeros regalos.
