"""Narration TTS (Edge-TTS default, ElevenLabs optional) + word-level alignment (faster-whisper)."""
from __future__ import annotations

import asyncio
import difflib
import os
import re
import wave
from pathlib import Path
from typing import Callable, Optional

Log = Optional[Callable[[str], None]]

ELEVEN_MODEL = "eleven_turbo_v2_5"
ELEVEN_DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # "George"; override with ELEVENLABS_VOICE_ID


def split_words(text: str) -> list[str]:
    """Script words with their punctuation attached, as they should be captioned."""
    return [w for w in re.split(r"\s+", text.strip()) if re.search(r"\w", w)]


def norm(word: str) -> str:
    return re.sub(r"[^\w]", "", word.lower().replace("’", "'").replace("'", ""), flags=re.UNICODE)


def audio_duration(path: Path) -> float:
    path = Path(path)
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    import av  # shipped with faster-whisper

    with av.open(str(path)) as c:
        if c.duration:
            return float(c.duration) / av.time_base
        s = c.streams.audio[0]
        return float(s.duration * s.time_base)


# ------------------------------------------------------------------------ TTS

async def _edge_tts(text: str, voice: str, out: Path) -> list[dict]:
    import edge_tts

    try:
        comm = edge_tts.Communicate(text, voice, boundary="WordBoundary")
    except TypeError:  # older edge-tts: word boundaries are the default
        comm = edge_tts.Communicate(text, voice)
    boundaries = []
    with open(out, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7
                boundaries.append({"word": chunk["text"], "start": start, "end": start + chunk["duration"] / 1e7})
    return boundaries


def _elevenlabs(text: str, voice: str, out: Path) -> None:
    import httpx

    voice_id = os.environ.get("ELEVENLABS_VOICE_ID") or (voice if "Neural" not in voice and "-" not in voice else ELEVEN_DEFAULT_VOICE)
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": os.environ["ELEVENLABS_API_KEY"], "accept": "audio/mpeg"},
        json={"text": text, "model_id": ELEVEN_MODEL},
        timeout=180,
    )
    r.raise_for_status()
    out.write_bytes(r.content)


def synthesize_narration(text: str, voice: str, out_dir: Path, log: Log = None) -> dict:
    """Returns {"path", "engine", "hints"}; hints are word timings the engine itself reported."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    mode = os.environ.get("GEO_TTS", "").lower()

    if mode == "placeholder":
        from .sfx_synthesizer import synthesize_placeholder_narration

        path, timings = synthesize_placeholder_narration(split_words(text), out_dir / "narration.wav")
        if log:
            log("GEO_TTS=placeholder: using synthetic blips instead of a real voice")
        return {"path": path, "engine": "placeholder", "hints": timings, "exact": True}

    if os.environ.get("ELEVENLABS_API_KEY") and mode != "edge":
        path = out_dir / "narration.mp3"
        _elevenlabs(text, voice, path)
        return {"path": path, "engine": "elevenlabs", "hints": [], "exact": False}

    path = out_dir / "narration.mp3"
    try:
        hints = asyncio.run(_edge_tts(text, voice, path))
    except Exception as e:  # noqa: BLE001 - surface a actionable message
        raise RuntimeError(
            f"Edge-TTS failed ({type(e).__name__}: {e}). Check the network connection and voice name "
            f"'{voice}', set ELEVENLABS_API_KEY, or set GEO_TTS=placeholder for an offline test render."
        ) from e
    if not path.exists() or path.stat().st_size < 1000:
        raise RuntimeError(f"Edge-TTS returned no audio for voice '{voice}'.")
    return {"path": path, "engine": "edge-tts", "hints": hints, "exact": False}


# ------------------------------------------------------------------ alignment

def _decode_16k_mono(path: Path):
    """Decodes audio to the float32 16 kHz mono array Whisper expects.

    Done here, not by faster-whisper, because its own decoder passes arguments
    that some PyAV releases reject (seen on Colab: `metadata_errors`).
    """
    import av
    import numpy as np

    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    chunks = []
    with av.open(str(path)) as container:
        for frame in container.decode(audio=0):
            out = resampler.resample(frame)
            for f in out if isinstance(out, list) else [out]:
                if f is not None:
                    chunks.append(f.to_ndarray().reshape(-1))
    try:  # flush
        for f in resampler.resample(None) or []:
            chunks.append(f.to_ndarray().reshape(-1))
    except Exception:  # noqa: BLE001 - older PyAV cannot flush
        pass
    if not chunks:
        raise RuntimeError(f"no audio decoded from {path}")
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def _whisper_words(audio: Path, prompt: str) -> list[dict]:
    from faster_whisper import WhisperModel

    try:
        samples = _decode_16k_mono(audio)
    except Exception:  # noqa: BLE001 - let faster-whisper try its own decoder
        samples = str(audio)

    device, compute = "cpu", "int8"
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            device, compute = "cuda", "float16"
    except Exception:  # noqa: BLE001
        pass
    device = os.environ.get("GEO_WHISPER_DEVICE", device)
    compute = os.environ.get("GEO_WHISPER_COMPUTE", "float16" if device == "cuda" else "int8")
    name = os.environ.get("GEO_WHISPER_MODEL", "base")

    def run(dev: str, ctype: str) -> list[dict]:
        model = WhisperModel(name, device=dev, compute_type=ctype)
        segments, _ = model.transcribe(
            samples,
            word_timestamps=True,
            initial_prompt=prompt[:800],
            vad_filter=False,
            condition_on_previous_text=False,
        )
        words = []
        for seg in segments:  # lazy generator: GPU library errors surface here
            for w in seg.words or []:
                if w.word.strip():
                    words.append({"word": w.word.strip(), "start": float(w.start), "end": float(w.end)})
        return words

    if device != "cpu":
        try:
            return run(device, compute)
        except Exception:  # noqa: BLE001 - e.g. missing cuDNN/cuBLAS; a short clip is fine on CPU
            pass
    return run("cpu", "int8")


def estimate_timings(script_words: list[str], duration: float) -> list[dict]:
    """Last-resort timings: spread words over the audio by length, pausing at punctuation."""
    if not script_words:
        return []
    weights = []
    for w in script_words:
        base = 1.0 + 0.45 * len(norm(w))
        pause = 2.6 if w[-1:] in ".!?" else 1.2 if w[-1:] in ",;:—" else 0.0
        weights.append((base, pause))
    total = sum(b + p for b, p in weights)
    lead = min(0.15, duration * 0.02)
    scale = max(0.01, duration - lead - 0.1) / total
    out, t = [], lead
    for w, (b, p) in zip(script_words, weights):
        out.append({"word": w, "start": round(t, 3), "end": round(t + b * scale, 3)})
        t += (b + p) * scale
    return out


def map_script_to_heard(script_words: list[str], heard: list[dict], duration: float) -> list[dict]:
    """Carries recogniser timestamps onto the *script's* words (captions must show the script).

    Words the recogniser got wrong or merged are interpolated between their matched neighbours.
    """
    if not heard:
        return estimate_timings(script_words, duration)
    a = [norm(w) for w in script_words]
    b = [norm(h["word"]) for h in heard]
    times: list[Optional[tuple[float, float]]] = [None] * len(a)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                times[i1 + k] = (heard[j1 + k]["start"], heard[j1 + k]["end"])
        elif tag == "replace" and (j2 - j1) > 0:
            # share the heard span across the differing script words, by length
            t0, t1 = heard[j1]["start"], heard[j2 - 1]["end"]
            lens = [max(1, len(x)) for x in a[i1:i2]]
            acc, tot = 0, sum(lens)
            for k, ln in enumerate(lens):
                s = t0 + (t1 - t0) * acc / tot
                acc += ln
                times[i1 + k] = (s, t0 + (t1 - t0) * acc / tot)
    # fill gaps ("delete" runs) between known neighbours
    i = 0
    while i < len(times):
        if times[i] is not None:
            i += 1
            continue
        j = i
        while j < len(times) and times[j] is None:
            j += 1
        left = times[i - 1][1] if i > 0 else 0.0
        right = times[j][0] if j < len(times) else duration
        right = max(right, left + 0.05 * (j - i))
        step = (right - left) / (j - i)
        for k in range(i, j):
            times[k] = (left + step * (k - i), left + step * (k - i + 1))
        i = j
    out, prev = [], 0.0
    for w, (s, e) in zip(script_words, times):  # type: ignore[misc]
        s = max(s, prev)
        e = max(e, s + 0.04)
        out.append({"word": w, "start": round(s, 3), "end": round(e, 3)})
        prev = s
    return out


def align_words(audio: Path, narration: str, tts: Optional[dict] = None, log: Log = None) -> dict:
    """Returns {"word_timings": [...], "method": ..., "duration": sec, "warnings": [...]}."""
    script = split_words(narration)
    duration = audio_duration(audio)
    warnings: list[str] = []
    tts = tts or {}

    if tts.get("exact") and len(tts.get("hints", [])) == len(script):
        return {"word_timings": tts["hints"], "method": "synthetic-exact", "duration": duration, "warnings": warnings}

    if os.environ.get("GEO_ALIGN", "").lower() != "estimate":
        try:
            heard = _whisper_words(audio, narration)
            if heard:
                return {
                    "word_timings": map_script_to_heard(script, heard, duration),
                    "method": "faster-whisper",
                    "duration": duration,
                    "warnings": warnings,
                }
            warnings.append("faster-whisper returned no words")
        except Exception as e:  # noqa: BLE001 - model download / runtime failures
            warnings.append(f"faster-whisper unavailable ({type(e).__name__}: {str(e)[:160]})")
            if log:
                log(warnings[-1])

    if tts.get("hints"):
        warnings.append("word timings taken from the TTS engine's own word boundaries")
        return {
            "word_timings": map_script_to_heard(script, tts["hints"], duration),
            "method": "tts-boundaries",
            "duration": duration,
            "warnings": warnings,
        }

    warnings.append("word timings were ESTIMATED from word lengths; sync will be approximate")
    return {"word_timings": estimate_timings(script, duration), "method": "estimated", "duration": duration, "warnings": warnings}
