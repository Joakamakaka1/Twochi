// Every text the interface shows, in one place: changing or translating them is
// editing this file.

export const texts = {
  appName: "Twochi",
  loading: "Cargando…",
  failure: "Algo ha fallado. Inténtalo de nuevo.",
  retry: "Reintentar",
  // «Tus gustos»: each person rates the pet that represents them (GLOSSARY.md, «Afinidad»).
  tastes: {
    open: "Tus gustos",
    backHome: "Volver a Casa",
    title: "Tus gustos",
    intro: "Tu mascota es como tú. Dile qué te gusta: tu pareja lo descubrirá cuidándola.",
    kinds: { food: "Comidas", activity: "Actividades" },
    faces: { "-2": "Lo odio", "-1": "No me gusta", "0": "Me da igual", "1": "Me gusta", "2": "Me encanta" },
  },
  auth: {
    signInWithGoogle: "Entrar con Google",
    enrollTitle: "Protege tu cuenta",
    enrollSteps:
      "Escanea este código QR con tu aplicación de autenticación y escribe el código de 6 cifras que te muestre.",
    enrollQrAlt: "Código QR para tu aplicación de autenticación",
    enrollSecret: "Si no puedes escanearlo, escribe esta clave en la aplicación:",
    verifyTitle: "Verifica que eres tú",
    verifySteps: "Escribe el código de 6 cifras de tu aplicación de autenticación.",
    code: "Código de 6 cifras",
    submitCode: "Verificar",
    codeProblems: {
      malformed: "El código tiene 6 cifras.",
      wrong_code: "Ese código no es correcto. Mira el que muestra ahora tu aplicación y vuelve a intentarlo.",
    },
    signOut: "Cerrar sesión",
  },
  care: {
    caringFor: (petName: string) => `Cuidas a ${petName}`,
    petArrivesWithPartner: "Tu mascota llegará cuando tu pareja se una.",
    moods: { happy: "Feliz", normal: "Normal", sad: "Triste", sick: "Enferma" },
    moodIs: (mood: string) => `Ánimo: ${mood}`,
    // The 3D figure, for screen readers; petting it has its own button.
    petFigure: (petName: string) => `${petName} en su casa`,
    asleep: "Está dormida",
    awake: "Está despierta",
    needsTitle: "Necesidades",
    needs: { hunger: "Hambre", energy: "Energía", hygiene: "Higiene", fun: "Diversión", affection: "Cariño" },
    // Next to a need under 30: the pet asks for it.
    asksFor: "la pide",
    roomsTitle: "Habitaciones",
    rooms: { kitchen: "Cocina", bathroom: "Baño", bedroom: "Dormitorio", living_room: "Salón" },
    actions: {
      feed: "Dar de comer",
      play: "Jugar",
      pet: "Acariciar",
      bathe: "Bañar",
      sleep: "Dormir",
      wake: "Despertar",
    },
    // The catalogue (GLOSSARY.md, «Catálogo»): the foods and the activities.
    items: {
      tortilla: "Tortilla",
      paella: "Paella",
      pizza: "Pizza",
      burger: "Hamburguesa",
      sushi: "Sushi",
      pasta: "Pasta",
      tacos: "Tacos",
      salad: "Ensalada",
      broccoli: "Brócoli",
      strawberries: "Fresas",
      ice_cream: "Helado",
      chocolate: "Chocolate",
      ball: "Pelota",
      video_games: "Videojuegos",
      dance: "Bailar",
      reading: "Leer",
      drawing: "Dibujar",
      puzzle: "Puzle",
    },
    trays: { feed: "¿Qué le das de comer?", play: "¿A qué jugáis?" },
    closeTray: "Cerrar",
    // How the pet took what it was given, by its affinity (GLOSSARY.md, «Afinidad»).
    reactions: {
      "2": "¡le encanta!",
      "1": "le gusta.",
      "0": "ni fu ni fa.",
      "-1": "no le gusta mucho.",
      "-2": "¡puaj, qué asco! Pero se lo toma.",
    },
    reactionTo: (item: string, reaction: string) => `${item}: ${reaction}`,
    // Why the engine refused a care action (GLOSSARY.md, «Rechazo»).
    rejections: {
      not_caretaker: "Esta mascota la cuida tu pareja.",
      asleep: "Está dormida. Despiértala antes.",
      already_asleep: "Ya está dormida.",
      already_awake: "Ya está despierta.",
      too_tired: "Está demasiado cansada para jugar.",
    },
  },
} as const;

// The development login. Its own export, so a production build drops it whole.
export const devTexts = {
  title: "Entrar con correo (solo en desarrollo)",
  email: "Correo",
  password: "Contraseña",
  submit: "Entrar con correo",
  wrongCredentials: "Correo o contraseña incorrectos.",
} as const;
