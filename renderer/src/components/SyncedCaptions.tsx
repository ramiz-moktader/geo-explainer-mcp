import React, { useMemo } from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import type { WordTiming } from "../types";
import { popIn } from "../utils/interpolation";

interface Phrase {
  words: WordTiming[];
  start: number;
  end: number;
}

const MAX_WORDS = 3;
const MAX_CHARS = 17; // one line at this font size

/** Groups word timings into 2-4 word phrases, breaking on punctuation/pauses. */
export const buildPhrases = (timings: WordTiming[]): Phrase[] => {
  const phrases: Phrase[] = [];
  let cur: WordTiming[] = [];
  const flush = () => {
    if (cur.length) {
      phrases.push({ words: cur, start: cur[0].start, end: cur[cur.length - 1].end });
      cur = [];
    }
  };
  timings.forEach((w, i) => {
    cur.push(w);
    const next = timings[i + 1];
    const chars = cur.reduce((n, x) => n + x.word.length + 1, 0);
    const punct = /[.!?,;:—]$/.test(w.word.trim());
    const pause = next ? next.start - w.end > 0.45 : true;
    const nextTooLong = next ? chars + next.word.length > MAX_CHARS : false;
    if ((punct && cur.length >= 2) || pause || cur.length >= MAX_WORDS || nextTooLong || /[.!?]$/.test(w.word.trim())) {
      flush();
    }
  });
  flush();
  return phrases;
};

export const SyncedCaptions: React.FC<{ timings: WordTiming[] }> = ({ timings }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const phrases = useMemo(() => buildPhrases(timings), [timings]);
  const t = frame / fps;

  let active: Phrase | null = null;
  for (let i = 0; i < phrases.length; i++) {
    const p = phrases[i];
    const until = phrases[i + 1] ? Math.min(phrases[i + 1].start, p.end + 0.6) : p.end + 0.5;
    if (t >= p.start - 0.03 && t < until) active = p;
  }
  if (!active) return null;

  const s = popIn(frame, Math.round((active.start - 0.03) * fps), fps, 13);
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        width,
        top: height * 0.78,
        transform: `translateY(-50%) scale(${0.7 + 0.3 * s})`,
        display: "flex",
        justifyContent: "center",
        flexWrap: "wrap",
        gap: "0 40px",
        padding: "0 70px",
        boxSizing: "border-box",
        fontFamily: "'Arial Black', 'DejaVu Sans', Impact, sans-serif",
        fontWeight: 900,
        fontSize: 76,
        lineHeight: 1.12,
        textTransform: "uppercase",
        textAlign: "center",
      }}
    >
      {active.words.map((w, i) => {
        const on = t >= w.start - 0.02 && t < w.end + 0.06;
        const said = t >= w.end + 0.06;
        return (
          <span
            key={i}
            style={{
              color: on ? "#ffe21f" : "#ffffff",
              opacity: said || on ? 1 : 0.92,
              WebkitTextStroke: "14px #000",
              paintOrder: "stroke fill",
              display: "inline-block",
              transform: on ? "scale(1.06) translateY(-4px)" : "scale(1)",
              textShadow: "0 8px 0 rgba(0,0,0,0.55)",
            }}
          >
            {w.word.trim()}
          </span>
        );
      })}
    </div>
  );
};
