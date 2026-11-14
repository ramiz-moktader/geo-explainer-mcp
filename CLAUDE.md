# CLAUDE.md — Geo-Explainer Short Video Generator & MCP Server

## 1. Mission & Product Vision
Build an end-to-end, autonomous software system that generates 1080×1920 (9:16 vertical, 60 FPS) animated map explainer videos in the style of GeoGlobeTales, and packages the entire pipeline as a **Model Context Protocol (MCP)** server installable directly from GitHub via `uvx` for Claude Desktop, Claude Code, and Gemini CLI.

When connected via MCP, the host LLM (Claude or Gemini) acts as the scriptwriter and director: it inspects available map/asset catalogs via MCP Resources, writes a structured `SceneGraph` JSON payload, and invokes MCP Tools to synthesize voiceover, align word-level timestamps, render frame-accurate MapLibre + SVG motion graphics in Remotion, mix audio/SFX, and output a finished `.mp4`.

---

## 2. Repository Structure
Scaffold the repository with the following exact layout so `uvx --from git+https://github.com/<user>/<repo>` works out of the box:

```text
geo-explainer-mcp/
├── CLAUDE.md
├── README.md
├── pyproject.toml                  # Hatchling build + console script `geo-explainer-mcp`
├── src/
│   └── geo_mcp/
│       ├── __init__.py
│       ├── server.py               # FastMCP server (STDIO default + optional --http)
│       ├── models.py               # Strict Pydantic v2 SceneGraph & Timeline schemas
│       ├── asset_catalog.py        # Auto-discovers user-uploaded GeoJSONs, flags, props, SFX
│       ├── audio_aligner.py        # TTS (Edge-TTS default + ElevenLabs optional) + Whisper word alignment
│       ├── timeline_compiler.py    # Converts trigger words into exact 60fps frame numbers
│       ├── sfx_synthesizer.py      # Generates fallback WAV Foley SFX if custom WAVs aren't added
│       └── worker.py               # Background render orchestrator (Audio -> Compile -> Remotion)
├── renderer/                       # Node.js + TypeScript + Remotion + MapLibre GL JS
│   ├── package.json
│   ├── tsconfig.json
│   ├── remotion.config.ts
│   └── src/
│       ├── index.ts
│       ├── Root.tsx
│       ├── types.ts                # Mirrors Pydantic SceneGraph schema
│       ├── GeoExplainer.tsx        # Main 9:16 composition & audio mixer
│       ├── components/
│       │   ├── MapCanvas.tsx       # Deterministic MapLibre GL wrapper + GeoJSON layers
│       │   ├── GeoAnchor.tsx       # Projects [lon, lat] -> [x, y] screen pixels per frame
│       │   ├── FlagAvatar.tsx      # Rounded flag character with expressions, arms & props
│       │   ├── CurvedMapLabel.tsx  # SVG <textPath> curved geographic labels & pointer arrows
│       │   ├── BadgeCluster.tsx    # Spring-animated icon badges (crown, passport, gavel, etc.)
│       │   └── SyncedCaptions.tsx  # Word-highlighted lower-third captions
│       └── utils/
│           └── interpolation.ts    # Camera easing & spring helpers
└── assets/
    ├── geojson/                    # User-uploaded .geojson / .json files (auto-indexed)
    ├── flags/                      # Optional custom SVG/PNG flags (fallback to flag-icons / SVG generator)
    ├── props/                      # Modular SVG props (crown, sword, castle, coin, scroll, shield)
    └── sfx/                        # Foley WAVs (whoosh.wav, pop.wav, thud.wav, clang.wav, ding.wav)
```

---

## 3. Core Technical Requirements

### A. Dynamic User Asset Discovery (`asset_catalog.py`)
The repository owner will upload custom GeoJSON files to `assets/geojson/` (and optionally custom SVGs/WAVs to `assets/flags/`, `assets/props/`, `assets/sfx/`).
- Scan `assets/geojson/*.{geojson,json}` at runtime. Parse each feature's `properties` (inspecting `ISO_A3`, `ISO_3166_2`, `ADM0_A3`, `NAME`, `name`, `id`) to build a live registry mapping region IDs/names to file paths and bounding-box centroids.
- If `assets/geojson/` is empty during initial testing, include a lightweight fallback GeoJSON (`assets/geojson/_starter_uk.geojson`) containing simplified polygons for England (`GB-ENG`), Scotland (`GB-SCT`), Wales (`GB-WLS`), and Northern Ireland (`GB-NIR`) so automated verification tests pass immediately.
- Expose this entire catalog via an MCP Resource (`geo://assets/catalog`) so the calling LLM knows the exact region IDs, centroids, prop names, and SFX names available in the repo.

### B. Strict `SceneGraph` Contract (`models.py` & `types.ts`)
Define a clean, LLM-friendly JSON schema:
- `title` (str), `narration` (str), `voice` (str, default `"en-US-AndrewNeural"`), `music_mood` (optional str).
- `scenes`: Ordered list of scene objects:
  - `scene_id` (str)
  - `start_word` (str — exact word/phrase in `narration` that triggers this scene; scene 0 starts at frame 0)
  - `camera`: `{ "center": [lon, lat], "zoom": float, "pitch": float, "bearing": float, "transition_sec": float }`
  - `polygons`: List of `{ "geojson_file": str, "feature_id": str, "fill_color": str, "border_color": str, "opacity": float, "transition_to_color": Optional[str], "trigger_word": Optional[str] }`
  - `characters`: List of `{ "id": str, "flag_code": str, "coords": [lon, lat], "expression": "neutral"|"angry"|"shocked"|"smug"|"sad", "hat": Optional[str], "prop": Optional[str], "action": "idle"|"bounce"|"slash"|"shake"|"grow", "trigger_word": Optional[str] }`
  - `labels`: List of `{ "text": str, "coords": [lon, lat], "curve": float, "style": "country"|"callout", "pointer_to": Optional[[lon, lat]], "trigger_word": Optional[str] }`
  - `badges`: List of `{ "icon": str, "label": str, "screen_pos": [x_pct, y_pct], "trigger_word": Optional[str] }`
  - `sfx`: List of `{ "sound": str, "trigger_word": str, "volume": float }`

### C. Audio & Word-Level Timestamp Alignment (`audio_aligner.py` & `timeline_compiler.py`)
1. **TTS Generation:**
   - Default to `edge-tts` (zero API key required, fast, high quality).
   - If `ELEVENLABS_API_KEY` is set in environment variables, use ElevenLabs v2 API (`eleven_turbo_v2_5`).
2. **Word Alignment:**
   - Run `faster-whisper` (with `word_timestamps=True`, `compute_type="int8"` on CPU or `float16` on GPU) on the generated narration audio to extract exact `[word, start_sec, end_sec]` tuples.
3. **Timeline Compilation:**
   - Fuzzy-match every `start_word` and `trigger_word` in sequential narration order to its exact timestamp, converting seconds to 60 FPS frame numbers (`frame = round(sec * 60)`).
   - Output `compiled_timeline.json` containing `total_frames`, `audio_path`, `word_timings`, resolved GeoJSON paths/features, and frame-indexed visual/SFX events.

### D. Deterministic MapLibre + Remotion Renderer (`renderer/`)
1. **Zero Race Conditions (Critical):**
   - MapLibre GL renders asynchronously via WebGL. Inside `MapCanvas.tsx`, wrap camera updates and GeoJSON source/layer updates in Remotion's `delayRender()` and only call `continueRender()` inside `map.once('idle', ...)` (with a safety timeout fallback) so headless Chromium never captures blank tiles or half-drawn borders.
   - Set `preserveDrawingBuffer: true` on the MapLibre `Map` instance.
   - Use an open, key-free satellite/terrain raster style (e.g., ESRI World Imagery raster tiles `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}` paired with clean vector borders) so map rendering works immediately with zero API keys, while allowing an optional `MAPTILER_API_KEY` override.
2. **Coordinate Projection (`GeoAnchor.tsx`):**
   - On every frame after camera positioning, project `[lon, lat]` coordinates to 1080×1920 screen coordinates using `map.project([lon, lat])` so `<FlagAvatar />` and `<CurvedMapLabel />` stay locked to geographic features during camera pans and zooms.
3. **Expressive SVG Components:**
   - `<FlagAvatar />`: Rounded-rectangle flag body with crisp border, drop shadow, layered SVG eyes (`neutral`, `angry`, `shocked`, `smug`, `sad`), articulated stick arms, optional headwear (`crown`, `helmet`), and props (`sword`, `castle`, `scroll`, `money_bag`). Animate entrances and actions with Remotion's `spring()`.
   - `<CurvedMapLabel />`: Renders curved country/region typography using SVG `<path>` + `<textPath>` with heavy stroke contrast (`paint-order: stroke fill`) so text is readable over satellite terrain.
   - `<SyncedCaptions />`: Renders 2–4 words per phrase at `y = 78%` height with spring pop-in and active-word color highlight synced to `word_timings`.
4. **Audio Mixing (`GeoExplainer.tsx`):**
   - Layer narration `<Audio>`, frame-accurate SFX `<Sequence from={event.frame}><Audio .../></Sequence>`, and optional background loop ducked to `0.08` volume while narration plays.

### E. MCP Server & GitHub `uvx` Packaging (`pyproject.toml` & `src/geo_mcp/server.py`)
1. **Package Config (`pyproject.toml`):**
   - Bundle `renderer/` and `assets/` inside the wheel/sdist (or locate relative to package root) so running `uvx --from git+https://github.com/<user>/<repo> geo-explainer-mcp` has full access to the Remotion app and assets.
   - On startup or first render, check if `renderer/node_modules` exists; if missing (e.g., fresh `uvx` cache environment), automatically run `npm install --no-audit --no-fund` inside `renderer/`.
2. **MCP Tools & Resources (`fastmcp>=3.0.0`):**
   - Resource `geo://assets/catalog`: Returns JSON list of all discovered GeoJSON files, their feature IDs/names, available props, flags, and SFX.
   - Resource `geo://schema/scene-graph`: Returns the JSON Schema + a complete working example `SceneGraph`.
   - Tool `render_geo_short(scene_graph: SceneGraph, output_dir: str = "./renders") -> dict`: Validates the scene graph, spawns `worker.py` in the background to avoid STDIO timeouts, and returns `{"job_id": "...", "status": "queued"}`.
   - Tool `check_render_status(job_id: str) -> dict`: Returns current stage (`tts`, `aligning`, `rendering`, `done`, `error`), progress percentage, and final `.mp4` path when complete.
   - Tool `preview_scene_frame(scene_graph: SceneGraph, scene_index: int = 0) -> str`: Renders a single PNG still frame via `npx remotion still` for fast visual verification.
   - Support default `stdio` transport (for Claude Desktop / Claude Code / Gemini CLI) and optional `--http --port 8000` flag (for remote VPS deployment).

---

## 4. Sequential Build & Verification Gates
Execute these 5 phases strictly in order. Do not proceed to the next phase until the verification gate for the current phase passes:

- **Phase 1 — Renderer Foundation & Deterministic Map Capture:**
  Initialize `renderer/` with Remotion, MapLibre GL JS, and TypeScript. Build `MapCanvas.tsx` with `delayRender`/`idle` synchronization and ESRI satellite tiles + GeoJSON polygon rendering.
  *Gate:* Run `npx remotion still` and a 2-second `npx remotion render` test on `_starter_uk.geojson`. Verify non-blank MP4 output with visible satellite imagery and highlighted polygons.

- **Phase 2 — SVG Flag Avatars, Labels & Captions:**
  Implement `GeoAnchor.tsx`, `FlagAvatar.tsx` (with all expressions and props), `CurvedMapLabel.tsx`, `BadgeCluster.tsx`, and `SyncedCaptions.tsx`.
  *Gate:* Render a 4-second mock scene featuring England and Wales flag avatars, a curved map label, and synced captions. Verify valid MP4 generation.

- **Phase 3 — Python Audio, Alignment & SFX Pipeline:**
  Build `models.py`, `asset_catalog.py`, `sfx_synthesizer.py` (generate clean synthesized WAVs in `assets/sfx/`), `audio_aligner.py` (`edge-tts` + `faster-whisper`), and `timeline_compiler.py`.
  *Gate:* Run an end-to-end CLI test generating an 8-second narrated video from a test JSON script with voiceover, SFX, and synchronized map animations.

- **Phase 4 — FastMCP Server & `uvx` Packaging:**
  Implement `server.py` and `worker.py`, configure `pyproject.toml` with package-data inclusion for `renderer/` and `assets/`, and add automatic `npm install` bootstrapping.
  *Gate:* Install locally in an isolated virtual environment (`pip install .` or `uvx --from . geo-explainer-mcp`), inspect tools/resources with FastMCP, and execute an end-to-end `render_geo_short` -> `check_render_status` cycle producing a playable `.mp4`.

- **Phase 5 — Documentation (`README.md`):**
  Write a clear `README.md` documenting how to add custom `.geojson` files to `assets/geojson/`, how to connect the GitHub URL to Claude Code, Claude Desktop, and Gemini CLI via `uvx`, and an example prompt for generating a video.

---

## 5. Implementation Notes (added after the first build)

- `src/geo_mcp/paths.py` (not in the original layout) locates the bundled `renderer/` + `assets/`, copies the renderer to a writable cache dir when installed as a wheel, and runs the first-time `npm install`.
- Renderer props are the compiled timeline (`compiled_timeline.json`); narration/SFX/music are staged into a per-job folder passed to Remotion as `--public-dir`. Flags, props and polygon features are inlined into the props.
- Offline/CI switches: `GEO_TTS=placeholder` (synthetic blips with exact timings), `GEO_ALIGN=estimate`, `GEO_BASEMAP=plain` (no tiles). `pytest tests/` runs without network or a browser.
- The first build was verified with those offline stand-ins only. ESRI tiles, Edge-TTS, ElevenLabs and the faster-whisper model download have not yet been exercised end-to-end; verify them first when changing `MapCanvas.tsx` or `audio_aligner.py`.
- `maplibre-gl` is pinned to v5 (`canvasContextAttributes.preserveDrawingBuffer`); `remotion` and `@remotion/cli` must stay on the same exact version.
- `src/geo_mcp/tile_cache.py` (added later): local caching tile proxy + pre-download. The renderer gets its URL as `tile_url` in the timeline. Test it offline with `tests/fake_tile_server.py` (`GEO_TILE_URL=http://127.0.0.1:PORT/{z}/{x}/{y}`).
- First Colab runs confirmed ESRI tiles, Edge-TTS and faster-whisper work. `GEO_GL=angle-egl` + `GEO_CHROME_MODE=chrome-for-testing` does use the GPU there but produced duplicated half-frames; treat GPU mode as experimental.
- `GEO_FPS` (24-60) sets the frame rate; frame offsets authored at 60 fps are scaled.
