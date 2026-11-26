import type { Animation, PetSceneHandle } from "../../scene";
import type { CareAction, CareActionResult } from "../../shared";
import { changeRest, openStage, react, reactionAnimation, tick, TICKLE_ANIMATION } from "./petAnimation";
import type { PetStage, StageStep } from "./petAnimation";

/** What drives the pet's scene: its rest, its reactions, and the scene itself. */
export interface StageDriver {
  /** The scene arrived (its handle) or went away (null). */
  attach: (scene: PetSceneHandle | null) => void;
  rest: (animation: Animation) => void;
  react: (action: CareAction, result: CareActionResult) => void;
  /** A tickle on the figure: a giggle, which the next tickle starts again. */
  tickle: () => void;
  stop: () => void;
}

// Keeps the stage outside React state, so a reaction never re-renders Casa: each step
// only calls play() on the scene and, while reacting, sets a timer to go back to rest.
export function createStageDriver(): StageDriver {
  let scene: PetSceneHandle | null = null;
  let stage: PetStage | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;

  function apply(step: StageStep) {
    stage = step.stage;
    if (step.play !== null) scene?.play(step.play);
    clearTimeout(timer);
    const until = stage.reactingUntil;
    if (until === null) return;
    timer = setTimeout(() => {
      if (stage !== null) apply(tick(stage, Date.now()));
    }, until - Date.now());
  }

  return {
    // A lazy scene arrives after the rest was decided: it starts with what is on stage.
    attach: (handle) => {
      scene = handle;
      if (stage !== null) scene?.play(stage.playing);
    },
    rest: (animation) => {
      apply(stage === null ? openStage(animation) : changeRest(stage, animation));
    },
    react: (action, result) => {
      if (stage !== null) apply(react(stage, reactionAnimation(action, result), Date.now()));
    },
    tickle: () => {
      if (stage !== null) apply(react(stage, TICKLE_ANIMATION, Date.now()));
    },
    stop: () => {
      clearTimeout(timer);
    },
  };
}
