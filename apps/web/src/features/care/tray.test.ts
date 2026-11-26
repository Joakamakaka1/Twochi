import { describe, expect, it } from "vitest";

import { ITEM_ICONS } from "../../shared";
import { trayFor } from "./tray";

describe("trayFor", () => {
  it("offers the twelve foods of the catalogue when feeding", () => {
    expect(trayFor("feed").map((item) => item.key)).toEqual([
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
    ]);
  });

  it("offers the six activities of the catalogue when playing", () => {
    expect(trayFor("play").map((item) => item.key)).toEqual([
      "ball",
      "video_games",
      "dance",
      "reading",
      "drawing",
      "puzzle",
    ]);
  });

  it("shows each item with its icon and its name", () => {
    expect(trayFor("feed")).toContainEqual({ key: "strawberries", icon: "🍓", name: "Fresas" });
    expect(trayFor("play")).toContainEqual({ key: "puzzle", icon: "🧩", name: "Puzle" });
  });

  it("puts every item of the catalogue in exactly one tray", () => {
    const offered = [...trayFor("feed"), ...trayFor("play")].map((item) => item.key);

    expect([...offered].sort()).toEqual(Object.keys(ITEM_ICONS).sort());
    expect(new Set(offered).size).toBe(offered.length);
  });
});
