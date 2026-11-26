import { describe, expect, it } from "vitest";

import { ITEM_ICONS } from "../../shared";
import type { ItemKey } from "../../shared";
import { trayFor } from "./tray";
import type { TrayItem } from "./tray";

describe("trayFor", () => {
  it("offers the twelve foods of the catalogue when feeding", () => {
    expect(trayFor("feed", {}).map((item) => item.key)).toEqual([
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
    expect(trayFor("play", {}).map((item) => item.key)).toEqual([
      "ball",
      "video_games",
      "dance",
      "reading",
      "drawing",
      "puzzle",
    ]);
  });

  it("shows each item with its icon and its name", () => {
    expect(trayFor("feed", {})).toContainEqual({
      key: "strawberries",
      icon: "🍓",
      name: "Fresas",
      label: "Fresas",
      seen: null,
    });
    expect(trayFor("play", {})).toContainEqual({ key: "puzzle", icon: "🧩", name: "Puzle", label: "Puzle", seen: null });
  });

  it("puts every item of the catalogue in exactly one tray", () => {
    const offered = [...trayFor("feed", {}), ...trayFor("play", {})].map((item) => item.key);

    expect([...offered].sort()).toEqual(Object.keys(ITEM_ICONS).sort());
    expect(new Set(offered).size).toBe(offered.length);
  });
});

describe("trayFor with the tastes discovered", () => {
  const item = (tray: TrayItem[], key: ItemKey) => tray.find((each) => each.key === key);

  it("shows no face on an item never given", () => {
    expect(trayFor("feed", {}).filter((each) => each.seen !== null)).toEqual([]);
  });

  it("shows on each item given the face of the last reaction seen", () => {
    const tray = trayFor("feed", { pizza: 2, broccoli: -2, salad: 0 });

    expect(item(tray, "pizza")?.seen).toEqual({ face: "😍", text: "le encanta" });
    expect(item(tray, "broccoli")?.seen).toEqual({ face: "😖", text: "le da asco" });
    expect(item(tray, "salad")?.seen).toEqual({ face: "😐", text: "le da igual" });
    expect(item(tray, "sushi")?.seen).toBeNull();
  });

  it("has a face for each step of the scale", () => {
    const tray = trayFor("play", { ball: 1, dance: -1 });

    expect(item(tray, "ball")?.seen).toEqual({ face: "🙂", text: "le gusta" });
    expect(item(tray, "dance")?.seen).toEqual({ face: "🙁", text: "no le gusta" });
  });

  it("puts in each tray only what was discovered of its own kind", () => {
    const tray = trayFor("play", { pizza: 2, puzzle: -2 });

    expect(tray.filter((each) => each.seen !== null).map((each) => each.key)).toEqual(["puzzle"]);
  });

  it("names each item with the reaction seen, for screen readers", () => {
    const tray = trayFor("feed", { pizza: 2 });

    expect(item(tray, "pizza")?.label).toBe("Pizza, le encanta");
    expect(item(tray, "sushi")?.label).toBe("Sushi");
  });
});
