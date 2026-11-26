import type { Animation } from "../../scene";
import type { CareAction, CareActionResult, Mood, Pet } from "../../shared";

/** How long the pet reacts to a care action before going back to how it rests. */
export const REACTION_MS = 1600;

const REST_BY_MOOD: Record<Mood, Animation> = { happy: "happy", normal: "idle", sad: "sad", sick: "sad" };

/** What the pet does at rest, from how it is: asleep, or its mood. */
export function restAnimation(pet: Pick<Pet, "mood" | "asleep">): Animation {
  return pet.asleep ? "sleep" : REST_BY_MOOD[pet.mood];
}

const APPLIED: Record<CareAction, Animation> = {
  feed: "eat",
  play: "happy",
  pet: "happy",
  bathe: "surprised",
  sleep: "sleep",
  wake: "surprised",
};

/** How the pet reacts to a care action, applied or refused by the engine. */
export function reactionAnimation(
  action: CareAction,
  result: Pick<CareActionResult, "applied" | "rejection">,
): Animation {
  if (result.applied) return APPLIED[action];
  // Too tired to play is not a tantrum; every other refusal is.
  return result.rejection === "too_tired" ? "sad" : "angry";
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
