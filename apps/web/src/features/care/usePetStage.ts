import { useEffect, useState } from "react";

import type { Pet } from "../../shared";
import { restAnimation } from "./petAnimation";
import { createStageDriver } from "./stageDriver";
import type { StageDriver } from "./stageDriver";

/**
 * The pet's stage: it plays the rest that fits the pet on the scene given to `attach`
 * (a callback ref), and `react` plays the reaction to a care result.
 */
export function usePetStage(pet: Pick<Pet, "mood" | "asleep">): Pick<StageDriver, "attach" | "react"> {
  const [driver] = useState(createStageDriver);
  const rest = restAnimation(pet);
  useEffect(() => {
    driver.rest(rest);
  }, [driver, rest]);
  useEffect(
    () => () => {
      driver.stop();
    },
    [driver],
  );
  return driver;
}
