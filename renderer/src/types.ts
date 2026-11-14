// Mirrors src/geo_mcp/models.py. The first block is the SceneGraph the LLM
// writes; the second block is the compiled timeline the renderer consumes.
import type { Feature } from "geojson";

export type LonLat = [number, number];
export type Expression = "neutral" | "angry" | "shocked" | "smug" | "sad";
export type Action = "idle" | "bounce" | "slash" | "shake" | "grow";
export type LabelStyle = "country" | "callout";

export interface Camera {
  center: LonLat;
  zoom: number;
  pitch: number;
  bearing: number;
  transition_sec: number;
}

export interface PolygonSpec {
  geojson_file: string;
  feature_id: string;
  fill_color: string;
  border_color: string;
  opacity: number;
  transition_to_color?: string | null;
  trigger_word?: string | null;
}

export interface CharacterSpec {
  id: string;
  flag_code: string;
  coords: LonLat;
  expression: Expression;
  hat?: string | null;
  prop?: string | null;
  action: Action;
  trigger_word?: string | null;
}

export interface LabelSpec {
  text: string;
  coords: LonLat;
  curve: number;
  style: LabelStyle;
  pointer_to?: LonLat | null;
  trigger_word?: string | null;
}

export interface BadgeSpec {
  icon: string;
  label: string;
  screen_pos: [number, number];
  trigger_word?: string | null;
}

export interface SfxSpec {
  sound: string;
  trigger_word: string;
  volume: number;
}

export interface SceneSpec {
  scene_id: string;
  start_word: string;
  camera: Camera;
  polygons: PolygonSpec[];
  characters: CharacterSpec[];
  labels: LabelSpec[];
  badges: BadgeSpec[];
  sfx: SfxSpec[];
}

export interface SceneGraph {
  title: string;
  narration: string;
  voice: string;
  music_mood?: string | null;
  scenes: SceneSpec[];
}

// ---------------------------------------------------------------- compiled

export interface WordTiming {
  word: string;
  start: number;
  end: number;
}

export interface CompiledPolygon extends PolygonSpec {
  feature: Feature;
  start_frame: number;
  trigger_frame: number | null;
}

export interface CompiledCharacter extends CharacterSpec {
  start_frame: number;
  flag_src: string | null; // data URI, or null -> generated flag
  hat_src: string | null;
  prop_src: string | null;
}

export interface CompiledLabel extends LabelSpec {
  start_frame: number;
}

export interface CompiledBadge extends BadgeSpec {
  start_frame: number;
  icon_src: string | null;
}

export interface CompiledScene {
  scene_id: string;
  start_frame: number;
  end_frame: number;
  camera: Camera;
  polygons: CompiledPolygon[];
  characters: CompiledCharacter[];
  labels: CompiledLabel[];
  badges: CompiledBadge[];
}

export interface SfxEvent {
  sound: string;
  src: string; // path relative to the public dir
  frame: number;
  volume: number;
}

export interface Timeline {
  title: string;
  fps: number;
  width: number;
  height: number;
  total_frames: number;
  audio_src: string | null;
  music_src: string | null;
  narration_end_frame: number;
  word_timings: WordTiming[];
  scenes: CompiledScene[];
  sfx_events: SfxEvent[];
  basemap: "satellite" | "plain";
  maptiler_key?: string | null;
  show_title?: boolean;
  [key: string]: unknown;
}
