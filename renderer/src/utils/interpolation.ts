import { Easing, interpolate, spring } from "remotion";
import type { Camera, CompiledScene } from "../types";

export const clamp01 = (t: number) => Math.max(0, Math.min(1, t));
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;

const lerpAngle = (a: number, b: number, t: number) => {
  const d = ((((b - a) % 360) + 540) % 360) - 180;
  return a + d * t;
};

export const sceneIndexAt = (scenes: CompiledScene[], frame: number) => {
  let idx = 0;
  for (let i = 0; i < scenes.length; i++) {
    if (scenes[i].start_frame <= frame) idx = i;
  }
  return idx;
};

/** Camera state at an exact frame: a pure function of the frame number. */
export const cameraAtFrame = (
  scenes: CompiledScene[],
  frame: number,
  fps: number,
): Camera => {
  const i = sceneIndexAt(scenes, frame);
  const target = scenes[i].camera;
  if (i === 0) return target;
  const start = scenes[i].start_frame;
  const dur = Math.max(1, Math.round(target.transition_sec * fps));
  const raw = clamp01((frame - start) / dur);
  if (raw >= 1) return target;
  // Start from wherever the previous scene's camera actually was.
  const from = cameraAtFrame(scenes, start - 1, fps);
  const t = Easing.inOut(Easing.cubic)(raw);
  // Zoom out slightly mid-flight on long moves so the pan reads as a "fly".
  const dist = Math.hypot(
    target.center[0] - from.center[0],
    target.center[1] - from.center[1],
  );
  const hop = Math.min(1.2, dist / 25) * Math.sin(Math.PI * t);
  return {
    center: [
      lerp(from.center[0], target.center[0], t),
      lerp(from.center[1], target.center[1], t),
    ],
    zoom: lerp(from.zoom, target.zoom, t) - hop,
    pitch: lerp(from.pitch, target.pitch, t),
    bearing: lerpAngle(from.bearing, target.bearing, t),
    transition_sec: target.transition_sec,
  };
};

/** 0 -> 1 spring pop that begins at `startFrame`. */
export const popIn = (
  frame: number,
  startFrame: number,
  fps: number,
  damping = 11,
) =>
  frame < startFrame
    ? 0
    : spring({
        frame: frame - startFrame,
        fps,
        config: { damping, stiffness: 170, mass: 0.7 },
      });

export const fade = (frame: number, startFrame: number, len = 12) =>
  interpolate(frame, [startFrame, startFrame + len], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
