# Playbook: make a map explainer video (for an AI coding agent)

You are working inside a clone of this repository with a terminal. Follow these steps in order to turn a topic
into a finished MP4. This is the workflow the project author's assistant used for `examples/chernobyl.json`.
All commands run from the repository root and work the same on Windows, macOS and Linux.

## 0. One-time setup

Needs Node.js 18+ and [`uv`](https://docs.astral.sh/uv/). Then:

```bash
uv sync                      # Python environment + this package
cd renderer && npm install --no-audit --no-fund && cd ..
```

Every command below is run as `uv run geo-explainer-render ...`.

## 1. See what you can use

```bash
uv run geo-explainer-render --catalog     # region ids, props, sfx, flags
uv run geo-explainer-render --schema      # JSON schema + a working example
```

Countries are in `world_countries.geojson` (name or three-letter code, e.g. `BGD`). Anything smaller needs its
own GeoJSON in `assets/geojson/`; for a simple marker area you may add a small circle polygon like
`assets/geojson/chernobyl_zone.geojson`. Flags use two-letter codes (`bd`, `ua`).

## 2. Research and write the script

1. Check the key facts (dates, numbers, places) with a web search before writing. Note anything simplified.
2. Write the narration: about 2.5 words per second, so 75-100 words for 30-40 seconds. Spell numbers as words
   ("nineteen eighty-six"). Short sentences.
3. Save a SceneGraph as `scripts/<topic>.json`, using `examples/chernobyl.json` as the pattern:
   - 5-7 scenes; each `start_word` is the first words of a sentence, in narration order.
   - Every `trigger_word` must appear word-for-word in the narration, inside that scene's stretch of text.
   - Elements live only for their scene. Repeat a polygon in the next scene to keep it visible.
   - `transition_to_color` + `trigger_word` recolours a polygon on that word.
   - Badges: `screen_pos` y between 12 and 25. Captions own the band around y = 78.

```bash
uv run geo-explainer-render scripts/<topic>.json --check    # must print OK
```

## 3. Preview every scene and fix the layout

```bash
uv run geo-explainer-render scripts/<topic>.json --preview 0 --out renders/<topic>
```

Repeat for each scene index and LOOK at each PNG. Fix and re-preview until:

- no flag character sits on top of its own polygon, a label, or a pointer arrow;
- no label runs off the left or right edge;
- the subject fills roughly the middle third of the frame.

Sizing help: a flag character is about 190 px wide and a country label about 60 px tall on the 1080 px wide
frame. One degree of longitude is `512 * 2^zoom / 360` px (zoom 4 = 23 px, zoom 6 = 91 px, zoom 8 = 364 px).
Typical zooms: 3-4 continent, 5-6 country, 7-9 city region.

## 4. Choose the voice

| Option | What to do |
| --- | --- |
| Free voice (default) | nothing; Edge-TTS speaks it and Whisper times the words |
| ElevenLabs by API key | set `ELEVENLABS_API_KEY` in the environment (never write the key into a file in this repo or into chat) |
| A voiceover you already have | set `GEO_NARRATION_AUDIO=path/to/voice.mp3`; optionally `GEO_WORD_TIMINGS=path/to/words.json` (list of `{word, start, end}`), otherwise Whisper aligns it. The narration text must match the audio |

## 5. Render

Draft first (fast, half size), then the final:

```bash
# draft
GEO_RENDER_SCALE=0.5 GEO_FPS=30 uv run geo-explainer-render scripts/<topic>.json --out renders/<topic>
# final 1080x1920
GEO_FPS=30 uv run geo-explainer-render scripts/<topic>.json --out renders/<topic>
```

On Windows PowerShell set variables first, e.g. `$env:GEO_FPS="30"; $env:GEO_RENDER_SCALE="0.5"`, then run the
command (remove with `Remove-Item Env:GEO_RENDER_SCALE` before the final render).

Other switches: `GEO_MAP_DETAIL=0.5` (faster, softer map), `GEO_BASEMAP=plain` (no satellite tiles, for offline
tests). Do not set `GEO_GL` or `GEO_CHROME_MODE` unless asked.

## 6. Check the result before reporting

- Read the lines printed at the end. `warning: word timings were ESTIMATED` means captions are not in sync;
  `map tiles ... failed` above zero means blank squares in the map.
- If `ffmpeg` is available, pull a few frames and look at them, especially just after each trigger word:
  `ffmpeg -ss 7.9 -i renders/<topic>/<file>.mp4 -frames:v 1 check.png`
- Tell the user: the MP4 path, its length, which voice and basemap were used, any warnings, and which facts
  were simplified.

## Rules

- Never commit API keys, `.env`, or files under `renders/`.
- Do not change files under `src/` or `renderer/` to make a single video work; change the script.
- If a step fails, report the exact error text instead of retrying with different settings more than once.
