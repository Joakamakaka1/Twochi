import type { CareAction, Need } from "../../shared";
import type { Room } from "./rooms";

// Casa's icons, next to the texts they go with: emoji today, and the seam where SVG art
// replaces them. They are decoration: every one sits beside its name.

export const NEED_ICONS: Readonly<Record<Need, string>> = {
  hunger: "🍗",
  energy: "⚡",
  hygiene: "🧼",
  fun: "🎈",
  affection: "💗",
};

export const ROOM_ICONS: Readonly<Record<Room, string>> = {
  kitchen: "🍽️",
  bathroom: "🛁",
  bedroom: "🛏️",
  living_room: "🛋️",
};

export const ACTION_ICONS: Readonly<Record<CareAction, string>> = {
  feed: "🥄",
  play: "🎲",
  pet: "✋",
  bathe: "🧽",
  sleep: "🌙",
  wake: "☀️",
};
