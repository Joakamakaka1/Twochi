import { ITEM_ICONS, texts } from "../../shared";
import type { ActivityKey, CareAction, FoodKey, ItemKey } from "../../shared";

/** The care actions that open a tray to choose what to give. */
export type TrayAction = Extract<CareAction, "feed" | "play">;

export function opensTray(action: CareAction): action is TrayAction {
  return action === "feed" || action === "play";
}

/** One item of a tray, as the carer sees it. */
export interface TrayItem {
  key: ItemKey;
  icon: string;
  name: string;
}

// What each tray offers, in order. Typed by the contract's kinds, so a food in the
// activities' tray, or one the engine moved to the other kind, breaks the build.
const TRAYS: { feed: readonly FoodKey[]; play: readonly ActivityKey[] } = {
  feed: [
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
  ],
  play: ["ball", "video_games", "dance", "reading", "drawing", "puzzle"],
};

/** The tray of a care action: the foods when feeding, the activities when playing. */
export function trayFor(action: TrayAction): TrayItem[] {
  const keys: readonly ItemKey[] = TRAYS[action];
  return keys.map((key) => ({ key, icon: ITEM_ICONS[key], name: texts.care.items[key] }));
}
