import { useCallback, useState } from "react";

import type { CareAction, CareActionResult } from "../../shared";
import type { LastOutcome } from "./bubble";

/**
 * What the pet's bubble needs besides the pet: the last care outcome, and a luck drawn
 * again with each one. The luck picks among the phrases of a situation and stays while
 * the situation does, so the bubble does not change its words on every tick.
 */
export function usePetBubble() {
  const [heard, setHeard] = useState<{ last: LastOutcome | null; luck: number }>(() => ({
    last: null,
    luck: Math.random(),
  }));
  // Stable, so Casa's care taps (and their lock) live as long as Casa.
  const hear = useCallback((action: CareAction, result: CareActionResult) => {
    setHeard({ last: { action, result, at: Date.now() }, luck: Math.random() });
  }, []);
  return { last: heard.last, luck: heard.luck, hear };
}
