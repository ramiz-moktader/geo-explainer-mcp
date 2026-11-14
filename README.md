# geo-explainer-mcp

An MCP server that turns a script into a **1080×1920, 60 fps animated map explainer short**: satellite map, highlighted regions, talking flag characters, curved labels, badges, word-synced captions, voiceover and sound effects.

You (or Claude / Gemini) write a `SceneGraph` JSON; the server does the rest:

```
SceneGraph ─▶ TTS (Edge-TTS / ElevenLabs) ─▶ word alignment (faster-whisper)
           ─▶ frame-accurate timeline ─▶ MapLibre + Remotion render ─▶ .mp4
```

> **Status of this first build.** The whole pipeline was built and rendered end-to-end in a sandbox with **no access to map tiles, Edge-TTS or the Whisper model**, so it was verified with offline stand-ins (plain vector basemap, synthetic "blip" narration with exact timings). The real satellite, TTS, ElevenLabs and Whisper paths are implemented but **have not been run yet** — run the [first-run check](#first-run-check) on your machine before relying on them.

## Two ways to use it (both free)

| | Where it renders | How |
| --- | --- | --- |
| **From Claude** | your computer | connect the MCP server: [`setup/CLAUDE_SETUP.md`](setup/CLAUDE_SETUP.md) |
| **On Colab** | Google's machine | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/ramiz-moktader/geo-explainer-mcp/blob/main/colab/geo_explainer_colab.ipynb) then paste a SceneGraph JSON |

The Colab notebook has not been run on Colab yet; expect to adjust the setup cell once.

## Requirements

| Needed | Why |
| --- | --- |
| Python 3.10+ and [`uv`](https://docs.astral.sh/uv/) | runs the server via `uvx` |
| Node.js 18+ (with `npm`/`npx` on PATH) | Remotion renderer; `npm install` runs automatically on first use |
| Internet access | ESRI satellite tiles, Edge-TTS, one-time Whisper model + headless Chrome download |

No API keys are required. Optional: `ELEVENLABS_API_KEY` (better voices), `MAPTILER_API_KEY` (MapTiler satellite tiles instead of ESRI).

## 1. Add your own maps

Drop `.geojson` / `.json` files (GeoJSON `FeatureCollection`s of polygons, WGS84 lon/lat) into `assets/geojson/` and push. They are indexed automatically at runtime — no code changes.

Each feature needs at least one identifying property. These are checked in order, and the first one found becomes the region id (all of them work as aliases, case-insensitively):

`ISO_3166_2` → `ISO_A3` → `ADM0_A3` → `id` → `NAME` → `name`

```json
{ "type": "Feature",
  "properties": { "ISO_3166_2": "BD-B", "name": "Chattogram Division" },
  "geometry": { "type": "Polygon", "coordinates": [ ... ] } }
```

Tips:

- Simplify heavy boundaries first (e.g. [mapshaper](https://mapshaper.org) to ~1–5 MB per file); every polygon used in a video is embedded in the render props.
- `_starter_uk.geojson` (rough England / Scotland / Wales / Northern Ireland shapes) is only there so tests work on an empty repo. Delete it whenever you like.
- Other optional folders: `assets/flags/<code>.svg|png` (custom flags), `assets/props/<name>.svg` (hats, hand props, badge icons), `assets/sfx/<name>.wav` (overrides the synthesized whoosh/pop/thud/clang/ding), `assets/music/<mood>.mp3|wav` (background beds).

Because assets ship inside the package, **`uvx` picks up new files after you push** and refresh: `uvx --refresh --from git+https://github.com/ramiz-moktader/geo-explainer-mcp geo-explainer-mcp`. For local iteration without pushing, point the server at a folder: `GEO_ASSETS_DIR=/path/to/assets`.

## 2. Connect it

Step-by-step version for beginners: [`setup/CLAUDE_SETUP.md`](setup/CLAUDE_SETUP.md).

**Claude Code**

```bash
claude mcp add geo-explainer -- uvx --from git+https://github.com/ramiz-moktader/geo-explainer-mcp geo-explainer-mcp
```

**Claude Desktop** — Settings → Developer → Edit Config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "geo-explainer": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/ramiz-moktader/geo-explainer-mcp", "geo-explainer-mcp"]
    }
  }
}
```

**Gemini CLI** — `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "geo-explainer": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/ramiz-moktader/geo-explainer-mcp", "geo-explainer-mcp"],
      "timeout": 600000
    }
  }
}
```

Add keys with an `"env": { "ELEVENLABS_API_KEY": "..." }` block in either JSON config. If a desktop app cannot find `uvx` or `node`, use their absolute paths.

**Remote / VPS (HTTP transport)**

```bash
uvx --from git+https://github.com/ramiz-moktader/geo-explainer-mcp geo-explainer-mcp --http --port 8000
# MCP endpoint: http://<host>:8000/mcp   (put it behind your own auth/reverse proxy)
```

## 3. Ask for a video

> Read `geo://assets/catalog` and `geo://schema/scene-graph` from the geo-explainer server. Then write and render a 30-second short explaining **why the United Kingdom is made of four countries**. Use 4–5 scenes, give each country a flag character with a fitting expression, add a curved label per country, one badge, and whoosh/pop SFX on the key words. Preview scene 0 first, then call `render_geo_short` and poll `check_render_status` until it is done. Tell me the MP4 path.

What the server exposes:

| Kind | Name | Purpose |
| --- | --- | --- |
| Resource | `geo://assets/catalog` | every GeoJSON file, region ids/names/centroids, flags, props, SFX |
| Resource | `geo://schema/scene-graph` | JSON Schema + a complete working example |
| Tool | `render_geo_short(scene_graph, output_dir="./renders")` | validates, starts a background render, returns `{job_id, status: "queued"}` |
| Tool | `check_render_status(job_id)` | stage (`tts`, `aligning`, `compiling`, `rendering`, `done`, `error`), progress %, warnings, final `.mp4` path |
| Tool | `preview_scene_frame(scene_graph, scene_index=0)` | one PNG still of a scene, no voiceover needed |

Rules the scriptwriter must follow (also stated in the schema resource): every `start_word` / `trigger_word` must appear verbatim in `narration`; scenes follow narration order; elements live for their scene, so repeat a polygon in the next scene to keep it on screen. Words that cannot be found are reported under `warnings` in the job status rather than failing the render.

## First-run check

Run this once on a machine with normal internet access (clone the repo first):

```bash
uv venv && uv pip install -e . pytest
.venv/bin/python -m pytest -q tests          # offline logic tests, a few seconds
.venv/bin/geo-explainer-render --preview 1 --out renders    # 1 still: are satellite tiles visible?
.venv/bin/geo-explainer-render --out renders                # full built-in example with real voice
```

Check in the output: satellite imagery (not a flat blue/green map), a real voice, captions that highlight in time with it, and no `warning: word timings were ESTIMATED` line (that means Whisper did not run).

`geo-explainer-render my_script.json --out renders` renders any SceneGraph file without an MCP client.

## Configuration

| Variable | Effect |
| --- | --- |
| `ELEVENLABS_API_KEY` | use ElevenLabs (`eleven_turbo_v2_5`); `voice` is then an ElevenLabs voice id (or set `ELEVENLABS_VOICE_ID`) |
| `MAPTILER_API_KEY` | MapTiler satellite tiles instead of ESRI World Imagery |
| `GEO_WHISPER_MODEL` | faster-whisper model, default `base` (`small` is more accurate, slower) |
| `GEO_ASSETS_DIR` | use this assets folder instead of the bundled one |
| `GEO_RENDER_CONCURRENCY` | browser tabs used for rendering (default: Remotion's choice) |
| `GEO_RENDER_SCALE` | e.g. `0.5` for fast 540×960 drafts |
| `GEO_GL` | Chromium GL backend: `swangle` (default on Linux), `angle`, `egl`, `vulkan` |
| `GEO_BROWSER_EXECUTABLE` | use an existing Chrome instead of Remotion's download |
| `GEO_BASEMAP=plain` | key-free, tile-free vector basemap (offline / CI) |
| `GEO_TTS=placeholder` | synthetic blip narration with exact word timings (offline / CI) |
| `GEO_ALIGN=estimate` | skip Whisper, estimate word timings |
| `GEO_CACHE_DIR` | where jobs, previews and the renderer copy live (default `~/.cache/geo-explainer-mcp`) |

## How timing works

1. The narration is synthesized once. `faster-whisper` (`word_timestamps=True`, `int8` on CPU / `float16` on GPU) returns per-word times.
2. Those times are mapped back onto **your script's words**, so captions show exactly what you wrote even when the recognizer mishears a name.
3. Each `start_word` / `trigger_word` is matched in narration order (exact first, then fuzzy) and converted with `frame = round(sec * 60)`.
4. Everything the renderer draws is a pure function of the frame number, and each frame is captured only after MapLibre reports `idle`, so renders are repeatable.

If Whisper is unavailable, the pipeline falls back to Edge-TTS's own word boundaries, then to estimated timings, and says so in `warnings`.

## Troubleshooting

- **`npm`/`npx` not found** — install Node.js 18+ and restart the MCP client.
- **First render is slow** — it runs `npm install` and downloads headless Chrome and the Whisper model once.
- **Flat-colour map instead of satellite** — tiles were unreachable; check the network, or set `MAPTILER_API_KEY`.
- **Render speed** — CPU-only WebGL is slow (the build sandbox, 2 cores, managed under 1 frame/s at full resolution). A machine with a GPU and `GEO_GL=angle` or `egl` is much faster; use `GEO_RENDER_SCALE=0.5` for drafts.
- **Job logs** — `~/.cache/geo-explainer-mcp/jobs/<job_id>/` holds `status.json`, `compiled_timeline.json`, `worker.log`.

## Licences and attribution

- Code in this repository: MIT.
- [Remotion](https://www.remotion.dev/license) is free for individuals and companies of up to three people; larger companies need a paid licence.
- ESRI World Imagery tiles require attribution ("Imagery © Esri and its data providers") and are subject to Esri's terms of use; check them before commercial publishing, or use your own tiles via `MAPTILER_API_KEY`.
- Flags come from [flag-icons](https://github.com/lipis/flag-icons) (MIT); context borders from [world-atlas](https://github.com/topojson/world-atlas) / Natural Earth (public domain).
