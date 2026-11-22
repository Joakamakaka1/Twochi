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
