/** The longest pause between two touches on the figure for them to be one burst. */
export const BURST_GAP_MS = 500;

// The touch of a burst from which the pet feels tickles (GLOSSARY.md, «Cosquillas»).
const TICKLES_FROM = 3;

/**
 * What a touch on the figure is: the first of a burst pets, as the button does; the
 * second does nothing; from the third on, tickles, which only show.
 */
export type Touch = "pet" | "nothing" | "tickle";

/** The burst going on: how many touches it has had, and when the last one came. */
interface Burst {
  touches: number;
  last: number;
}

function nextTouch(burst: Burst | null, at: number): { burst: Burst; touch: Touch } {
  const continues = burst !== null && at - burst.last <= BURST_GAP_MS;
  const touches = continues ? burst.touches + 1 : 1;
  const touch = touches === 1 ? "pet" : touches < TICKLES_FROM ? "nothing" : "tickle";
  return { burst: { touches, last: at }, touch };
}

/** What each touch on the figure is, from their instants in milliseconds, in order. */
export function classifyTouches(instants: readonly number[]): Touch[] {
  let burst: Burst | null = null;
  return instants.map((at) => {
    const next = nextTouch(burst, at);
    burst = next.burst;
    return next.touch;
  });
}

/** What touching the figure does: pet through the API, or tickle on screen only. */
export interface TouchHandlers {
  pet: () => void;
  tickle: () => void;
}

/**
 * Follows the touches on the figure and does what each one is. Tickles never reach the
 * API, so touching fast spends no pettings. Asleep, a burst only pets, which the engine
 * refuses with a grumble: a sleeping pet feels no tickles.
 */
export function petTouches(on: TouchHandlers): (at: number, asleep: boolean) => void {
  let burst: Burst | null = null;
  return (at, asleep) => {
    const next = nextTouch(burst, at);
    burst = next.burst;
    if (next.touch === "pet") on.pet();
    else if (next.touch === "tickle" && !asleep) on.tickle();
  };
}
