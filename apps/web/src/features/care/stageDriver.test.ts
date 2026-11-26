import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Animation } from "../../scene";
import type { CareActionResult, Pet } from "../../shared";
import { REACTION_MS } from "./petAnimation";
import { createStageDriver } from "./stageDriver";

const PET = {} as Pet;
const applied: CareActionResult = {
  applied: true,
  rejection: null,
  deltas: {},
  reaction: null,
  sickness: null,
  pet: PET,
};

// The scene as the driver sees it: what it was asked to play, in order.
function fakeScene() {
  const played: Animation[] = [];
  return {
    played,
    play: (animation: Animation) => {
      played.push(animation);
    },
  };
}

describe("the stage driver", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("plays the rest, each reaction, and the rest again once the reaction is over", () => {
    const scene = fakeScene();
    const driver = createStageDriver();
    driver.attach(scene);

    driver.rest("idle");
    driver.react("feed", applied);
    expect(scene.played).toEqual(["idle", "eat"]);

    vi.advanceTimersByTime(REACTION_MS - 1);
    expect(scene.played).toEqual(["idle", "eat"]);
    vi.advanceTimersByTime(1);
    expect(scene.played).toEqual(["idle", "eat", "idle"]);
  });

  it("giggles at each tickle, and goes back to rest once the last one is over", () => {
    const scene = fakeScene();
    const driver = createStageDriver();
    driver.attach(scene);
    driver.rest("sad");

    driver.tickle();
    vi.advanceTimersByTime(REACTION_MS - 1);
    driver.tickle();
    vi.advanceTimersByTime(REACTION_MS - 1);
    expect(scene.played).toEqual(["sad", "happy", "happy"]);
    vi.advanceTimersByTime(1);
    expect(scene.played).toEqual(["sad", "happy", "happy", "sad"]);
  });

  it("does not cut a giggle with the answer to a petting, and reacts to it once the giggle is over", () => {
    const scene = fakeScene();
    const driver = createStageDriver();
    driver.attach(scene);
    driver.rest("idle");

    driver.tickle();
    vi.advanceTimersByTime(500);
    driver.react("pet", applied);
    expect(scene.played).toEqual(["idle", "happy"]);
    vi.advanceTimersByTime(REACTION_MS - 500);
    expect(scene.played).toEqual(["idle", "happy", "idle"]);

    driver.react("pet", applied);
    expect(scene.played).toEqual(["idle", "happy", "idle", "happy"]);
  });

  it("shows a refusal at once, even during a giggle", () => {
    const scene = fakeScene();
    const driver = createStageDriver();
    driver.attach(scene);
    driver.rest("idle");

    driver.tickle();
    driver.react("pet", { ...applied, applied: false, rejection: "not_caretaker" });

    expect(scene.played).toEqual(["idle", "happy", "angry"]);
  });

  it("does not go back to rest once stopped", () => {
    const scene = fakeScene();
    const driver = createStageDriver();
    driver.attach(scene);
    driver.rest("idle");
    driver.react("feed", applied);

    driver.stop();
    vi.advanceTimersByTime(REACTION_MS * 2);

    expect(scene.played).toEqual(["idle", "eat"]);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("plays what is on stage when the scene arrives after the rest, as a lazy scene does", () => {
    const scene = fakeScene();
    const driver = createStageDriver();
    driver.rest("sleep");

    driver.attach(scene);

    expect(scene.played).toEqual(["sleep"]);
  });

  it("ignores a reaction before the pet's rest is known, and a scene that went away", () => {
    const scene = fakeScene();
    const driver = createStageDriver();
    driver.attach(scene);
    driver.react("feed", applied);
    expect(scene.played).toEqual([]);

    driver.rest("idle");
    driver.attach(null);
    driver.react("feed", applied);
    vi.advanceTimersByTime(REACTION_MS);
    expect(scene.played).toEqual(["idle"]);
  });
});
