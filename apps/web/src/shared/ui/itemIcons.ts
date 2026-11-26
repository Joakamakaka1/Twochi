import type { ItemKey } from "../api";

// The icon of each item of the catalogue, in one map: emoji today, and the seam where
// SVG or PNG art replaces them. A key the API adds breaks the build until it has one.
export const ITEM_ICONS: Readonly<Record<ItemKey, string>> = {
  tortilla: "🍳",
  paella: "🥘",
  pizza: "🍕",
  burger: "🍔",
  sushi: "🍣",
  pasta: "🍝",
  tacos: "🌮",
  salad: "🥗",
  broccoli: "🥦",
  strawberries: "🍓",
  ice_cream: "🍨",
  chocolate: "🍫",
  ball: "⚽",
  video_games: "🎮",
  dance: "💃",
  reading: "📚",
  drawing: "🎨",
  puzzle: "🧩",
};
