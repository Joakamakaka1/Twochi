import { describe, expect, it } from "vitest";

import { ROOMS } from "./rooms";

describe("ROOMS", () => {
  it("are Cocina, Baño, Dormitorio and Salón, each with its own care", () => {
    expect(ROOMS.map(({ room, actions }) => [room, actions.filter((action) => action !== "pet")])).toEqual([
      ["kitchen", ["feed"]],
      ["bathroom", ["bathe"]],
      ["bedroom", ["sleep", "wake"]],
      ["living_room", ["play"]],
    ]);
  });

  it("let the carer pet the pet in every room", () => {
    for (const { actions } of ROOMS) expect(actions).toContain("pet");
  });
});
