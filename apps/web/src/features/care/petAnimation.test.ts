import { describe, expect, it } from "vitest";

import type { CareAction, Mood, Rejection } from "../../shared";
import {
  changeRest,
  openStage,
  react,
  reactionAnimation,
  REACTION_MS,
  restAnimation,
  tick,
} from "./petAnimation";

const MOODS: readonly Mood[] = ["happy", "normal", "sad", "sick"];

describe("restAnimation", () => {
  it.each([
    ["happy", "happy"],
    ["normal", "idle"],
    ["sad", "sad"],
    ["sick", "sad"],
  ] as const)("rests as %s → %s while awake", (mood, animation) => {
    expect(restAnimation({ mood, asleep: false })).toBe(animation);
  });

  it.each(MOODS)("sleeps whatever its mood (%s) while asleep", (mood) => {
    expect(restAnimation({ mood, asleep: true })).toBe("sleep");
  });
});

describe("reactionAnimation", () => {
  it.each([
    ["feed", "eat"],
    ["play", "happy"],
    ["pet", "happy"],
    ["bathe", "surprised"],
    ["sleep", "sleep"],
    ["wake", "surprised"],
  ] as const)("reacts to %s applied with %s", (action, animation) => {
    expect(reactionAnimation(action, { applied: true, rejection: null })).toBe(animation);
  });

  it.each([
    ["not_caretaker", "angry"],
    ["asleep", "angry"],
    ["already_asleep", "angry"],
    ["already_awake", "angry"],
    ["too_tired", "sad"],
  ] as const)("reacts to a refusal for %s with %s", (rejection: Rejection, animation) => {
    const actions: readonly CareAction[] = ["feed", "play", "pet", "bathe", "sleep", "wake"];
    for (const action of actions) {
      expect(reactionAnimation(action, { applied: false, rejection })).toBe(animation);
    }
  });
});

describe("the pet's stage", () => {
  const T0 = 1_000_000;

  it("opens playing the rest", () => {
    expect(openStage("happy")).toEqual({
      stage: { rest: "happy", playing: "happy", reactingUntil: null },
      play: "happy",
    });
  });

  it("plays the new rest when the pet's mood or sleep changes, and nothing when it stays", () => {
    const { stage } = openStage("idle");

    const sad = changeRest(stage, "sad");
    expect(sad.play).toBe("sad");
    expect(changeRest(sad.stage, "sad").play).toBeNull();
  });

  it("plays every reaction, also the same one twice in a row or the one it rests as", () => {
    const first = react(openStage("happy").stage, "happy", T0);
    expect(first.play).toBe("happy");

    const second = react(first.stage, "happy", T0 + 100);
    expect(second.play).toBe("happy");
  });

  it("goes back to rest once the reaction is over, not before", () => {
    const reacting = react(openStage("idle").stage, "eat", T0).stage;

    expect(reacting.reactingUntil).toBe(T0 + REACTION_MS);
    expect(tick(reacting, T0 + REACTION_MS - 1).play).toBeNull();
    const after = tick(reacting, T0 + REACTION_MS);
    expect(after.play).toBe("idle");
    expect(after.stage.reactingUntil).toBeNull();
    expect(tick(after.stage, T0 + REACTION_MS * 2).play).toBeNull();
  });

  it("finishes the reaction when the rest changes meanwhile, then goes to the new rest", () => {
    const reacting = react(openStage("idle").stage, "eat", T0).stage;

    const changed = changeRest(reacting, "happy");
    expect(changed.play).toBeNull();
    expect(tick(changed.stage, T0 + REACTION_MS).play).toBe("happy");
  });

  it("does not start the clip again when the reaction is already the new rest", () => {
    const fallingAsleep = react(openStage("idle").stage, "sleep", T0).stage;
    const asleep = changeRest(fallingAsleep, "sleep").stage;

    const after = tick(asleep, T0 + REACTION_MS);
    expect(after.play).toBeNull();
    expect(after.stage).toEqual({ rest: "sleep", playing: "sleep", reactingUntil: null });
  });

  it("reacts for the whole time again after a second reaction", () => {
    const first = react(openStage("idle").stage, "eat", T0).stage;
    const second = react(first, "happy", T0 + 1000).stage;

    expect(tick(second, T0 + REACTION_MS).play).toBeNull();
    expect(tick(second, T0 + 1000 + REACTION_MS).play).toBe("idle");
  });
});
