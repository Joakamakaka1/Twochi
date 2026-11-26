import type { Animation } from "./clips";

/** Where the placeholder figure is at one instant, relative to standing still on the floor. */
export interface Pose {
  /** Body scale on x, y and z; squash and stretch keeps the volume. */
  scale: readonly [number, number, number];
  /** How high the body is off the floor (a hop). */
  lift: number;
  /** Sideways offset (a tremble). */
  sway: number;
  /** Sideways tilt in radians (a head tilt, lying down). */
  tilt: number;
  /** Forward lean in radians (drooping, leaning to the food). */
  lean: number;
  /** How open the eyes are: 0 closed, 1 open, more is wide open. */
  eyes: number;
}

/** The pose of `animation` `elapsed` seconds after it started playing. */
export function proceduralPose(_animation: Animation, _elapsed: number): Pose {
  throw new Error("not implemented");
}
