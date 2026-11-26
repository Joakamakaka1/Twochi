import { ACTIVITIES, AFFINITY_FACES, FOODS, ITEM_ICONS, texts } from "../../shared";
import type { ActivityKey, Affinity, CareAction, FoodKey, ItemKey } from "../../shared";

/** The care actions that open a tray to choose what to give. */
export type TrayAction = Extract<CareAction, "feed" | "play">;

export function opensTray(action: CareAction): action is TrayAction {
  return action === "feed" || action === "play";
}

/** The tastes discovered: for each item given, the affinity seen the last time. */
export type Discovered = Readonly<Partial<Record<ItemKey, Affinity>>>;

/** The reaction seen the last time an item was given: its face and what it says. */
export interface SeenReaction {
  face: string;
  text: string;
}

/** One item of a tray, as the caretaker sees it. */
export interface TrayItem {
  key: ItemKey;
  icon: string;
  name: string;
  /** Its accessible name: the item's, with the reaction seen when there is one. */
  label: string;
  /** Null until the caretaker gives it for the first time. */
  seen: SeenReaction | null;
}

// What each tray offers, in the catalogue's order. Typed by the contract's kinds, so a
// food in the activities' tray, or one the engine moved to the other kind, breaks the build.
const TRAYS: { feed: readonly FoodKey[]; play: readonly ActivityKey[] } = { feed: FOODS, play: ACTIVITIES };

/**
 * The tray of a care action: the foods when feeding, the activities when playing. Each
 * item the caretaker already gave shows the face of the last reaction seen, never the pet's
 * taste as it is now (GLOSSARY.md, «Gusto descubierto»).
 */
export function trayFor(action: TrayAction, discovered: Discovered): TrayItem[] {
  const keys: readonly ItemKey[] = TRAYS[action];
  return keys.map((key) => {
    const icon = ITEM_ICONS[key];
    const name = texts.care.items[key];
    const affinity = discovered[key];
    if (affinity === undefined) return { key, icon, name, label: name, seen: null };
    const seen = { face: AFFINITY_FACES[affinity], text: texts.care.seen[affinity] };
    return { key, icon, name, label: texts.care.seenItem(name, seen.text), seen };
  });
}
