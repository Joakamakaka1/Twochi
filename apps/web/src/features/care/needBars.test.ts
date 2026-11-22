import { describe, expect, it } from "vitest";

import type { Pet } from "../../shared";
import { needBars } from "./needBars";

const READ_AT = "2026-11-22T12:00:00Z";

function petWith(values: Record<keyof Pet["needs"], [number, number]>): Pet {
  const need = ([value, ratePerHour]: [number, number]) => ({
    value,
    updated_at: READ_AT,
    rate_per_hour: ratePerHour,
  });
  return {
    id: "00000000-0000-4000-8000-0000000fb20b",
    name: "Bru",
    model_key: "placeholder",
    asleep: false,
    mood: "normal",
    needs: {
      hunger: need(values.hunger),
      energy: need(values.energy),
      hygiene: need(values.hygiene),
      fun: need(values.fun),
      affection: need(values.affection),
    },
  };
}

const at = (iso: string) => new Date(iso);

describe("needBars", () => {
  it("shows the five needs in order, each at its value now", () => {
    const pet = petWith({ hunger: [80, -4], energy: [70, -3], hygiene: [60, -2], fun: [50, -6], affection: [40, -1] });

    const bars = needBars(pet, at("2026-11-22T14:00:00Z"));

    expect(bars.map((bar) => [bar.need, bar.value])).toEqual([
      ["hunger", 72],
      ["energy", 64],
      ["hygiene", 56],
      ["fun", 38],
      ["affection", 38],
    ]);
  });

  it("marks «la pide» on the needs under 30, and not at 30", () => {
    const pet = petWith({ hunger: [29.9, 0], energy: [30, 0], hygiene: [0, 0], fun: [31, 0], affection: [100, 0] });

    const asking = needBars(pet, at(READ_AT)).filter((bar) => bar.asks);

    expect(asking.map((bar) => bar.need)).toEqual(["hunger", "hygiene"]);
  });

  it("starts asking when the need drops under 30 while the screen is open", () => {
    const pet = petWith({ hunger: [34, -4], energy: [80, 0], hygiene: [80, 0], fun: [80, 0], affection: [80, 0] });
    const hunger = (iso: string) => needBars(pet, at(iso))[0];

    expect(hunger("2026-11-22T12:59:00Z")?.asks).toBe(false);
    expect(hunger("2026-11-22T13:01:00Z")?.asks).toBe(true);
  });

  it("does not go up when the device clock is behind the server", () => {
    const pet = petWith({ hunger: [25, -4], energy: [80, -3], hygiene: [80, -2], fun: [80, -5], affection: [80, -3] });

    const bars = needBars(pet, at("2026-11-22T10:00:00Z"));

    expect(bars.map((bar) => bar.value)).toEqual([25, 80, 80, 80, 80]);
    expect(bars[0]?.asks).toBe(true);
  });
});
