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
