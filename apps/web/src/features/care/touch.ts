import type { CareAction, CareActionResult } from "../../shared";

/** The longest pause between two touches on the figure for them to be one burst. */
export const BURST_GAP_MS = 500;

// The touch of a burst from which the pet feels tickles (GLOSSARY.md, «Cosquillas»).
const TICKLES_FROM = 3;

/**
 * What a touch on the figure is: the first of a burst pets, as the button does; the
 * second does nothing; from the third on, tickles, which only show.
 */
export type Touch = "pet" | "nothing" | "tickle";

/** What each touch on the figure is, from their instants in milliseconds, in order. */
export function classifyTouches(instants: readonly number[]): Touch[] {
  let inBurst = 0;
  return instants.map((at, index) => {
    const before = instants[index - 1];
    // A clock that went back starts a new burst rather than stretching this one.
    const continues = before !== undefined && at >= before && at - before <= BURST_GAP_MS;
    inBurst = continues ? inBurst + 1 : 1;
    return inBurst === 1 ? "pet" : inBurst < TICKLES_FROM ? "nothing" : "tickle";
  });
}

/**
 * Whether the engine's answer adds nothing to a giggle in course: a petting it applied,
 * which the first touch of the burst asked for. A refusal or a change of health is news.
 */
export function quietDuringTickles(action: CareAction, result: CareActionResult): boolean {
  return action === "pet" && result.applied && result.sickness === null;
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
  // The last touches of the burst going on: enough for classifyTouches to tell the next
  // one, as from the third on they are all tickles.
  let burst: readonly number[] = [];
  return (at, asleep) => {
    const touches = [...burst, at];
    const touch = classifyTouches(touches).at(-1);
    burst = touch === "pet" ? [at] : touches.slice(-(TICKLES_FROM - 1));
    if (touch === "pet") on.pet();
    else if (touch === "tickle" && !asleep) on.tickle();
  };
}
