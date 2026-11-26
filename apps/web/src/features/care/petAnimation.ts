import type { Animation } from "../../scene";
import type { Affinity, CareAction, CareActionResult, Mood, Pet } from "../../shared";

/** How long the pet reacts to a care action before going back to how it rests. */
export const REACTION_MS = 1600;

const REST_BY_MOOD: Record<Mood, Animation> = { happy: "happy", normal: "idle", sad: "sad", sick: "sad" };

/** What the pet does at rest, from how it is: asleep, or its mood. */
export function restAnimation(pet: Pick<Pet, "mood" | "asleep">): Animation {
  return pet.asleep ? "sleep" : REST_BY_MOOD[pet.mood];
}

// The single map from the pet and what just happened to it to the clip it plays
// (TWO-48, «Emociones y animaciones»): its rest above, its reactions here.
const APPLIED: Record<CareAction, Animation> = {
  feed: "eat",
  play: "happy",
  pet: "happy",
  bathe: "surprised",
  sleep: "sleep",
  wake: "surprised",
};

// Loving or liking it is a joy, neutral or not liking it is just eating (or playing),
// and disgust is a comic tantrum.
const BY_AFFINITY: Record<Affinity, Animation> = { "2": "happy", "1": "happy", "0": "eat", "-1": "eat", "-2": "angry" };

/** How the pet reacts to a care action, applied or refused by the engine. */
export function reactionAnimation(
  action: CareAction,
  result: Pick<CareActionResult, "applied" | "reaction" | "sickness" | "pet">,
): Animation {
  // A refusal is a tantrum, except asleep: it grumbles and goes on sleeping.
  if (!result.applied) return result.pet.asleep ? "sleep" : "angry";
  if (result.sickness === "healed") return "happy";
  // What it was given goes before falling sick; its rest turns sad right after.
  if (result.reaction !== null) return BY_AFFINITY[result.reaction.affinity];
  if (result.sickness === "fell_sick") return "sad";
  return APPLIED[action];
}

/** What the scene is playing: the rest, or a reaction until a moment. */
export interface PetStage {
  rest: Animation;
  playing: Animation;
  reactingUntil: number | null;
}

/** The stage after an event, and the clip to play on the scene, if any. */
export interface StageStep {
  stage: PetStage;
  play: Animation | null;
}

/** The stage when Casa opens: playing the rest. */
export function openStage(rest: Animation): StageStep {
  return { stage: { rest, playing: rest, reactingUntil: null }, play: rest };
}

/** The pet's mood or sleep changed: a reaction in course finishes first. */
export function changeRest(stage: PetStage, rest: Animation): StageStep {
  const changed = { ...stage, rest };
  if (stage.reactingUntil !== null || stage.playing === rest) return { stage: changed, play: null };
  return { stage: { ...changed, playing: rest }, play: rest };
}

/** A care action came back: its reaction plays from the start, even if already playing. */
export function react(stage: PetStage, reaction: Animation, now: number): StageStep {
  return { stage: { ...stage, playing: reaction, reactingUntil: now + REACTION_MS }, play: reaction };
}

/** Time passed: once the reaction is over, back to the rest. */
export function tick(stage: PetStage, now: number): StageStep {
  if (stage.reactingUntil === null || now < stage.reactingUntil) return { stage, play: null };
  const resting = { ...stage, playing: stage.rest, reactingUntil: null };
  return { stage: resting, play: stage.playing === stage.rest ? null : stage.rest };
}
