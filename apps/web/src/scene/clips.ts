/** The pet's animation clips, named as the rigged GLB will name them. */
export const ANIMATIONS = ["idle", "happy", "sad", "eat", "sleep", "angry", "surprised"] as const;

export type Animation = (typeof ANIMATIONS)[number];
