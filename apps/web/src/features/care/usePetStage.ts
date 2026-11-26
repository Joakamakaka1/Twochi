import { useCallback, useEffect, useRef } from "react";
import type { RefObject } from "react";

import type { Animation, PetSceneHandle } from "../../scene";
import type { CareAction, CareActionResult, Pet } from "../../shared";
import { changeRest, openStage, react, reactionAnimation, restAnimation, tick } from "./petAnimation";
import type { PetStage, StageStep } from "./petAnimation";

// Keeps the stage outside React state, so a reaction never re-renders Casa: each step
// only calls play() on the scene and, while reacting, sets a timer to go back to rest.
function createStageDriver(play: (animation: Animation) => void) {
  let stage: PetStage | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;

  function apply(step: StageStep) {
    stage = step.stage;
    if (step.play !== null) play(step.play);
    clearTimeout(timer);
    const until = stage.reactingUntil;
    if (until === null) return;
    timer = setTimeout(() => {
      if (stage !== null) apply(tick(stage, Date.now()));
    }, until - Date.now());
  }

  return {
    rest(animation: Animation) {
      apply(stage === null ? openStage(animation) : changeRest(stage, animation));
    },
    react(action: CareAction, result: CareActionResult) {
      if (stage !== null) apply(react(stage, reactionAnimation(action, result), Date.now()));
    },
    stop() {
      clearTimeout(timer);
    },
  };
}

type StageDriver = ReturnType<typeof createStageDriver>;

/**
 * Plays on `scene` the rest that fits the pet, and returns how to make it react to a
 * care result.
 */
export function usePetStage(
  pet: Pick<Pet, "mood" | "asleep">,
  scene: RefObject<PetSceneHandle | null>,
): (action: CareAction, result: CareActionResult) => void {
  const driver = useRef<StageDriver | null>(null);
  useEffect(() => {
    const created = createStageDriver((animation) => {
      scene.current?.play(animation);
    });
    driver.current = created;
    return () => {
      created.stop();
      driver.current = null;
    };
  }, [scene]);
  const rest = restAnimation(pet);
  useEffect(() => {
    driver.current?.rest(rest);
  }, [rest]);
  return useCallback((action, result) => {
    driver.current?.react(action, result);
  }, []);
}
