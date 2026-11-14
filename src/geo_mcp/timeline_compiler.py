"""Turns a SceneGraph + word timings into a frame-indexed timeline for the renderer."""
from __future__ import annotations

import difflib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Optional

from . import FPS, HEIGHT, WIDTH
from .asset_catalog import flag_data_uri, music_path, prop_data_uri, resolve_feature, sfx_path
from .audio_aligner import norm, split_words
from .models import SceneGraph

TAIL_SEC = 0.7


def to_frame(sec: float) -> int:
    return int(round(sec * FPS))


def _f(frames_at_60: int) -> int:
    """Scales a frame count authored at 60 fps to the active frame rate."""
    return max(1, round(frames_at_60 * FPS / 60))


class WordIndex:
    """Fuzzy, order-aware lookup of words/phrases in the narration's word timings."""

    def __init__(self, word_timings: list[dict]):
        self.timings = word_timings
        self.tokens = [norm(w["word"]) for w in word_timings]

    def _match_at(self, i: int, phrase: list[str], cutoff: float) -> float:
        if i + len(phrase) > len(self.tokens):
            return 0.0
        scores = []
        for k, p in enumerate(phrase):
            t = self.tokens[i + k]
            s = 1.0 if t == p else difflib.SequenceMatcher(a=t, b=p).ratio()
            if s < cutoff:
                return 0.0
            scores.append(s)
        return sum(scores) / len(scores)

    def find(self, phrase: str, lo: int = 0, hi: Optional[int] = None) -> Optional[int]:
        """Index of the first word of `phrase` in [lo, hi); exact first, then fuzzy."""
        toks = [norm(w) for w in split_words(phrase)] or [norm(phrase)]
        toks = [t for t in toks if t]
        if not toks:
            return None
        hi = len(self.tokens) if hi is None else min(hi, len(self.tokens))
        for cutoff in (1.0, 0.74):
            best, best_i = 0.0, None
            for i in range(max(lo, 0), hi):
                s = self._match_at(i, toks, cutoff)
                if s >= 1.0:
                    return i
                if s > best:
                    best, best_i = s, i
            if best_i is not None:
                return best_i
        # multi-word phrase with a wrong word in it: anchor on its first word
        return self.find(toks[0], lo, hi) if len(toks) > 1 else None

    def frame(self, idx: int) -> int:
        return to_frame(self.timings[idx]["start"])


def compile_timeline(
    graph: SceneGraph,
    word_timings: list[dict],
    audio_path: Optional[Path],
    audio_duration: float,
    public_dir: Path,
    warnings: Optional[list[str]] = None,
) -> dict:
    """Builds the renderer props and stages audio into `public_dir` (Remotion's --public-dir)."""
    warnings = warnings if warnings is not None else []
    public_dir = Path(public_dir)
    public_dir.mkdir(parents=True, exist_ok=True)
    index = WordIndex(word_timings)
    last_word_end = word_timings[-1]["end"] if word_timings else 0.0
    total_frames = max(to_frame(max(audio_duration, last_word_end) + TAIL_SEC), FPS)

    # ---- scene boundaries, strictly in narration order
    starts: list[int] = []  # word index at which each scene begins
    cursor = 0
    for si, scene in enumerate(graph.scenes):
        if si == 0:
            starts.append(0)
            continue
        idx = index.find(scene.start_word, lo=cursor + 1)
        if idx is None:
            idx = min(cursor + 1, max(len(word_timings) - 1, 0))
            warnings.append(
                f"scene '{scene.scene_id}': start_word '{scene.start_word}' not found after the previous scene; "
                "starting it right after the previous scene"
            )
        starts.append(idx)
        cursor = idx
    start_frames = [0] + [index.frame(i) if word_timings else 0 for i in starts[1:]]
    for i in range(1, len(start_frames)):  # keep strictly increasing
        start_frames[i] = max(start_frames[i], start_frames[i - 1] + 1)

    scenes_out, sfx_events = [], []
    for si, scene in enumerate(graph.scenes):
        s_frame = start_frames[si]
        e_frame = start_frames[si + 1] if si + 1 < len(graph.scenes) else total_frames
        lo = starts[si]
        hi = starts[si + 1] if si + 1 < len(graph.scenes) else len(word_timings)

        def trigger(word: Optional[str], what: str) -> Optional[int]:
            """Frame for a trigger word inside this scene's stretch of narration."""
            if not word:
                return None
            idx = index.find(word, lo, hi)
            if idx is None:
                idx = index.find(word, lo)  # later in the narration
                if idx is not None and index.frame(idx) >= e_frame:
                    warnings.append(
                        f"scene '{scene.scene_id}': trigger_word '{word}' for {what} is spoken after this scene ends; "
                        "firing at the end of the scene"
                    )
                    return max(s_frame, e_frame - _f(20))
            if idx is None:
                warnings.append(
                    f"scene '{scene.scene_id}': trigger_word '{word}' for {what} not found in the narration; using scene start"
                )
                return None
            return min(max(index.frame(idx), s_frame), max(s_frame, e_frame - 1))

        polygons = []
        for p in scene.polygons:
            try:
                path, feature = resolve_feature(p.geojson_file, p.feature_id)
            except LookupError as e:
                raise ValueError(f"scene '{scene.scene_id}': {e}") from e
            tf = trigger(p.trigger_word, f"polygon {p.feature_id}")
            has_transition = bool(p.transition_to_color)
            polygons.append(
                {
                    **p.model_dump(),
                    "geojson_file": path.name,
                    "geojson_path": str(path),
                    "feature": feature,
                    "start_frame": s_frame if has_transition or tf is None else tf,
                    "trigger_frame": (tf if tf is not None else s_frame + _f(30)) if has_transition else None,
                }
            )

        characters = []
        for c in scene.characters:
            tf = trigger(c.trigger_word, f"character {c.id}")
            flag = flag_data_uri(c.flag_code)
            if flag is None:
                warnings.append(f"flag '{c.flag_code}' not found; character '{c.id}' uses a generated placeholder flag")
            for kind, name in (("hat", c.hat), ("prop", c.prop)):
                if name and prop_data_uri(name) is None:
                    warnings.append(f"{kind} '{name}' not found in assets/props; character '{c.id}' renders without it")
            characters.append(
                {
                    **c.model_dump(),
                    "start_frame": tf if tf is not None else s_frame + _f(6),
                    "flag_src": flag,
                    "hat_src": prop_data_uri(c.hat),
                    "prop_src": prop_data_uri(c.prop),
                }
            )

        labels = [
            {**l.model_dump(), "start_frame": (t if (t := trigger(l.trigger_word, f"label {l.text}")) is not None else s_frame + _f(10))}
            for l in scene.labels
        ]
        badges = [
            {
                **b.model_dump(),
                "start_frame": (t if (t := trigger(b.trigger_word, f"badge {b.label}")) is not None else s_frame + _f(14)),
                "icon_src": prop_data_uri(b.icon),
            }
            for b in scene.badges
        ]

        for s in scene.sfx:
            try:
                src = sfx_path(s.sound)
            except LookupError as e:
                warnings.append(f"scene '{scene.scene_id}': {e}; skipped")
                continue
            dst = public_dir / "sfx" / src.name
            dst.parent.mkdir(exist_ok=True)
            if not dst.exists():
                shutil.copyfile(src, dst)
            tf = trigger(s.trigger_word, f"sfx {s.sound}")
            sfx_events.append(
                {"sound": s.sound, "src": f"sfx/{src.name}", "frame": tf if tf is not None else s_frame, "volume": s.volume}
            )

        scenes_out.append(
            {
                "scene_id": scene.scene_id,
                "start_word": scene.start_word,
                "start_frame": s_frame,
                "end_frame": e_frame,
                "camera": scene.camera.model_dump(),
                "polygons": polygons,
                "characters": characters,
                "labels": labels,
                "badges": badges,
            }
        )

    audio_src = None
    if audio_path:
        audio_src = f"narration{Path(audio_path).suffix}"
        if Path(audio_path).resolve() != (public_dir / audio_src).resolve():
            shutil.copyfile(audio_path, public_dir / audio_src)

    music_src = None
    if graph.music_mood:
        found = music_path(graph.music_mood)
        if found:
            music_src = f"music{found.suffix}"
            shutil.copyfile(found, public_dir / music_src)
        else:
            from .sfx_synthesizer import synthesize_music

            synthesize_music(graph.music_mood, public_dir / "music.wav")
            music_src = "music.wav"

    basemap = os.environ.get("GEO_BASEMAP", "satellite").lower()
    return {
        "title": graph.title,
        "fps": FPS,
        "width": WIDTH,
        "height": HEIGHT,
        "total_frames": total_frames,
        "audio_path": str(audio_path) if audio_path else None,
        "audio_src": audio_src,
        "music_src": music_src,
        "narration_end_frame": to_frame(last_word_end) if word_timings else total_frames,
        "word_timings": word_timings,
        "scenes": scenes_out,
        "sfx_events": sorted(sfx_events, key=lambda e: e["frame"]),
        "basemap": "plain" if basemap == "plain" else "satellite",
        "maptiler_key": os.environ.get("MAPTILER_API_KEY") or None,
        "show_title": os.environ.get("GEO_SHOW_TITLE", "1") != "0",
        "warnings": warnings,
    }


def write_timeline(timeline: dict, path: Path) -> Path:
    path = Path(path)
    path.write_text(json.dumps(timeline), encoding="utf-8")
    return path


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "geo-short"
