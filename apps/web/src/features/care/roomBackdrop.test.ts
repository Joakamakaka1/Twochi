import { describe, expect, it } from "vitest";

import { roomBackdrop } from "./roomBackdrop";
import { ROOMS } from "./rooms";

const AWAKE = { asleep: false };
const ASLEEP = { asleep: true };

describe("roomBackdrop", () => {
  it("gives each of the four rooms a backdrop of its own", () => {
    const backdrops = ROOMS.map(({ room }) => roomBackdrop(room, AWAKE));

    expect(new Set(backdrops).size).toBe(4);
    for (const backdrop of backdrops) expect(backdrop).toMatch(/\.(svg|png|webp)$/);
  });

  it("turns the bedroom's light off while the pet sleeps", () => {
    expect(roomBackdrop("bedroom", ASLEEP)).not.toBe(roomBackdrop("bedroom", AWAKE));
    expect(roomBackdrop("bedroom", ASLEEP)).toMatch(/\.(svg|png|webp)$/);
  });

  it("leaves the other rooms as they are while the pet sleeps", () => {
    for (const room of ["kitchen", "bathroom", "living_room"] as const) {
      expect(roomBackdrop(room, ASLEEP)).toBe(roomBackdrop(room, AWAKE));
    }
  });

  it("serves every backdrop from the app, not from another host", () => {
    for (const { room } of ROOMS) {
      for (const pet of [AWAKE, ASLEEP]) expect(roomBackdrop(room, pet)).not.toMatch(/^(?:[a-z]+:)?\/\//i);
    }
  });
});
