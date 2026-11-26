import type { ActivityKey, FoodKey } from "../api";

// The catalogue by kind, in the order screens list it (GLOSSARY.md, «Catálogo»). Typed
// by the contract's kinds, so an item the engine moves to the other kind breaks the
// build; a test checks every item of ITEM_ICONS appears once.
export const FOODS: readonly FoodKey[] = [
  "tortilla",
  "paella",
  "pizza",
  "burger",
  "sushi",
  "pasta",
  "tacos",
  "salad",
  "broccoli",
  "strawberries",
  "ice_cream",
  "chocolate",
];

export const ACTIVITIES: readonly ActivityKey[] = ["ball", "video_games", "dance", "reading", "drawing", "puzzle"];
