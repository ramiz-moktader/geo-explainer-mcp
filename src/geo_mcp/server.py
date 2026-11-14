"""FastMCP server: catalog + schema resources and the render tools."""
from __future__ import annotations

import argparse
import json
import os
import time
import uuid
from pathlib import Path

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from . import FPS, HEIGHT, WIDTH, __version__
from .asset_catalog import build_catalog, resolve_feature, sfx_path
from .models import SceneGraph, example_scene_graph
from .paths import cache_dir
from .worker import create_job, jobs_dir, render_preview, spawn_job

INSTRUCTIONS = f"""\
Generates {WIDTH}x{HEIGHT} {FPS}fps animated map explainer shorts.
Workflow: (1) read geo://assets/catalog for region ids, centroids, props, flags and SFX;
(2) read geo://schema/scene-graph for the SceneGraph schema and a working example;
(3) write a SceneGraph - every start_word / trigger_word must be a word or short phrase that
appears verbatim in `narration`, and scenes must follow narration order;
(4) optionally call preview_scene_frame to check a scene's framing;
(5) call render_geo_short, then poll check_render_status every ~20s until status is 'done' or 'error'.
"""

mcp = FastMCP("geo-explainer", instructions=INSTRUCTIONS, version=__version__)


@mcp.resource("geo://assets/catalog", mime_type="application/json")
def assets_catalog() -> str:
    """Every discovered GeoJSON file with its feature ids/names/centroids, plus props, flags and SFX."""
    return json.dumps(build_catalog(), indent=2)


@mcp.resource("geo://schema/scene-graph", mime_type="application/json")
def scene_graph_schema() -> str:
    """JSON Schema for SceneGraph plus a complete working example."""
    return json.dumps(
        {
            "json_schema": SceneGraph.model_json_schema(),
            "example": example_scene_graph(),
            "notes": [
                "Scene 0 starts at frame 0; every later scene starts when its start_word is spoken.",
                "Elements live for the duration of their scene. Repeat a polygon in the next scene to keep it on screen.",
                "A polygon with transition_to_color changes colour at trigger_word; otherwise trigger_word is when it appears.",
                "Captions occupy the band around y=78%; keep badges above y=70.",
                "Aim for 2-4 short sentences per scene and 20-60 seconds of narration overall.",
            ],
        },
        indent=2,
    )


def _preflight(graph: SceneGraph) -> None:
    """Fail fast, in the tool call, on references the worker could never resolve."""
    problems = []
    for scene in graph.scenes:
        for p in scene.polygons:
            try:
                resolve_feature(p.geojson_file, p.feature_id)
            except LookupError as e:
                problems.append(f"scene '{scene.scene_id}': {e}")
        for s in scene.sfx:
            try:
                sfx_path(s.sound)
            except LookupError as e:
                problems.append(f"scene '{scene.scene_id}': {e}")
    if problems:
        raise ToolError("SceneGraph references unknown assets:\n- " + "\n- ".join(problems))


@mcp.tool
def render_geo_short(scene_graph: SceneGraph, output_dir: str = "./renders") -> dict:
    """Validate a SceneGraph and start rendering it to an MP4 in the background.

    Returns {"job_id", "status": "queued"} immediately; poll check_render_status(job_id).
    A 30-second short typically takes several minutes to render.
    """
    _preflight(scene_graph)
    job_id, job_dir = create_job(scene_graph, output_dir)
    spawn_job(job_dir)
    return {"job_id": job_id, "status": "queued", "output_dir": str(Path(output_dir).expanduser().resolve())}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OSError):
        return True
    return True


@mcp.tool
def check_render_status(job_id: str) -> dict:
    """Current stage (queued, tts, aligning, compiling, rendering, done, error), progress %, and the .mp4 path when done."""
    path = jobs_dir() / job_id / "status.json"
    if not job_id.isalnum() or not path.exists():
        return {"job_id": job_id, "status": "error", "error": "unknown job_id"}
    s = json.loads(path.read_text())
    if s.get("status") not in ("done", "error") and s.get("pid") and not _alive(int(s["pid"])):
        time.sleep(0.5)  # the worker may have just written its final status
        s = json.loads(path.read_text())
        if s.get("status") not in ("done", "error"):
            s.update(status="error", error="render worker exited unexpectedly; see " + str(path.parent / "worker.log"))
    keep = ("job_id", "status", "progress", "message", "output_path", "duration_sec", "warnings", "error")
    return {k: s.get(k) for k in keep if s.get(k) not in (None, [])} | {"job_id": job_id}


@mcp.tool
def preview_scene_frame(scene_graph: SceneGraph, scene_index: int = 0) -> str:
    """Render one PNG still of a scene (no voiceover needed) and return its file path.

    Use it to check camera framing, polygon colours and character/label placement before a full render.
    """
    _preflight(scene_graph)
    out = cache_dir() / "previews" / f"scene{scene_index}-{uuid.uuid4().hex[:8]}.png"
    return str(render_preview(scene_graph, scene_index, out))


def main() -> None:
    ap = argparse.ArgumentParser(prog="geo-explainer-mcp", description="Geo-explainer MCP server")
    ap.add_argument("--http", action="store_true", help="serve over streamable HTTP instead of stdio")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8000)
    args = ap.parse_args()
    if args.http:
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
