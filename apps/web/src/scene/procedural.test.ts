import { describe, expect, it } from "vitest";

import { ANIMATIONS } from "./clips";
import type { Animation } from "./clips";
import { proceduralPose, sickTremble } from "./procedural";

// The pose sampled at 60 frames a second, from `from` to `to` seconds after play.
function frames(animation: Animation, from: number, to: number) {
  const poses = [];
  for (let t = from; t <= to; t += 1 / 60) poses.push(proceduralPose(animation, t));
  return poses;
}

const highest = (animation: Animation) => Math.max(...frames(animation, 1, 13).map((pose) => pose.lift));

// Times the body leaves the floor in twelve seconds.
function hops(animation: Animation) {
  let count = 0;
  let wasUp = false;
  for (const pose of frames(animation, 1, 13)) {
    const up = pose.lift > 0.01;
    if (up && !wasUp) count += 1;
    wasUp = up;
  }
  return count;
}

describe("proceduralPose", () => {
  it.each(ANIMATIONS)("keeps the volume of the body while %s squashes and stretches", (animation) => {
    for (const pose of frames(animation, 0, 6)) {
      const [x, y, z] = pose.scale;
      expect(x * y * z).toBeCloseTo(1, 6);
      expect(pose.lift).toBeGreaterThanOrEqual(0);
    }
  });

  it("breathes at rest: the body grows and shrinks", () => {
    const heights = frames("idle", 1, 5).map((pose) => pose.scale[1]);

    expect(Math.max(...heights) - Math.min(...heights)).toBeGreaterThan(0.02);
  });

  it("hops higher and more often when happy than at rest", () => {
    expect(highest("happy")).toBeGreaterThan(highest("idle"));
    expect(hops("happy")).toBeGreaterThan(hops("idle"));
    expect(hops("idle")).toBeGreaterThan(0);
  });

  it("does not hop when sad, and droops forward", () => {
    for (const pose of frames("sad", 1, 13)) {
      expect(pose.lift).toBe(0);
      expect(pose.lean).toBeGreaterThan(0);
    }
  });

  it("sleeps lying down with the eyes closed, still breathing", () => {
    const poses = frames("sleep", 1, 13);
    const heights = poses.map((pose) => pose.scale[1]);

    for (const pose of poses) {
      expect(pose.eyes).toBe(0);
      expect(pose.lift).toBe(0);
      expect(Math.abs(pose.tilt)).toBeGreaterThan(0.2);
    }
    expect(Math.max(...heights) - Math.min(...heights)).toBeGreaterThan(0.02);
  });

  it("is awake with the eyes open in every other clip", () => {
    for (const animation of ANIMATIONS.filter((each) => each !== "sleep")) {
      expect(proceduralPose(animation, 2).eyes, animation).toBeGreaterThan(0.5);
    }
  });

  it("squashes as each clip starts, deeper than breathing", () => {
    for (const animation of ANIMATIONS) {
      const start = Math.min(...frames(animation, 0, 0.3).map((pose) => pose.scale[1]));
      expect(start, animation).toBeLessThan(0.9);
    }
    const resting = Math.min(...frames("idle", 1, 13).map((pose) => pose.scale[1]));
    expect(resting).toBeGreaterThan(0.95);
  });

  it("trembles when angry: it shakes from side to side several times a second", () => {
    const sides = frames("angry", 0.5, 1.5).map((pose) => Math.sign(pose.sway));
    const changes = sides.filter((side, index) => index > 0 && side !== 0 && side !== sides[index - 1]).length;

    expect(changes).toBeGreaterThan(8);
  });

  it("chomps when eating: it squashes and stretches several times a second, leaning to the food", () => {
    const poses = frames("eat", 0.5, 1.5);
    const heights = poses.map((pose) => pose.scale[1]);
    const peaks = heights.filter(
      (height, index) => height > (heights[index - 1] ?? Infinity) && height > (heights[index + 1] ?? Infinity),
    ).length;

    expect(peaks).toBeGreaterThanOrEqual(3);
    for (const pose of poses) expect(pose.lean).toBeGreaterThan(0);
  });

  it("jumps and stretches up with wide eyes when surprised", () => {
    expect(Math.max(...frames("surprised", 0, 0.6).map((pose) => pose.lift))).toBeGreaterThan(0.15);
    const after = proceduralPose("surprised", 1);
    expect(after.scale[1]).toBeGreaterThan(1.1);
    expect(after.eyes).toBeGreaterThan(1);
  });

  it("gives a finite pose however long the clip has been playing", () => {
    for (const animation of ANIMATIONS) {
      const pose = proceduralPose(animation, 86_400 * 3);
      for (const value of [...pose.scale, pose.lift, pose.sway, pose.tilt, pose.lean, pose.eyes]) {
        expect(Number.isFinite(value), animation).toBe(true);
      }
    }
  });
});

// The tremble sampled at 60 frames a second for `seconds` seconds.
function trembling(seconds: number, reducedMotion: boolean) {
  const sways = [];
  for (let t = 0; t <= seconds; t += 1 / 60) sways.push(sickTremble(t, reducedMotion));
  return sways;
}

// Times a sideways motion turns back, per second.
function turnsPerSecond(sways: readonly number[], seconds: number) {
  let turns = 0;
  for (let i = 2; i < sways.length; i += 1) {
    const before = (sways[i - 1] ?? 0) - (sways[i - 2] ?? 0);
    const now = (sways[i] ?? 0) - (sways[i - 1] ?? 0);
    if (before * now < 0) turns += 1;
  }
  return turns / seconds;
}

describe("sickTremble", () => {
  it("shakes a sick pet quickly and visibly", () => {
    const sways = trembling(4, false);

    expect(Math.max(...sways.map(Math.abs))).toBeGreaterThanOrEqual(0.02);
    expect(turnsPerSecond(sways, 4)).toBeGreaterThanOrEqual(8);
  });

  it("softens into a slow, small sway for whoever asks for less motion", () => {
    const calm = trembling(4, true);
    const shaking = trembling(4, false);

    expect(Math.max(...calm.map(Math.abs))).toBeLessThanOrEqual(Math.max(...shaking.map(Math.abs)) / 3);
    expect(turnsPerSecond(calm, 4)).toBeLessThanOrEqual(2);
  });
});
