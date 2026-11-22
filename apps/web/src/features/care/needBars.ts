import { needValueAt } from "../../shared";
import type { Need, Pet } from "../../shared";

export interface NeedBar {
  need: Need;
  value: number;
  asks: boolean;
}

const NEEDS: readonly Need[] = ["hunger", "energy", "hygiene", "fun", "affection"];

export function needBars(pet: Pet, now: Date): NeedBar[] {
  return NEEDS.map((need) => ({ need, value: needValueAt(pet.needs[need], now), asks: false }));
}
