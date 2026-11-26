import { describe, expect, it } from "vitest";

import { phrases } from "../../shared";
import type { Affinity, CareAction, CareActionResult, ItemKey, Mood, Need, Pet, Rejection } from "../../shared";
import { BUBBLE_MS, bubbleKey, celebrating, chooseBubble, tickled } from "./bubble";
import type { BubbleState, LastOutcome } from "./bubble";
import { needBars } from "./needBars";

const NOW = Date.parse("2026-11-26T12:00:00Z");
const FIRST = () => 0;
const LAST = () => 0.999_999;

type NeedValues = Record<Need, number>;
const FULL: NeedValues = { hunger: 80, energy: 80, hygiene: 80, fun: 80, affection: 80 };

// The pet as Casa holds it, with its needs frozen at NOW.
function stateOf(pet: { mood?: Mood; asleep?: boolean; needs?: Partial<NeedValues> }): BubbleState & { pet: Pet } {
  const values = { ...FULL, ...pet.needs };
  const needs = Object.fromEntries(
    Object.entries(values).map(([need, value]) => [
      need,
      { value, updated_at: new Date(NOW).toISOString(), rate_per_hour: 0 },
    ]),
  ) as Pet["needs"];
  const full: Pet = {
    id: "00000000-0000-4000-8000-0000000fb20b",
    name: "Bru",
    model_key: "placeholder",
    asleep: pet.asleep ?? false,
    mood: pet.mood ?? "normal",
    needs,
  };
  return { pet: full, bars: needBars(full, new Date(NOW)), now: NOW };
}

function outcome(action: CareAction, result: Partial<CareActionResult>, at = NOW): LastOutcome {
  const applied: CareActionResult = {
    applied: true,
    rejection: null,
    deltas: {},
    reaction: null,
    sickness: null,
    pet: stateOf({}).pet,
  };
  return { action, result: { ...applied, ...result }, at };
}

const refused = (rejection: Rejection, asleep = false) =>
  outcome("feed", { applied: false, rejection, pet: { ...stateOf({}).pet, asleep } });
const took = (action: "feed" | "play", item_key: ItemKey, affinity: Affinity) =>
  outcome(action, { reaction: { item_key, affinity } });

describe("the bubble at rest", () => {
  it("says something of its mood when nothing is urgent", () => {
    expect(chooseBubble(stateOf({ mood: "happy" }), null, FIRST)).toBe(phrases.moods.happy[0]);
    expect(chooseBubble(stateOf({ mood: "normal" }), null, FIRST)).toBe(phrases.moods.normal[0]);
    expect(chooseBubble(stateOf({ mood: "sad", needs: { fun: 35 } }), null, FIRST)).toBe(phrases.moods.sad[0]);
  });

  it("asks for the most urgent need under 30, before its mood", () => {
    const state = stateOf({ mood: "sad", needs: { hunger: 25, energy: 15 } });

    expect(chooseBubble(state, null, FIRST)).toBe(phrases.asks.energy[0]);
  });

  it("asks for nothing at 30 or more", () => {
    expect(chooseBubble(stateOf({ needs: { hunger: 30 } }), null, FIRST)).toBe(phrases.moods.normal[0]);
  });

  it("hints at what it lacks most when sick, even when nothing is under 30", () => {
    const state = stateOf({ mood: "sick", needs: { hunger: 35, energy: 50, hygiene: 32, fun: 60, affection: 45 } });

    expect(chooseBubble(state, null, FIRST)).toBe(phrases.sick.hygiene[0]);
  });

  it("gives the sick hint before any request", () => {
    const state = stateOf({ mood: "sick", needs: { hunger: 20, fun: 10 } });

    expect(chooseBubble(state, null, FIRST)).toBe(phrases.sick.fun[0]);
  });

  it("only says sleepy things while asleep, sick or asking", () => {
    const state = stateOf({ mood: "sick", asleep: true, needs: { hunger: 5 } });

    expect(chooseBubble(state, null, FIRST)).toBe(phrases.asleep[0]);
    expect(chooseBubble(state, null, LAST)).toBe(phrases.asleep.at(-1));
  });
});

describe("the bubble after a care action", () => {
  it("says how the pet took each food, naming it", () => {
    const state = stateOf({});

    expect(chooseBubble(state, took("feed", "pizza", 2), FIRST)).toBe(phrases.reactions.food[2][0]("Pizza"));
    expect(chooseBubble(state, took("feed", "broccoli", -2), FIRST)).toBe(phrases.reactions.food[-2][0]("Brócoli"));
    expect(chooseBubble(state, took("feed", "pizza", 2), FIRST)).toContain("Pizza");
  });

  it("says how the pet took each activity, by its affinity", () => {
    const state = stateOf({});
    const affinities: readonly Affinity[] = [2, 1, 0, -1, -2];

    for (const affinity of affinities) {
      expect(chooseBubble(state, took("play", "dance", affinity), LAST)).toBe(
        phrases.reactions.activity[affinity].at(-1)?.("Bailar"),
      );
    }
  });

  it("has its own words for each refusal", () => {
    const rejections: readonly Rejection[] = ["not_caretaker", "asleep", "already_asleep", "already_awake", "too_tired"];

    for (const rejection of rejections) {
      expect(chooseBubble(stateOf({}), refused(rejection), FIRST)).toBe(phrases.rejections[rejection][0]);
    }
  });

  it("grumbles at a refusal even while asleep: the last outcome goes first", () => {
    const state = stateOf({ asleep: true });

    expect(chooseBubble(state, refused("asleep", true), FIRST)).toBe(phrases.rejections.asleep[0]);
  });

  it("grumbles when touched or petted asleep, with words of its own", () => {
    const touchedAsleep = outcome("pet", {
      applied: false,
      rejection: "asleep",
      pet: { ...stateOf({}).pet, asleep: true },
    });

    expect(chooseBubble(stateOf({ asleep: true }), touchedAsleep, FIRST)).toBe(phrases.grumble[0]);
    expect(chooseBubble(stateOf({ asleep: true }), touchedAsleep, LAST)).toBe(phrases.grumble.at(-1));
  });

  it("says «ya vale» to a petting that raised no affection", () => {
    const state = stateOf({});

    expect(chooseBubble(state, outcome("pet", { deltas: { affection: 0 } }), FIRST)).toBe(phrases.enough[0]);
    expect(chooseBubble(state, outcome("pet", { deltas: { affection: 15 } }), FIRST)).toBe(phrases.applied.pet[0]);
  });

  it("has words for each action applied without an item", () => {
    const actions = ["bathe", "sleep", "wake"] as const;

    for (const action of actions) {
      expect(chooseBubble(stateOf({}), outcome(action, {}), FIRST)).toBe(phrases.applied[action][0]);
    }
  });

  it("celebrates healing above the reaction to what healed it", () => {
    const healed = outcome("feed", { reaction: { item_key: "broccoli", affinity: -2 }, sickness: "healed" });

    expect(chooseBubble(stateOf({}), healed, FIRST)).toBe(phrases.healed[0]);
  });

  it("says how it took what it was given, even when that left it sick", () => {
    const fellSick = outcome("play", { reaction: { item_key: "ball", affinity: 2 }, sickness: "fell_sick" });

    expect(chooseBubble(stateOf({ mood: "sick" }), fellSick, FIRST)).toBe(phrases.reactions.activity[2][0]("Pelota"));
  });

  it("says it feels unwell when an action without an item left it sick", () => {
    const fellSick = outcome("pet", { deltas: { affection: 15 }, sickness: "fell_sick" });

    expect(chooseBubble(stateOf({ mood: "sick" }), fellSick, FIRST)).toBe(phrases.fellSick[0]);
  });

  it("lasts a few seconds, then goes back to the bubble of its state", () => {
    const state = stateOf({ needs: { hunger: 20 } });
    const fed = took("feed", "pizza", 1);

    expect(chooseBubble({ ...state, now: NOW + BUBBLE_MS - 1 }, fed, FIRST)).toBe(phrases.reactions.food[1][0]("Pizza"));
    expect(chooseBubble({ ...state, now: NOW + BUBBLE_MS }, fed, FIRST)).toBe(phrases.asks.hunger[0]);
  });
});

const TICKLE: LastOutcome = { action: "tickle", at: NOW };

describe("the bubble while tickled", () => {
  it("giggles for a few seconds, then goes back to the bubble of its state", () => {
    const state = stateOf({ mood: "happy" });

    expect(chooseBubble(state, TICKLE, FIRST)).toBe(phrases.tickles[0]);
    expect(chooseBubble({ ...state, now: NOW + BUBBLE_MS - 1 }, TICKLE, LAST)).toBe(phrases.tickles.at(-1));
    expect(chooseBubble({ ...state, now: NOW + BUBBLE_MS }, TICKLE, FIRST)).toBe(phrases.moods.happy[0]);
  });

  it("keeps the same giggle while the fit of tickles goes on", () => {
    expect(tickled(TICKLE, NOW + 300)).toBe(TICKLE);
    expect(tickled(TICKLE, NOW + BUBBLE_MS - 1)).toBe(TICKLE);
  });

  it("starts a new giggle after anything else, or once the last one is over", () => {
    expect(tickled(null, NOW)).toEqual({ action: "tickle", at: NOW });
    expect(tickled(TICKLE, NOW + BUBBLE_MS)).toEqual({ action: "tickle", at: NOW + BUBBLE_MS });
    expect(tickled(outcome("pet", { deltas: { affection: 15 } }), NOW + 100)).toEqual({
      action: "tickle",
      at: NOW + 100,
    });
  });
});

describe("celebrating", () => {
  it("is true while the pet talks about having healed", () => {
    const healed = outcome("bathe", { sickness: "healed" });

    expect(celebrating(healed, NOW)).toBe(true);
    expect(celebrating(healed, NOW + BUBBLE_MS)).toBe(false);
  });

  it("is false after anything else, tickles included", () => {
    expect(celebrating(null, NOW)).toBe(false);
    expect(celebrating(TICKLE, NOW)).toBe(false);
    expect(celebrating(outcome("bathe", { sickness: "fell_sick" }), NOW)).toBe(false);
  });
});

describe("the bubble's variety", () => {
  it("picks among several phrases with the random given", () => {
    const state = stateOf({ mood: "happy" });

    const first = chooseBubble(state, null, FIRST);
    const last = chooseBubble(state, null, LAST);

    expect(first).not.toBe(last);
    expect(phrases.moods.happy).toContain(last);
  });

  it("has several phrases for every situation", () => {
    const lists: readonly (readonly unknown[])[] = [
      phrases.healed,
      phrases.fellSick,
      phrases.enough,
      phrases.asleep,
      phrases.grumble,
      phrases.tickles,
      ...Object.values(phrases.reactions.food),
      ...Object.values(phrases.reactions.activity),
      ...Object.values(phrases.rejections),
      ...Object.values(phrases.applied),
      ...Object.values(phrases.sick),
      ...Object.values(phrases.asks),
      ...Object.values(phrases.moods),
    ];

    for (const list of lists) expect(list.length).toBeGreaterThanOrEqual(2);
  });
});

describe("the bubble's key", () => {
  it("is new for each outcome, so the same phrase twice in a row is said again", () => {
    const first = outcome("pet", { deltas: { affection: 0 } }, NOW);
    const second = outcome("pet", { deltas: { affection: 0 } }, NOW + 1500);

    expect(chooseBubble({ ...stateOf({}), now: NOW + 1500 }, second, FIRST)).toBe(
      chooseBubble(stateOf({}), first, FIRST),
    );
    expect(bubbleKey(second, NOW + 1500)).not.toBe(bubbleKey(first, NOW));
  });

  it("is the state's once the outcome is over, the same with or without one", () => {
    const fed = took("feed", "pizza", 1);

    expect(bubbleKey(fed, NOW + BUBBLE_MS)).toBe(bubbleKey(null, NOW + BUBBLE_MS));
    expect(bubbleKey(fed, NOW + BUBBLE_MS - 1)).not.toBe(bubbleKey(null, NOW));
  });
});
