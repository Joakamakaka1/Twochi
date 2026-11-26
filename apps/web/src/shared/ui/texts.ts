// Every text the interface shows, in one place: changing or translating them is
// editing this file.

export const texts = {
  appName: "Twochi",
  loading: "Cargando…",
  failure: "Algo ha fallado. Inténtalo de nuevo.",
  retry: "Reintentar",
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
