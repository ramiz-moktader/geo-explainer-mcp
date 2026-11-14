import React from "react";
import { Composition } from "remotion";
import { GeoExplainer } from "./GeoExplainer";
import type { Timeline } from "./types";

const camera = { center: [-3, 54.5] as [number, number], zoom: 4.6, pitch: 0, bearing: 0, transition_sec: 1 };

// Minimal props so `npm run studio` opens; real renders pass --props=<timeline>.
const defaultTimeline: Timeline = {
  title: "Geo Explainer",
  fps: 60,
  width: 1080,
  height: 1920,
  total_frames: 120,
  audio_src: null,
  music_src: null,
  narration_end_frame: 120,
  word_timings: [],
  scenes: [
    {
      scene_id: "empty",
      start_frame: 0,
      end_frame: 120,
      camera,
      polygons: [],
      characters: [],
      labels: [],
      badges: [],
    },
  ],
  sfx_events: [],
  basemap: "plain",
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="GeoExplainer"
    component={GeoExplainer}
    width={1080}
    height={1920}
    fps={60}
    durationInFrames={120}
    defaultProps={defaultTimeline}
    calculateMetadata={({ props }) => ({
      durationInFrames: Math.max(1, props.total_frames),
      fps: props.fps ?? 60,
      width: props.width ?? 1080,
      height: props.height ?? 1920,
    })}
  />
);
