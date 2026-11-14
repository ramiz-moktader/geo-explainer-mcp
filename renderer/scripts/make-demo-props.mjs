// Writes demo timelines (no Python needed) used by the Phase 1 / Phase 2 gates:
//   node scripts/make-demo-props.mjs && npx remotion still src/index.ts GeoExplainer out/p1.png --props=demo/phase1.json
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..", "..");
const fc = JSON.parse(
  fs.readFileSync(path.join(root, "assets/geojson/_starter_uk.geojson"), "utf8"),
);
const feat = (id) => fc.features.find((f) => f.properties.ISO_3166_2 === id);
const dataUri = (p) =>
  fs.existsSync(p)
    ? "data:image/svg+xml;base64," + fs.readFileSync(p).toString("base64")
    : null;
const flag = (code) =>
  dataUri(path.join(here, "..", "node_modules/flag-icons/flags/4x3", `${code}.svg`));
const prop = (name) => dataUri(path.join(root, "assets/props", `${name}.svg`));
const basemap = process.env.GEO_BASEMAP === "plain" ? "plain" : "satellite";

const poly = (id, fill, extra = {}) => ({
  geojson_file: "_starter_uk.geojson",
  feature_id: id,
  fill_color: fill,
  border_color: "#ffffff",
  opacity: 0.7,
  transition_to_color: null,
  trigger_word: null,
  feature: feat(id),
  start_frame: 0,
  trigger_frame: null,
  ...extra,
});
const cam = (center, zoom, t = 1) => ({ center, zoom, pitch: 0, bearing: 0, transition_sec: t });
const base = { fps: 60, width: 1080, height: 1920, audio_src: null, music_src: null, sfx_events: [], basemap };

const phase1 = {
  ...base,
  title: "Phase 1 map capture",
  show_title: false,
  total_frames: 120,
  narration_end_frame: 120,
  word_timings: [],
  scenes: [
    {
      scene_id: "uk",
      start_frame: 0,
      end_frame: 60,
      camera: cam([-3.2, 54.6], 4.75),
      polygons: [
        poly("GB-ENG", "#e0314b"),
        poly("GB-SCT", "#2f6fd6"),
        poly("GB-WLS", "#27a85a"),
        poly("GB-NIR", "#f0a500"),
      ],
      characters: [], labels: [], badges: [],
    },
    {
      scene_id: "zoom",
      start_frame: 60,
      end_frame: 120,
      camera: cam([-2.2, 52.6], 5.6, 0.9),
      polygons: [
        poly("GB-ENG", "#e0314b", { start_frame: 60, transition_to_color: "#ffd84a", trigger_frame: 80 }),
        poly("GB-WLS", "#27a85a", { start_frame: 60 }),
      ],
      characters: [], labels: [], badges: [],
    },
  ],
};

const words = "England and Wales have shared a border for centuries".split(" ");
const phase2 = {
  ...base,
  title: "England vs Wales",
  total_frames: 240,
  narration_end_frame: 240,
  word_timings: words.map((w, i) => ({ word: w, start: 0.3 + i * 0.38, end: 0.3 + i * 0.38 + 0.33 })),
  scenes: [
    {
      scene_id: "duo",
      start_frame: 0,
      end_frame: 240,
      camera: cam([-2.6, 52.5], 5.7),
      polygons: [poly("GB-ENG", "#e0314b"), poly("GB-WLS", "#27a85a")],
      characters: [
        { id: "eng", flag_code: "gb-eng", coords: [-1.2, 52.6], expression: "smug", hat: "crown", prop: "sword", action: "slash", trigger_word: null, start_frame: 10, flag_src: flag("gb-eng"), hat_src: prop("crown"), prop_src: prop("sword") },
        { id: "wls", flag_code: "gb-wls", coords: [-3.8, 52.2], expression: "angry", hat: null, prop: "shield", action: "shake", trigger_word: null, start_frame: 50, flag_src: flag("gb-wls"), hat_src: null, prop_src: prop("shield") },
      ],
      labels: [
        { text: "England", coords: [-1.3, 53.75], curve: 0.5, style: "country", pointer_to: null, trigger_word: null, start_frame: 20 },
        { text: "Offa's Dyke", coords: [-3.6, 50.9], curve: 0, style: "callout", pointer_to: [-3.05, 52.3], trigger_word: null, start_frame: 110 },
      ],
      badges: [
        { icon: "castle", label: "600+ castles", screen_pos: [30, 14], trigger_word: null, start_frame: 130, icon_src: prop("castle") },
        { icon: "crown", label: "1 crown", screen_pos: [70, 21], trigger_word: null, start_frame: 160, icon_src: prop("crown") },
      ],
    },
  ],
};

const out = path.join(here, "..", "demo");
fs.mkdirSync(out, { recursive: true });
fs.writeFileSync(path.join(out, "phase1.json"), JSON.stringify(phase1));
fs.writeFileSync(path.join(out, "phase2.json"), JSON.stringify(phase2));
console.log("wrote", out, "basemap:", basemap);
