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

// What each clip does, before the squash every clip starts with: `height` is the body's
// squash (< 1) or stretch (> 1) on y.
interface Motion {
  height: number;
  lift: number;
  sway: number;
  tilt: number;
  lean: number;
  eyes: number;
}

const TAU = Math.PI * 2;
const STILL: Motion = { height: 1, lift: 0, sway: 0, tilt: 0, lean: 0, eyes: 1 };

// Every clip starts with a quick squash and rebound, so each play() reads as a reaction.
const START_SECONDS = 0.3;
const START_SQUASH = 0.18;

function wave(t: number, period: number): number {
  return Math.sin((TAU * t) / period);
}

function breath(t: number, period: number, depth: number): number {
  return 1 + depth * wave(t, period);
}

// A hop of `height` that lasts `duration`, every `every` seconds from `delay` on.
function hop(t: number, every: number, duration: number, height: number, delay: number): number {
  if (t < delay) return 0;
  const progress = ((t - delay) % every) / duration;
  return progress < 1 ? height * Math.sin(Math.PI * progress) : 0;
}

// Stretched while in the air, as cartoons do.
function hopping(breathing: number, lift: number): Pick<Motion, "height" | "lift"> {
  return { height: breathing * (1 + 0.6 * lift), lift };
}

const MOTIONS: Record<Animation, (t: number) => Motion> = {
  idle: (t) => ({ ...STILL, ...hopping(breath(t, 3, 0.03), hop(t, 4, 0.35, 0.08, 1.5)) }),
  happy: (t) => ({
    ...STILL,
    ...hopping(breath(t, 2, 0.04), hop(t, 1.2, 0.4, 0.22, 0.4)),
    tilt: 0.08 * wave(t, 2.4),
  }),
  sad: (t) => ({ ...STILL, height: 0.95 * breath(t, 4.5, 0.02), lean: 0.25, eyes: 0.6 }),
  sleep: (t) => ({ ...STILL, height: 0.85 * breath(t, 5, 0.05), tilt: 0.5, eyes: 0 }),
  eat: (t) => ({ ...STILL, height: 1 + 0.1 * wave(t, 0.25), lean: 0.2 }),
  angry: (t) => ({ ...STILL, height: 0.92, sway: 0.05 * wave(t, 0.1), lean: -0.05, eyes: 0.7 }),
  surprised: (t) => ({
    ...STILL,
    height: 1 + 0.15 * Math.min(t / 0.4, 1),
    lift: t < 0.45 ? 0.3 * Math.sin((Math.PI * t) / 0.45) : 0,
    eyes: 1.4,
  }),
};

/** The pose of `animation` `elapsed` seconds after it started playing. */
export function proceduralPose(animation: Animation, elapsed: number): Pose {
  const t = Math.max(elapsed, 0);
  const motion = MOTIONS[animation](t);
  const start = t < START_SECONDS ? 1 - START_SQUASH * Math.sin((Math.PI * t) / START_SECONDS) : 1;
  const height = motion.height * start;
  const side = 1 / Math.sqrt(height);
  return {
    scale: [side, height, side],
    lift: motion.lift,
    sway: motion.sway,
    tilt: motion.tilt,
    lean: motion.lean,
    eyes: motion.eyes,
  };
}

// A sick pet shivers; for whoever asks the system for less motion, it only sways a little.
const SHIVER = { amplitude: 0.025, period: 0.1 };
const CALM_SWAY = { amplitude: 0.006, period: 1.5 };

/** The sideways offset a sick pet adds to its pose at `seconds` on a running clock. */
export function sickTremble(seconds: number, reducedMotion: boolean): number {
  const { amplitude, period } = reducedMotion ? CALM_SWAY : SHIVER;
  return amplitude * wave(Math.max(seconds, 0), period);
}
