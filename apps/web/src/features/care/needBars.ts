import { needValueAt } from "../../shared";
import type { Need, Pet } from "../../shared";

export interface NeedBar {
  need: Need;
  value: number;
  // «la pide»: the pet asks for this need.
  asks: boolean;
}

// The threshold comes from the ticket (TWO-34): the API gives no such value, and this is
// a hint on screen, not an engine rule.
const ASKS_BELOW = 30;

const NEEDS: readonly Need[] = ["hunger", "energy", "hygiene", "fun", "affection"];

/** The five needs as Casa shows them at `now`, interpolated from the last API read. */
export function needBars(pet: Pet, now: Date): NeedBar[] {
  return NEEDS.map((need) => {
    const value = needValueAt(pet.needs[need], now);
    return { need, value, asks: value < ASKS_BELOW };
  });
}

/**
 * The need Casa highlights: the one the pet asks for most, the lowest under 30, or none.
 * A tie goes to the need shown first.
 */
export function mostUrgent(bars: readonly NeedBar[]): Need | null {
  let urgent: NeedBar | null = null;
  for (const bar of bars) {
    if (bar.asks && (urgent === null || bar.value < urgent.value)) urgent = bar;
  }
  return urgent?.need ?? null;
}

/** The need the pet lacks most, under 30 or not. A tie goes to the need shown first. */
export function lowestNeed(bars: readonly NeedBar[]): Need {
  let lowest: NeedBar | null = null;
  for (const bar of bars) {
    if (lowest === null || bar.value < lowest.value) lowest = bar;
  }
  return lowest?.need ?? "hunger";
}
