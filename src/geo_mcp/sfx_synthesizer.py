"""Synthesises clean fallback Foley / music WAVs so the pipeline needs no audio assets."""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

SR = 44100
DEFAULT_SFX = ("whoosh", "pop", "thud", "clang", "ding")


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    return a * np.exp(-t / decay)


def _write(path: Path, x: np.ndarray, peak: float = 0.85) -> Path:
    x = x / (np.max(np.abs(x)) + 1e-9) * peak
    fade = min(len(x) // 2, int(0.004 * SR))
    x[:fade] *= np.linspace(0, 1, fade)
    x[-fade:] *= np.linspace(1, 0, fade)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return path


def _whoosh() -> np.ndarray:
    n = int(0.55 * SR)
    rng = np.random.default_rng(7)
    noise = rng.standard_normal(n)
    # sweep a one-pole band emphasis upward then down for the "pass-by" feel
    t = np.linspace(0, 1, n)
    cutoff = 300 + 5200 * np.sin(np.pi * t) ** 2
    out = np.zeros(n)
    lp = 0.0
    for i in range(n):
        a = min(1.0, 2 * np.pi * cutoff[i] / SR)
        lp += a * (noise[i] - lp)
        out[i] = lp
    return out * np.sin(np.pi * t) ** 1.5


def _pop() -> np.ndarray:
    n = int(0.16 * SR)
    t = np.arange(n) / SR
    f = 950 * np.exp(-t * 26) + 180
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.002, 0.035)


def _thud() -> np.ndarray:
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 120 * np.exp(-t * 14) + 45
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * _env(n, 0.003, 0.11)
    click = np.random.default_rng(3).standard_normal(n) * _env(n, 0.0005, 0.008) * 0.35
    return body + click


def _clang() -> np.ndarray:
    n = int(0.9 * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for ratio, amp, dec in ((1.0, 1.0, 0.30), (2.76, 0.6, 0.22), (5.4, 0.4, 0.14), (8.93, 0.25, 0.09), (11.3, 0.15, 0.06)):
        out += amp * np.sin(2 * np.pi * 620 * ratio * t) * np.exp(-t / dec)
    hit = np.random.default_rng(5).standard_normal(n) * _env(n, 0.0005, 0.006) * 0.5
    return out + hit


def _ding() -> np.ndarray:
    n = int(1.1 * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for ratio, amp, dec in ((1.0, 1.0, 0.45), (2.0, 0.35, 0.3), (3.01, 0.2, 0.2), (4.2, 0.1, 0.12)):
        out += amp * np.sin(2 * np.pi * 1318.5 * ratio * t) * np.exp(-t / dec)
    return out * np.clip(t / 0.002, 0, 1)


_SFX = {"whoosh": _whoosh, "pop": _pop, "thud": _thud, "clang": _clang, "ding": _ding}


def synthesize_sfx(name: str, out_dir: Path) -> Path:
    if name not in _SFX:
        raise KeyError(f"no synthesiser for sfx '{name}' (have: {', '.join(_SFX)})")
    return _write(Path(out_dir) / f"{name}.wav", _SFX[name]())


def ensure_default_sfx(out_dir: Path) -> list[Path]:
    """Writes any missing default WAVs into out_dir; never overwrites custom files."""
    out = []
    for name in DEFAULT_SFX:
        p = Path(out_dir) / f"{name}.wav"
        out.append(p if p.exists() else synthesize_sfx(name, out_dir))
    return out


_MOODS = {
    "epic": (110.0, (0, 7, 12, 15), 0.5),
    "tense": (98.0, (0, 3, 6, 10), 0.8),
    "calm": (130.81, (0, 4, 7, 11), 0.25),
    "upbeat": (146.83, (0, 4, 7, 9), 1.6),
}


def synthesize_music(mood: str, out_path: Path, seconds: float = 8.0) -> Path:
    """A seamless-looping ambient pad; a stand-in until real music is dropped in assets/music."""
    root, chord, pulse_hz = _MOODS.get(mood.lower(), _MOODS["calm"])
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for i, semi in enumerate(chord):
        f = root * 2 ** (semi / 12)
        f = round(f * seconds) / seconds  # whole cycles -> click-free loop
        for h, amp in ((1, 1.0), (2, 0.3), (3, 0.12)):
            out += amp / (1 + i * 0.3) * np.sin(2 * np.pi * f * h * t + i)
    pulse = round(pulse_hz * seconds) / seconds
    out *= 0.75 + 0.25 * np.sin(2 * np.pi * pulse * t)
    path = Path(out_path)
    x = out / (np.max(np.abs(out)) + 1e-9) * 0.6
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767).astype("<i2").tobytes())
    return path


def synthesize_placeholder_narration(words: list[str], out_path: Path) -> tuple[Path, list[dict]]:
    """Offline stand-in for TTS: one soft blip per word, with exact word timings.

    Only used when GEO_TTS=placeholder (no network / CI). Returns (wav, word_timings).
    """
    timings, chunks, t = [], [], 0.25
    chunks.append(np.zeros(int(t * SR)))
    for i, word in enumerate(words):
        core = "".join(c for c in word if c.isalnum())
        dur = 0.16 + 0.045 * min(len(core), 10)
        n = int(dur * SR)
        tt = np.arange(n) / SR
        f = 170 + 40 * ((i * 7) % 5)
        tone = (np.sin(2 * np.pi * f * tt) + 0.4 * np.sin(2 * np.pi * 2 * f * tt)) * np.sin(np.pi * tt / dur) ** 0.7
        chunks.append(tone * 0.5)
        timings.append({"word": word, "start": round(t, 3), "end": round(t + dur, 3)})
        gap = 0.32 if word[-1:] in ".!?" else 0.14 if word[-1:] in ",;:" else 0.05
        chunks.append(np.zeros(int(gap * SR)))
        t += dur + gap
    chunks.append(np.zeros(int(0.3 * SR)))
    x = np.concatenate(chunks)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((x * 32767 * 0.8).astype("<i2").tobytes())
    return path, timings


if __name__ == "__main__":
    from .paths import assets_dir

    for p in ensure_default_sfx(assets_dir() / "sfx"):
        print(p)
