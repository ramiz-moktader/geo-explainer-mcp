"""Auto-discovers GeoJSON regions, flags, props and SFX at runtime."""
from __future__ import annotations

import base64
import json
import mimetypes
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator, Optional

from .paths import assets_dir, cache_dir, renderer_dir
from .sfx_synthesizer import DEFAULT_SFX, ensure_default_sfx

# Property keys inspected on every feature, most specific first.
ID_KEYS = ("ISO_3166_2", "iso_3166_2", "ISO_A3", "iso_a3", "ADM0_A3", "adm0_a3", "id", "ID")
NAME_KEYS = ("NAME", "name", "NAME_EN", "name_en", "NAME_1", "ADMIN", "admin", "shapeName")
_BAD = {"", "-99", "-1", "none", "null"}


def _clean(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return None if s.lower() in _BAD else s


def _coords(geom: dict) -> Iterator[tuple[float, float]]:
    def walk(c):
        if c and isinstance(c[0], (int, float)):
            yield float(c[0]), float(c[1])
        else:
            for x in c or []:
                yield from walk(x)

    if not geom:
        return
    if geom.get("type") == "GeometryCollection":
        for g in geom.get("geometries", []):
            yield from _coords(g)
    else:
        yield from walk(geom.get("coordinates"))


def _features(doc: Any) -> list[dict]:
    if not isinstance(doc, dict):
        return []
    t = doc.get("type")
    if t == "FeatureCollection":
        return [f for f in doc.get("features", []) if isinstance(f, dict)]
    if t == "Feature":
        return [doc]
    if t in ("Polygon", "MultiPolygon"):
        return [{"type": "Feature", "properties": {}, "geometry": doc}]
    return []


def _describe(feature: dict, index: int) -> Optional[dict]:
    geom = feature.get("geometry") or {}
    if geom.get("type") not in ("Polygon", "MultiPolygon", "GeometryCollection"):
        return None
    props = feature.get("properties") or {}
    ids = [_clean(props.get(k)) for k in ID_KEYS] + [_clean(feature.get("id"))]
    names = [_clean(props.get(k)) for k in NAME_KEYS]
    aliases: list[str] = []
    for v in ids + names:
        if v and v not in aliases:
            aliases.append(v)
    pts = list(_coords(geom))
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    bbox = [round(min(xs), 4), round(min(ys), 4), round(max(xs), 4), round(max(ys), 4)]
    return {
        "id": aliases[0] if aliases else f"feature-{index}",
        "name": next((n for n in names if n), aliases[0] if aliases else f"feature-{index}"),
        "aliases": aliases,
        "centroid": [round((bbox[0] + bbox[2]) / 2, 4), round((bbox[1] + bbox[3]) / 2, 4)],
        "bbox": bbox,
        "_index": index,
    }


def geojson_dir() -> Path:
    return assets_dir() / "geojson"


def _geojson_files() -> list[Path]:
    d = geojson_dir()
    if not d.is_dir():
        return []
    files = sorted(p for p in d.iterdir() if p.suffix.lower() in (".geojson", ".json"))
    user = [p for p in files if not p.name.startswith("_starter")]
    return files if not user else user + [p for p in files if p.name.startswith("_starter")]


@lru_cache(maxsize=64)
def _load(path_str: str, mtime: float) -> tuple[dict, list[dict]]:
    doc = json.loads(Path(path_str).read_text(encoding="utf-8"))
    feats = _features(doc)
    described = [d for i, f in enumerate(feats) if (d := _describe(f, i))]
    return {"features": feats}, described


def _index(path: Path) -> tuple[list[dict], list[dict]]:
    doc, described = _load(str(path), path.stat().st_mtime)
    return doc["features"], described


def _norm(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def resolve_feature(geojson_file: str, feature_id: str) -> tuple[Path, dict]:
    """Finds a feature by id/name (case-insensitive); returns (file path, GeoJSON Feature)."""
    files = _geojson_files()
    want_file = _norm(Path(geojson_file).stem)
    ordered = [p for p in files if p.name == geojson_file or _norm(p.stem) == want_file]
    ordered += [p for p in files if p not in ordered]  # fall back to every other file
    want = _norm(feature_id)
    for path in ordered:
        try:
            feats, described = _index(path)
        except (OSError, ValueError):
            continue
        for d in described:
            if any(_norm(a) == want for a in d["aliases"] + [d["id"]]):
                f = feats[d["_index"]]
                return path, {
                    "type": "Feature",
                    "properties": {"id": d["id"], "name": d["name"]},
                    "geometry": f["geometry"],
                }
    known = [d["id"] for p in files for d in _safe_described(p)][:40]
    raise LookupError(
        f"feature '{feature_id}' not found in '{geojson_file}' or any other GeoJSON. "
        f"Known ids include: {', '.join(known) or '(none)'}"
    )


def _safe_described(path: Path) -> list[dict]:
    try:
        return _index(path)[1]
    except (OSError, ValueError):
        return []


# ------------------------------------------------------------- images / audio

def _stems(folder: Path, exts: tuple[str, ...]) -> dict[str, Path]:
    if not folder.is_dir():
        return {}
    return {p.stem.lower(): p for p in sorted(folder.iterdir()) if p.suffix.lower() in exts}


def _data_uri(path: Path) -> str:
    mime = "image/svg+xml" if path.suffix.lower() == ".svg" else (mimetypes.guess_type(path.name)[0] or "image/png")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def _flag_icons_dir() -> Path:
    return renderer_dir() / "node_modules" / "flag-icons" / "flags" / "4x3"


def flag_data_uri(code: str) -> Optional[str]:
    """Custom assets/flags/<code>.svg|png first, then the flag-icons package; None -> generated flag."""
    key = code.strip().lower()
    custom = _stems(assets_dir() / "flags", (".svg", ".png", ".jpg", ".jpeg", ".webp"))
    for k in (key, key.replace("_", "-")):
        if k in custom:
            return _data_uri(custom[k])
    builtin = _flag_icons_dir() / f"{key.replace('_', '-')}.svg"
    return _data_uri(builtin) if builtin.exists() else None


def prop_data_uri(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    props = _stems(assets_dir() / "props", (".svg", ".png", ".webp"))
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    path = props.get(key) or props.get(key.replace("_", "-"))
    return _data_uri(path) if path else None


def sfx_path(name: str) -> Path:
    """Custom WAV/MP3 in assets/sfx wins; otherwise a synthesised default."""
    key = name.strip().lower()
    custom = _stems(assets_dir() / "sfx", (".wav", ".mp3", ".ogg"))
    if key in custom:
        return custom[key]
    if key in DEFAULT_SFX:
        fallback = cache_dir() / "sfx"
        ensure_default_sfx(fallback)
        return fallback / f"{key}.wav"
    raise LookupError(f"sfx '{name}' not found. Available: {', '.join(sorted(set(custom) | set(DEFAULT_SFX)))}")


def music_path(mood: str) -> Optional[Path]:
    return _stems(assets_dir() / "music", (".wav", ".mp3", ".ogg")).get(mood.strip().lower())


def build_catalog() -> dict:
    geo = []
    for path in _geojson_files():
        try:
            described = _safe_described(path)
            json.loads(path.read_text(encoding="utf-8"))
            err = None if described else "no polygon features found"
        except (OSError, ValueError) as e:
            described, err = [], f"could not parse: {e}"
        entry = {
            "file": path.name,
            "feature_count": len(described),
            "features": [{k: v for k, v in d.items() if not k.startswith("_")} for d in described],
        }
        if err:
            entry["error"] = err
        geo.append(entry)
    custom_flags = sorted(_stems(assets_dir() / "flags", (".svg", ".png", ".jpg", ".jpeg", ".webp")))
    fi = _flag_icons_dir()
    builtin_flags = sorted(p.stem for p in fi.glob("*.svg")) if fi.is_dir() else []
    props = sorted(_stems(assets_dir() / "props", (".svg", ".png", ".webp")))
    sfx = sorted(set(_stems(assets_dir() / "sfx", (".wav", ".mp3", ".ogg"))) | set(DEFAULT_SFX))
    return {
        "assets_dir": str(assets_dir()),
        "geojson": geo,
        "flags": {
            "custom": custom_flags,
            "builtin": builtin_flags
            or "ISO 3166-1 alpha-2 codes plus gb-eng/gb-sct/gb-wls/gb-nir (listed after the first npm install)",
            "note": "Unknown codes still render, as a generated placeholder flag.",
        },
        "props": props,
        "hats": [p for p in props if p in ("crown", "helmet")] or props,
        "badge_icons": props,
        "sfx": sfx,
        "music": sorted(_stems(assets_dir() / "music", (".wav", ".mp3", ".ogg"))) + ["epic", "calm", "tense", "upbeat"],
        "expressions": ["neutral", "angry", "shocked", "smug", "sad"],
        "actions": ["idle", "bounce", "slash", "shake", "grow"],
    }


if __name__ == "__main__":
    print(json.dumps(build_catalog(), indent=2)[:4000])
