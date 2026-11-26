import type { Animation } from "../../scene";
import type { CareAction, CareActionResult, Pet } from "../../shared";

/** How long the pet reacts to a care action before going back to how it rests. */
export const REACTION_MS = 1600;

/** What the pet does at rest, from how it is: asleep, or its mood. */
export function restAnimation(_pet: Pick<Pet, "mood" | "asleep">): Animation {
  throw new Error("not implemented");
}

/** How the pet reacts to a care action, applied or refused by the engine. */
export function reactionAnimation(
  _action: CareAction,
  _result: Pick<CareActionResult, "applied" | "rejection">,
): Animation {
  throw new Error("not implemented");
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

export function openStage(_rest: Animation): StageStep {
  throw new Error("not implemented");
}

export function changeRest(_stage: PetStage, _rest: Animation): StageStep {
  throw new Error("not implemented");
}

export function react(_stage: PetStage, _reaction: Animation, _now: number): StageStep {
  throw new Error("not implemented");
}

export function tick(_stage: PetStage, _now: number): StageStep {
  throw new Error("not implemented");
}
