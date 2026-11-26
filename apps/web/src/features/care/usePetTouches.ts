import { useCallback, useMemo } from "react";

import type { CareAction } from "../../shared";
import { petTouches } from "./touch";

/** What a touch on the figure sets off in Casa. */
interface PetTouchesProps {
  asleep: boolean;
  /** Casa's care tap, for the petting of a burst's first touch. */
  tap: (action: CareAction) => void;
  /** The stage's giggle and the bubble's, for each tickle. */
  tickle: () => void;
  hearTickle: () => void;
}

/**
 * The figure's touches: the first of a burst pets, as the button does, and tickles stay
 * on screen. The handler is new only when the pet falls asleep or wakes, so the memoised
 * scene skips the bars' tick.
 */
export function usePetTouches({ asleep, tap, tickle, hearTickle }: PetTouchesProps): () => void {
  const touches = useMemo(
    () =>
      petTouches({
        pet: () => {
          tap("pet");
        },
        tickle: () => {
          tickle();
          hearTickle();
        },
      }),
    [tap, tickle, hearTickle],
  );
  return useCallback(() => {
    touches(performance.now(), asleep);
  }, [touches, asleep]);
}
