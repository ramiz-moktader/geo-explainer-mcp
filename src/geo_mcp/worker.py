"""Background render orchestrator: TTS -> align -> compile -> Remotion render.

Run as a detached process by the MCP server (`python -m geo_mcp.worker <job_dir>`),
or directly from a shell: `geo-explainer-render script.json --out ./renders`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Callable, Optional

from . import FPS
from .audio_aligner import align_words, estimate_timings, split_words, synthesize_narration
from .models import SceneGraph
from .paths import cache_dir, ensure_renderer, npm_command
from .timeline_compiler import compile_timeline, slugify, write_timeline

Status = Callable[..., None]
COMPOSITION = "GeoExplainer"


def jobs_dir() -> Path:
    p = cache_dir() / "jobs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_status(job_dir: Path, **fields) -> dict:
    path = Path(job_dir) / "status.json"
    current = {}
    if path.exists():
        try:
            current = json.loads(path.read_text())
        except ValueError:
            current = {}
    current.update(fields)
    current["updated_at"] = time.time()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(current, indent=2))
    os.replace(tmp, path)
    return current


def _render_env() -> dict:
    env = dict(os.environ)
    env.setdefault("NODE_OPTIONS", "--max-old-space-size=4096")
    return env


def _remotion(args: list[str], cwd: Path, on_line: Optional[Callable[[str], None]] = None) -> str:
    cmd = [npm_command("npx"), "--no-install", "remotion", *args]
    proc = subprocess.Popen(
        cmd, cwd=cwd, env=_render_env(), stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace",
    )
    tail: list[str] = []
    assert proc.stdout
    for line in proc.stdout:
        line = line.rstrip()
        if not line:
            continue
        tail.append(line)
        del tail[:-60]
        if on_line:
            on_line(line)
    if proc.wait() != 0:
        raise RuntimeError("Remotion failed:\n" + "\n".join(tail[-25:]))
    return "\n".join(tail)


def _extra_flags() -> list[str]:
    flags = []
    if os.environ.get("GEO_RENDER_CONCURRENCY"):
        flags.append(f"--concurrency={os.environ['GEO_RENDER_CONCURRENCY']}")
    if os.environ.get("GEO_RENDER_SCALE"):
        flags.append(f"--scale={os.environ['GEO_RENDER_SCALE']}")
    return flags


def run_pipeline(graph: SceneGraph, job_dir: Path, output_dir: Path, status: Status) -> Path:
    job_dir, output_dir = Path(job_dir), Path(output_dir).expanduser().resolve()
    public = job_dir / "public"
    public.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    log = lambda m: status(message=m)  # noqa: E731

    status(status="tts", progress=2, message="synthesising narration")
    tts = synthesize_narration(graph.narration, graph.voice, public, log)

    status(status="aligning", progress=10, message=f"aligning words ({tts['engine']} audio)")
    aligned = align_words(tts["path"], graph.narration, tts, log)
    warnings += aligned["warnings"]

    status(status="compiling", progress=18, message=f"compiling timeline ({aligned['method']} timings)")
    timeline = compile_timeline(graph, aligned["word_timings"], tts["path"], aligned["duration"], public, warnings)
    timeline.update(tts_engine=tts["engine"], alignment_method=aligned["method"])
    props = write_timeline(timeline, job_dir / "compiled_timeline.json")

    status(status="rendering", progress=20, message="preparing renderer", warnings=warnings,
           total_frames=timeline["total_frames"])
    rdir = ensure_renderer(log)
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{slugify(graph.title)}-{job_dir.name[:8]}.mp4"
    total = timeline["total_frames"]
    last = {"p": -1}

    waits: list[int] = []
    stats = {"timeouts": 0, "reported": 0}

    def on_line(line: str) -> None:
        t = re.search(r"geo-timing (\d+) (\d+) ([01])", line)
        if t:  # per-frame "map ready" wait, logged by MapCanvas.tsx
            waits.append(int(t.group(2)))
            stats["timeouts"] += int(t.group(3))
            if len(waits) - stats["reported"] >= 40:
                recent = waits[stats["reported"]:]
                stats["reported"] = len(waits)
                status(message=f"map wait per frame: avg {sum(recent) / len(recent) / 1000:.2f}s, "
                               f"max {max(recent) / 1000:.1f}s, tile timeouts so far: {stats['timeouts']}")
            return
        m = re.search(r"(Rendered|Encoded)\s+(\d+)/(\d+)", line)
        if not m:
            return
        done, n = int(m.group(2)), max(1, int(m.group(3)))
        frac = done / n
        pct = 22 + (62 * frac if m.group(1) == "Rendered" else 62 + 15 * frac)
        pct = int(min(99, pct))
        if pct != last["p"]:
            last["p"] = pct
            status(progress=pct, message=f"{m.group(1).lower()} {done}/{n} frames")

    _remotion(
        ["render", "src/index.ts", COMPOSITION, str(out), f"--props={props}", f"--public-dir={public}",
         "--log=verbose", *_extra_flags()],  # verbose: needed to receive the page's geo-timing lines
        rdir, on_line,
    )
    if waits:
        warnings.append(
            f"render timing: map wait avg {sum(waits) / len(waits) / 1000:.2f}s per frame over {len(waits)} frames; "
            f"{stats['timeouts']} frames hit the tile timeout"
        )
    if not out.exists() or out.stat().st_size < 10_000:
        raise RuntimeError(f"renderer finished but {out} is missing or empty")
    status(status="done", progress=100, message="render complete", output_path=str(out),
           duration_sec=round(total / FPS, 2), warnings=warnings)
    return out


def render_preview(graph: SceneGraph, scene_index: int, out_png: Path) -> Path:
    """Single still of one scene (no TTS): word timings are estimated from the script."""
    if not 0 <= scene_index < len(graph.scenes):
        raise ValueError(f"scene_index {scene_index} out of range (0..{len(graph.scenes) - 1})")
    work = cache_dir() / "previews" / uuid.uuid4().hex[:10]
    public = work / "public"
    public.mkdir(parents=True, exist_ok=True)
    words = split_words(graph.narration)
    duration = len(words) / 2.7 + 0.6
    timeline = compile_timeline(graph, estimate_timings(words, duration), None, duration, public, [])
    scene = timeline["scenes"][scene_index]
    # late in the scene, so every triggered element is on screen and the camera has settled
    frame = max(scene["start_frame"], scene["end_frame"] - max(1, round(12 * FPS / 60)))
    props = write_timeline(timeline, work / "compiled_timeline.json")
    out_png = Path(out_png).expanduser().resolve()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    _remotion(
        ["still", "src/index.ts", COMPOSITION, str(out_png), f"--props={props}", f"--public-dir={public}",
         f"--frame={frame}", *[f for f in _extra_flags() if f.startswith("--scale")]],
        ensure_renderer(),
    )
    return out_png


def run_job(job_dir: Path) -> int:
    job_dir = Path(job_dir)
    job = json.loads((job_dir / "job.json").read_text())
    status = lambda **f: write_status(job_dir, **f)  # noqa: E731
    status(pid=os.getpid())
    try:
        graph = SceneGraph.model_validate(job["scene_graph"])
        run_pipeline(graph, job_dir, Path(job["output_dir"]), status)
        return 0
    except Exception as e:  # noqa: BLE001 - everything is reported through status.json
        (job_dir / "error.log").write_text(traceback.format_exc())
        status(status="error", error=f"{type(e).__name__}: {e}"[:4000], message="render failed")
        return 1


def create_job(graph: SceneGraph, output_dir: str) -> tuple[str, Path]:
    job_id = uuid.uuid4().hex[:12]
    job_dir = jobs_dir() / job_id
    job_dir.mkdir(parents=True)
    (job_dir / "job.json").write_text(
        json.dumps({"scene_graph": graph.model_dump(), "output_dir": str(Path(output_dir).expanduser().resolve())})
    )
    write_status(job_dir, job_id=job_id, status="queued", progress=0, message="queued",
                 output_path=None, error=None, warnings=[], created_at=time.time())
    return job_id, job_dir


def spawn_job(job_dir: Path) -> int:
    """Detached worker so the MCP stdio call returns immediately."""
    log = open(Path(job_dir) / "worker.log", "ab")
    kwargs: dict = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        [sys.executable, "-m", "geo_mcp.worker", "--job-dir", str(job_dir)],
        stdin=subprocess.DEVNULL, stdout=log, stderr=log, close_fds=True, **kwargs,
    )
    write_status(job_dir, pid=proc.pid)
    return proc.pid


def cli(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Render a SceneGraph JSON file to an MP4.")
    ap.add_argument("script", nargs="?", help="path to a SceneGraph .json (omit to render the built-in example)")
    ap.add_argument("--out", default="./renders", help="output directory")
    ap.add_argument("--job-dir", help=argparse.SUPPRESS)
    ap.add_argument("--preview", type=int, metavar="SCENE", help="render a single PNG of this scene index instead")
    args = ap.parse_args(argv)

    if args.job_dir:
        return run_job(Path(args.job_dir))

    if args.script:
        graph = SceneGraph.model_validate_json(Path(args.script).read_text(encoding="utf-8"))
    else:
        from .models import example_scene_graph

        graph = SceneGraph.model_validate(example_scene_graph())

    if args.preview is not None:
        print(render_preview(graph, args.preview, Path(args.out) / f"preview-scene{args.preview}.png"))
        return 0

    job_id, job_dir = create_job(graph, args.out)

    def status(**f):
        s = write_status(job_dir, **f)
        print(f"[{s.get('status', '?'):>9}] {s.get('progress', 0):>3}%  {s.get('message', '')}", file=sys.stderr, flush=True)

    try:
        out = run_pipeline(graph, job_dir, Path(args.out), status)
    except Exception as e:  # noqa: BLE001
        status(status="error", error=str(e), message="render failed")
        print(f"error: {e}", file=sys.stderr)
        return 1
    for w in json.loads((job_dir / "status.json").read_text()).get("warnings", []):
        print(f"warning: {w}", file=sys.stderr)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(cli())
