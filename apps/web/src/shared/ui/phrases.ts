// What the pet says in its bubble (GLOSSARY.md, «Bocadillo»): generic phrases, several
// per situation, in the pet's own voice. Next to the texts, so changing or translating
// them is editing this file. Never an adjective with gender: the pet is whoever it
// caricatures.

type Phrases = readonly [string, string, ...string[]];
// A phrase about the food or activity it was given, with its name.
type ItemPhrases = readonly [(item: string) => string, (item: string) => string, ...((item: string) => string)[]];

export const phrases = {
  // After the action that healed it: a celebration.
  healed: [
    "¡Me encuentro genial otra vez!",
    "¡Ya estoy bien! ¡Gracias por cuidarme!",
    "¡Adiós, catarro! ¡Qué bien me siento!",
  ],
  // After the action that left it sick.
  fellSick: ["Uy… no me encuentro nada bien.", "Me duele todo…", "Ay… me siento fatal…"],
  // How it took a food or an activity, by its affinity (GLOSSARY.md, «Afinidad»).
  reactions: {
    food: {
      2: [
        (item) => `¡${item}! ¡Es mi comida favorita!`,
        (item) => `¡Ñam, ñam! ${item}, ¡me encanta!`,
        (item) => `¡${item}! ¡Qué rico, qué rico!`,
      ],
      1: [(item) => `${item}… ¡qué rico!`, () => "¡Ñam! Esto me gusta.", (item) => `${item}, ¡muy bien!`],
      0: [(item) => `${item}… bueno, vale.`, () => "Ni fu ni fa.", () => "Pues… se deja comer."],
      [-1]: [
        (item) => `${item}… no es lo mío.`,
        () => "Mmm… no mucho, la verdad.",
        () => "Me lo como, pero no me encanta.",
      ],
      [-2]: [
        (item) => `¡Puaj! ¿${item}? ¡Qué asco!`,
        () => "¡Bleh! Me lo como, pero ¡qué asco!",
        (item) => `¡Agh! ${item}… ¡nunca más!`,
      ],
    } satisfies Record<number, ItemPhrases>,
    activity: {
      2: [
        (item) => `¡${item}! ¡Es lo que más me gusta!`,
        () => "¡Sí, sí, sí! ¡Otra vez!",
        (item) => `¡${item}! ¡Me encanta!`,
      ],
      1: [(item) => `¡${item}! ¡Qué bien!`, () => "¡Me lo paso bien!", () => "¡Esto mola!"],
      0: [(item) => `${item}… vale, está bien.`, () => "Bueno, no está mal.", () => "Ni fu ni fa."],
      [-1]: [
        (item) => `${item}… no es lo mío.`,
        () => "Mmm… ¿podemos hacer otra cosa?",
        () => "Bueno… si insistes.",
      ],
      [-2]: [
        (item) => `¿${item}? ¡Puaj, qué rollo!`,
        () => "¡Bleh! Lo hago, pero ¡qué asco!",
        (item) => `¡Agh! ${item}… ¡nunca más!`,
      ],
    } satisfies Record<number, ItemPhrases>,
  },
  // Why it did not do it, said with charm (GLOSSARY.md, «Rechazo»).
  rejections: {
    not_caretaker: ["Tú no me cuidas: me cuida tu pareja.", "¡Eh! Que tú no eres quien me cuida."],
    asleep: ["Zzz… déjame dormir… despiértame antes.", "Mmm… cinco minutitos más…", "Zzz… estoy durmiendo…"],
    already_asleep: ["Zzz… si ya estoy durmiendo…", "Ya duermo, ya… zzz."],
    already_awake: ["¡Pero si ya tengo los ojos abiertos!", "¡Ya estoy en pie, de verdad!"],
    too_tired: ["No tengo fuerzas para jugar…", "Uf… estoy sin energía para jugar.", "Necesito dormir antes de jugar…"],
  } satisfies Record<string, Phrases>,
  // Touched or petted while asleep: it grumbles and goes on sleeping.
  grumble: ["Mmm… ¿quién me toca? Zzz…", "Grrr… déjame dormir… zzz.", "Zzz… ahora no… zzz."],
  // Many touches in a row (GLOSSARY.md, «Cosquillas»).
  tickles: ["¡Jajaja! ¡Cosquillas no!", "¡Ji, ji, ji! ¡Para, para!", "¡Jajaja! ¡Que me haces cosquillas!"],
  // A petting that raised no affection: enough for now.
  enough: ["Ya vale, ¡que me despeinas!", "Vale, vale, ya está bien de mimos.", "¡Ya vale! Luego más."],
  // After an action applied without an item.
  applied: {
    feed: ["¡Ñam!", "¡Qué rico!"],
    play: ["¡Qué divertido!", "¡Otra vez!"],
    pet: ["¡Mmm, qué gustito!", "¡Más mimos!", "¡Me encantan las caricias!"],
    bathe: ["¡Qué fresquito! Huelo de maravilla.", "¡Burbujas, burbujas!", "¡Qué gusto, un baño!"],
    sleep: ["Buenas noches… zzz.", "A dormir… hasta luego.", "Qué sueño… zzz."],
    wake: ["¡Buenos días!", "¡Uaaah! ¿Ya es de día?", "¡Ya estoy en pie!"],
  } satisfies Record<string, Phrases>,
  // Asleep, whatever else it lacks.
  asleep: ["Zzz…", "Zzz… mmm… zzz…", "Zzz… qué sueño más bonito…"],
  // Sick: a hint of what it lacks most.
  sick: {
    hunger: ["No me encuentro bien… creo que necesito comer.", "Me siento fatal… y tengo mucha hambre."],
    energy: ["No me encuentro bien… necesito dormir.", "Me siento fatal… estoy sin fuerzas."],
    hygiene: ["No me encuentro bien… necesito un baño.", "Me siento fatal… y huelo raro."],
    fun: ["No me encuentro bien… me aburro muchísimo.", "Me siento fatal… ¿jugamos a algo?"],
    affection: ["No me encuentro bien… necesito mimos.", "Me siento fatal… ¿me das un abrazo?"],
  } satisfies Record<string, Phrases>,
  // A need under 30: what it asks for (GLOSSARY.md, «Petición»).
  asks: {
    hunger: ["¡Tengo hambre!", "Mi tripa hace ruidos…", "¿Hay algo de comer?"],
    energy: ["Tengo sueño…", "Uaaah… necesito dormir.", "Se me cierran los ojos…"],
    hygiene: ["Necesito un baño…", "¡Huelo un poco raro!", "¿Me bañas?"],
    fun: ["¡Me aburro!", "¿Jugamos a algo?", "Qué aburrimiento…"],
    affection: ["¿Me das un mimo?", "Necesito cariño…", "¿Me acaricias?"],
  } satisfies Record<string, Phrases>,
  // Nothing urgent: something of its mood.
  moods: {
    happy: ["¡Qué bien se está aquí!", "¡Hoy es un gran día!", "¡Te quiero mucho!"],
    normal: ["Aquí estoy.", "¿Qué hacemos?", "Hola, hola."],
    sad: ["Hoy no tengo un buen día…", "Me siento un poco de bajón…", "Estoy un poco triste…"],
  } satisfies Record<string, Phrases>,
} as const;
