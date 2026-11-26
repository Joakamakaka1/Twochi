import type { Affinity } from "../api";

// The face of each step of the affinity, from «lo odio» to «me encanta», in one map: the
// person's own in «Tus gustos», and the reaction seen with an item in its tray. Emoji
// today, and the seam where art replaces them.
export const AFFINITY_FACES: Readonly<Record<Affinity, string>> = { [-2]: "😖", [-1]: "🙁", 0: "😐", 1: "🙂", 2: "😍" };
