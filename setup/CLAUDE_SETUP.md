# Run it from Claude on your own computer (free, no API keys)

The video is rendered on your computer; Claude writes the script and drives the tools.

## 1. Install three things (once)

| Tool | Get it | Check |
| --- | --- | --- |
| Node.js 18+ | https://nodejs.org (LTS installer) | `node -v` |
| uv | https://docs.astral.sh/uv/getting-started/installation/ | `uvx --version` |
| Git | https://git-scm.com/downloads | `git --version` |

## 2. Connect the server

**Claude Desktop**: Settings > Developer > Edit Config, then merge in the contents of
[`claude_desktop_config.example.json`](claude_desktop_config.example.json):

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

Quit Claude Desktop completely and reopen it. "geo-explainer" should appear in the tools list.
If it does not start, replace `"uvx"` with its full path (`where uvx` on Windows, `which uvx` on macOS/Linux).

**Claude Code**:

```bash
claude mcp add geo-explainer -- uvx --from git+https://github.com/ramiz-moktader/geo-explainer-mcp geo-explainer-mcp
```

## 3. Ask for a video

> Read `geo://assets/catalog` and `geo://schema/scene-graph` from the geo-explainer server. Then write and
> render a 30-second short explaining **why the United Kingdom is made of four countries**. Use 4-5 scenes,
> a flag character per country, one curved label per country, one badge, and whoosh/pop sound effects on key
> words. Preview scene 0 first and show me, then call `render_geo_short` with output_dir set to my Videos
> folder and poll `check_render_status` until it is done. Tell me the MP4 path.

What happens: Claude reads your map catalog, writes the narration and scenes, renders a preview still,
starts the full render in the background, checks progress every ~20 seconds, and reports the file path.

## Good to know

- The first render is slow: it installs the Node packages and downloads headless Chrome and the Whisper
  model (a few hundred MB in total). Later renders skip all of that.
- After you push new GeoJSON files to GitHub, restart Claude; if the old catalog still shows, run
  `uvx --refresh --from git+https://github.com/ramiz-moktader/geo-explainer-mcp geo-explainer-mcp --help` once.
- No GPU or a slow laptop? Use the Colab notebook instead: `colab/geo_explainer_colab.ipynb`.
