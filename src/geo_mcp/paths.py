"""Locates the bundled renderer/assets and bootstraps the Node side."""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import __version__

PKG_DIR = Path(__file__).resolve().parent


def cache_dir() -> Path:
    base = os.environ.get("GEO_CACHE_DIR") or os.path.join(
        os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")), "geo-explainer-mcp"
    )
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _bundle_root() -> tuple[Path, bool]:
    """Returns (root containing renderer/ and assets/, is_installed_wheel)."""
    bundled = PKG_DIR / "_bundle"
    if (bundled / "renderer" / "package.json").exists():
        return bundled, True
    repo = PKG_DIR.parent.parent  # src/geo_mcp -> repo root (editable / source checkout)
    return repo, False


def assets_dir() -> Path:
    if os.environ.get("GEO_ASSETS_DIR"):
        return Path(os.environ["GEO_ASSETS_DIR"]).expanduser().resolve()
    return _bundle_root()[0] / "assets"


def renderer_dir() -> Path:
    """A writable copy of the Remotion app (site-packages may be read-only)."""
    if os.environ.get("GEO_RENDERER_DIR"):
        return Path(os.environ["GEO_RENDERER_DIR"]).expanduser().resolve()
    root, installed = _bundle_root()
    src = root / "renderer"
    if not installed:
        return src
    digest = hashlib.sha1()
    for f in sorted(src.rglob("*")):
        if f.is_file():
            digest.update(str(f.relative_to(src)).encode())
            digest.update(f.read_bytes())
    dst = cache_dir() / f"renderer-{__version__}-{digest.hexdigest()[:10]}"
    if not (dst / "package.json").exists():
        tmp = dst.with_name(dst.name + f".tmp{os.getpid()}")
        shutil.copytree(src, tmp, ignore=shutil.ignore_patterns("node_modules", "out", "demo"))
        try:
            tmp.rename(dst)
        except OSError:  # another process won the race
            shutil.rmtree(tmp, ignore_errors=True)
    return dst


def npm_command(name: str = "npm") -> str:
    exe = shutil.which(name) or shutil.which(f"{name}.cmd")
    if not exe:
        raise RuntimeError(
            f"`{name}` was not found on PATH. Install Node.js 18+ (https://nodejs.org) "
            "so the Remotion renderer can run."
        )
    return exe


def ensure_renderer(log=None) -> Path:
    """Runs `npm install` in renderer/ the first time (fresh uvx cache, new clone)."""
    rdir = renderer_dir()
    marker = rdir / "node_modules" / ".geo-install-ok"
    if marker.exists():
        return rdir
    lock = rdir / ".npm-install.lock"
    waited = 0
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if marker.exists():
                return rdir
            if waited > 900 or time.time() - lock.stat().st_mtime > 900:
                lock.unlink(missing_ok=True)  # stale lock
                continue
            time.sleep(2)
            waited += 2
    try:
        if not marker.exists():
            if log:
                log("installing renderer dependencies (npm install, first run only)")
            proc = subprocess.run(
                [npm_command(), "install", "--no-audit", "--no-fund"],
                cwd=rdir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"npm install failed in {rdir}:\n{proc.stdout[-3000:]}")
            marker.parent.mkdir(exist_ok=True)
            marker.write_text("ok")
    finally:
        lock.unlink(missing_ok=True)
    return rdir


if __name__ == "__main__":
    print("assets:", assets_dir())
    print("renderer:", ensure_renderer(lambda m: print(m, file=sys.stderr)))
