# Run it from Google Antigravity (Gemini)

Antigravity runs on your own computer, so the video is rendered there. Gemini writes the script and drives the tools.
This setup has not been tested by the project author; the steps follow Antigravity's standard way of adding a custom MCP server.

## 1. Install (once)

Node.js 18+, `uv` and Git, as in [`CLAUDE_SETUP.md`](CLAUDE_SETUP.md). Check with `node -v` and `uvx --version`.

## 2. Add the server

1. In Antigravity, open the **...** menu at the top of the agent panel and choose **MCP Servers** (MCP Store).
2. Click **Manage MCP Servers**, then **View raw config**. This opens `mcp_config.json`.
3. Add the `geo-explainer` entry (keep any servers already listed), then save:

```json
{
  "mcpServers": {
    "geo-explainer": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/ramiz-moktader/geo-explainer-mcp", "geo-explainer-mcp"],
      "env": {
        "GEO_FPS": "30",
        "GEO_MAP_DETAIL": "0.75"
      }
    }
  }
}
```

4. Back on the Manage MCP Servers page click **Refresh**. `geo-explainer` should list three tools:
   `render_geo_short`, `check_render_status`, `preview_scene_frame`.

If it does not start, replace `"uvx"` with its full path (`where uvx` on Windows, `which uvx` on macOS/Linux).
To use ElevenLabs instead of the free voice, add `"ELEVENLABS_API_KEY": "..."` inside `env` (never commit that file).

## 3. Ask for a video

> Use the geo-explainer MCP server. Read its resources `geo://assets/catalog` and `geo://schema/scene-graph`.
> Then write a SceneGraph for a 30-second vertical map explainer on **<your topic>**, using only region ids from the
> catalog. Every `start_word` and `trigger_word` must appear word-for-word in `narration`, in order.
> Call `preview_scene_frame` for scene 0 and show me the image. Then call `render_geo_short` and poll
> `check_render_status` every 20 seconds until it is done. Tell me the MP4 path.

If Gemini cannot read MCP resources in your version, paste it the contents of `examples/chernobyl.json` as a
pattern and tell it the region ids you want (country names or three-letter codes work).

## Notes

- The first render installs Node packages and downloads headless Chrome and the Whisper model; later ones are faster.
- Antigravity's agent can also just run the command-line tool in its terminal:
  `uvx --from git+https://github.com/ramiz-moktader/geo-explainer-mcp geo-explainer-render my_script.json --out renders`
