"""Local caching proxy for satellite tiles.

Headless Chrome fetching tiles straight from the internet is the slow, unreliable part of a
render: one stalled request keeps MapLibre from going idle and every frame then waits for the
safety timeout. Instead the renderer is pointed at this proxy, which

* answers from a disk cache (shared by every browser tab and every later render),
* fetches a missing tile from the upstream server with a short timeout and retries, and
* never hangs: if the upstream fails it returns a transparent tile and counts the failure.

`prefetch()` warms the cache for all camera positions of a timeline before rendering starts.
"""
from __future__ import annotations

import base64
import hashlib
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Iterable, Optional

from . import HEIGHT, WIDTH
from .paths import cache_dir

ESRI_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
MAPTILER_URL = "https://api.maptiler.com/tiles/satellite-v2/{z}/{x}/{y}.jpg?key={key}"
MAX_TILE_ZOOM = 17
BLANK_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def upstream_template() -> str:
    """GEO_TILE_URL (any XYZ template with {z}/{x}/{y}) > MapTiler key > ESRI World Imagery."""
    if os.environ.get("GEO_TILE_URL"):
        return os.environ["GEO_TILE_URL"]
    if os.environ.get("MAPTILER_API_KEY"):
        return MAPTILER_URL.replace("{key}", os.environ["MAPTILER_API_KEY"])
    return ESRI_URL


def _sniff(data: bytes) -> Optional[str]:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


class TileProxy:
    def __init__(self, template: Optional[str] = None, timeout: float = 6.0, retries: int = 2):
        self.template = template or upstream_template()
        key = hashlib.sha1(self.template.split("?")[0].encode()).hexdigest()[:10]
        self.dir = cache_dir() / "tiles" / key
        self.timeout, self.retries = timeout, retries
        self.stats = {"cached": 0, "downloaded": 0, "failed": 0}
        self._lock = threading.Lock()
        self._inflight: dict[tuple, threading.Event] = {}
        self._client = None
        self._server: Optional[ThreadingHTTPServer] = None
        self.port = 0

    # ------------------------------------------------------------ fetching
    def _http(self):
        if self._client is None:
            import httpx

            self._client = httpx.Client(
                timeout=self.timeout, follow_redirects=True,
                limits=httpx.Limits(max_connections=24, max_keepalive_connections=24),
                headers={"User-Agent": "geo-explainer-mcp tile cache"},
            )
        return self._client

    def _path(self, z: int, x: int, y: int) -> Path:
        return self.dir / str(z) / str(x) / f"{y}.tile"

    def _count(self, key: str) -> None:
        with self._lock:
            self.stats[key] += 1

    def get(self, z: int, x: int, y: int) -> tuple[bytes, str, bool]:
        """Returns (bytes, mime, ok). Never raises and never blocks longer than timeout * retries."""
        n = 1 << z
        if not (0 <= z <= 22 and 0 <= y < n):
            return BLANK_PNG, "image/png", False
        x %= n
        path = self._path(z, x, y)
        if path.exists():
            data = path.read_bytes()
            self._count("cached")
            return data, _sniff(data) or "image/png", True

        key = (z, x, y)
        with self._lock:  # collapse concurrent requests for the same tile into one download
            waiter = self._inflight.get(key)
            if waiter is None:
                self._inflight[key] = threading.Event()
        if waiter is not None:
            waiter.wait(self.timeout * self.retries + 2)
            if path.exists():
                data = path.read_bytes()
                self._count("cached")
                return data, _sniff(data) or "image/png", True
            return BLANK_PNG, "image/png", False
        try:
            url = self.template.format(z=z, x=x, y=y)
            for _ in range(self.retries):
                try:
                    r = self._http().get(url)
                except Exception:  # noqa: BLE001 - network errors: retry, then blank
                    continue
                if r.status_code == 200 and _sniff(r.content):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = path.with_suffix(f".tmp{threading.get_ident()}")
                    tmp.write_bytes(r.content)
                    os.replace(tmp, path)
                    self._count("downloaded")
                    return r.content, _sniff(r.content) or "image/png", True
                if r.status_code in (400, 403, 404):
                    break  # the server will not have this tile; do not retry
            self._count("failed")
            return BLANK_PNG, "image/png", False
        finally:
            with self._lock:
                self._inflight.pop(key).set()

    # -------------------------------------------------------------- server
    def start(self) -> str:
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):  # noqa: N802
                try:
                    z, x, y = (int(p) for p in self.path.split("?")[0].strip("/").split("/")[:3])
                    data, mime, _ = proxy.get(z, x, y)
                    code = 200
                except Exception:  # noqa: BLE001
                    data, mime, code = BLANK_PNG, "image/png", 200
                self.send_response(code)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):  # keep stdout clean (stdio MCP transport)
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.port}/{{z}}/{{x}}/{{y}}"

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
        if self._client:
            self._client.close()

    def summary(self) -> str:
        s = self.stats
        return f"map tiles: {s['downloaded']} downloaded, {s['cached']} from cache, {s['failed']} failed"


# ---------------------------------------------------------------- prefetch

def _camera_samples(scenes: list[dict]) -> Iterable[tuple[float, float, float, float]]:
    """(lon, lat, zoom, pitch) along the camera path: every scene target plus points in transit."""
    prev = None
    for sc in scenes:
        cam = sc["camera"]
        lon, lat = cam["center"]
        cur = (lon, lat, cam["zoom"], cam.get("pitch", 0))
        if prev is not None:
            dist = math.hypot(cur[0] - prev[0], cur[1] - prev[1])
            hop = min(1.2, dist / 25)  # mirrors cameraAtFrame() in interpolation.ts
            for i in range(1, 12):
                t = i / 12
                yield (
                    prev[0] + (cur[0] - prev[0]) * t,
                    prev[1] + (cur[1] - prev[1]) * t,
                    prev[2] + (cur[2] - prev[2]) * t - hop * math.sin(math.pi * t),
                    max(prev[3], cur[3]),
                )
        yield cur
        prev = cur


def tiles_for_timeline(timeline: dict, limit: int = 6000) -> list[tuple[int, int, int]]:
    """Over-approximates the raster tiles MapLibre will request (256 px tiles -> zoom + 1)."""
    tiles: dict[tuple[int, int, int], None] = {}
    half = math.hypot(WIDTH / 2, HEIGHT / 2)
    for lon, lat, zoom, pitch in _camera_samples(timeline["scenes"]):
        world = 512 * 2**zoom
        cx = (lon + 180) / 360 * world
        s = math.sin(math.radians(max(-85.05, min(85.05, lat))))
        cy = (0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)) * world
        radius = half * (1.05 + pitch / 35)  # a tilted view sees further
        for tz in {min(MAX_TILE_ZOOM, max(0, math.floor(zoom + 1)))}:
            n = 1 << tz
            px = world / n
            x0, x1 = math.floor((cx - radius) / px), math.floor((cx + radius) / px)
            y0, y1 = max(0, math.floor((cy - radius) / px)), min(n - 1, math.floor((cy + radius) / px))
            if (x1 - x0 + 1) * (y1 - y0 + 1) > 900:
                continue  # implausible for one view; leave it to on-demand fetching
            for x in range(x0, x1 + 1):
                for y in range(y0, y1 + 1):
                    tiles[(tz, x % n, y)] = None
    return list(tiles)[:limit]


def prefetch(proxy: TileProxy, timeline: dict, log: Optional[Callable[[str], None]] = None, workers: int = 16) -> int:
    tiles = tiles_for_timeline(timeline)
    if log:
        log(f"downloading {len(tiles)} map tiles (cached ones are skipped)")
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, _ in enumerate(pool.map(lambda t: proxy.get(*t), tiles), 1):
            done = i
            if log and i % 250 == 0:
                log(f"map tiles {i}/{len(tiles)}")
    return done
