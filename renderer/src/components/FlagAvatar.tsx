import React from "react";
import { Img, interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import type { CompiledCharacter, Expression } from "../types";
import { popIn } from "../utils/interpolation";

const W = 190;
const H = 136;
const R = 30;
const INK = "#14161c";

// Deterministic fallback flag when no SVG/PNG is available for a code.
const hashHue = (s: string, salt: number) => {
  let h = salt * 97;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 360;
  return h;
};

const GeneratedFlag: React.FC<{ code: string }> = ({ code }) => (
  <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
    {[0, 1, 2].map((i) => (
      <rect
        key={i}
        x={0}
        y={(H / 3) * i}
        width={W}
        height={H / 3 + 1}
        fill={`hsl(${hashHue(code, i + 1)}, 62%, ${i === 1 ? 88 : 46}%)`}
      />
    ))}
    <text
      x={W / 2}
      y={H - 12}
      textAnchor="middle"
      fontFamily="Arial Black, DejaVu Sans, sans-serif"
      fontWeight={900}
      fontSize={20}
      fill={INK}
      opacity={0.55}
    >
      {code.toUpperCase()}
    </text>
  </svg>
);

const Face: React.FC<{ expression: Expression; blink: number }> = ({
  expression,
  blink,
}) => {
  const cx = W / 2;
  const ey = 56;
  const dx = 34;
  const big = expression === "shocked";
  const ry = (big ? 22 : 17) * (expression === "smug" ? 0.62 : 1) * blink;
  const rx = big ? 18 : 15;
  const pupil = big ? 5 : 8;
  const pupilDy = expression === "sad" ? 4 : expression === "smug" ? 1 : 0;
  const pupilDx = expression === "smug" ? 4 : 0;
  const brow = (side: -1 | 1) => {
    const x = cx + side * dx;
    const tilt =
      expression === "angry"
        ? -side * 9
        : expression === "sad"
          ? side * 7
          : expression === "smug"
            ? side === 1
              ? -6
              : 3
            : 0;
    const lift = expression === "shocked" ? -12 : expression === "smug" && side === 1 ? -7 : 0;
    const y = ey - 26 + lift;
    return (
      <line
        key={side}
        x1={x - 17}
        y1={y - tilt}
        x2={x + 17}
        y2={y + tilt}
        stroke={INK}
        strokeWidth={7}
        strokeLinecap="round"
      />
    );
  };
  const mouthY = 104;
  const mouth = {
    neutral: <path d={`M ${cx - 16} ${mouthY} Q ${cx} ${mouthY + 9} ${cx + 16} ${mouthY}`} />,
    angry: <path d={`M ${cx - 18} ${mouthY + 6} Q ${cx} ${mouthY - 8} ${cx + 18} ${mouthY + 6}`} />,
    sad: <path d={`M ${cx - 16} ${mouthY + 6} Q ${cx} ${mouthY - 6} ${cx + 16} ${mouthY + 6}`} />,
    smug: <path d={`M ${cx - 14} ${mouthY + 2} Q ${cx + 6} ${mouthY + 10} ${cx + 20} ${mouthY - 6}`} />,
    shocked: <ellipse cx={cx} cy={mouthY + 2} rx={10} ry={13} fill={INK} />,
  }[expression];
  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      style={{ position: "absolute", left: 0, top: 0, overflow: "visible" }}
    >
      {([-1, 1] as const).map((side) => (
        <g key={side}>
          <ellipse
            cx={cx + side * dx}
            cy={ey}
            rx={rx}
            ry={Math.max(1.5, ry)}
            fill="#fff"
            stroke={INK}
            strokeWidth={4}
          />
          {blink > 0.4 && (
            <circle cx={cx + side * dx + pupilDx} cy={ey + pupilDy} r={pupil} fill={INK} />
          )}
        </g>
      ))}
      {expression !== "neutral" && [brow(-1), brow(1)]}
      <g fill="none" stroke={INK} strokeWidth={6} strokeLinecap="round">
        {mouth}
      </g>
      {expression === "sad" && (
        <path
          d={`M ${cx - dx - 12} ${ey + 20} q -7 12 0 17 q 7 -5 0 -17`}
          fill="#6ec6ff"
          stroke={INK}
          strokeWidth={2.5}
        />
      )}
    </svg>
  );
};

export const FlagAvatar: React.FC<{ character: CompiledCharacter }> = ({ character }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame - character.start_frame;
  if (t < 0) return null;
  const sec = t / fps;
  const enter = popIn(frame, character.start_frame, fps);
  const action = character.action;

  let dx = 0;
  let dy = Math.sin(sec * 2.4) * 4; // idle bob
  let scale = enter;
  let tilt = Math.sin(sec * 1.7) * 1.5;
  let armR = -18 + Math.sin(sec * 2.4) * 5; // degrees, right arm
  const armL = 18 - Math.sin(sec * 2.4) * 5;

  if (action === "bounce") {
    dy = -Math.abs(Math.sin(sec * Math.PI * 2.2)) * 34;
    scale *= 1 + Math.sin(sec * Math.PI * 4.4) * 0.03;
  } else if (action === "shake") {
    const decay = interpolate(sec, [0, 2.5], [1, 0.35], { extrapolateRight: "clamp" });
    dx = Math.sin(sec * 46) * 9 * decay;
    tilt = Math.sin(sec * 38) * 4 * decay;
  } else if (action === "grow") {
    scale *= interpolate(popIn(frame, character.start_frame + Math.round(fps / 6), fps, 9), [0, 1], [1, 1.35]);
  } else if (action === "slash") {
    const cyc = (sec % 1.1) / 1.1;
    const swing = interpolate(cyc, [0, 0.25, 0.42, 1], [-70, -95, 55, -70]);
    armR = swing;
    tilt = interpolate(cyc, [0, 0.25, 0.42, 1], [0, -5, 7, 0]);
  }

  const blinkPhase = (sec + (character.id.length % 5) * 0.37) % 3.1;
  const blink = blinkPhase > 2.95 ? 0.1 : 1;

  const arm = (side: -1 | 1, deg: number, child?: React.ReactNode) => (
    <div
      style={{
        position: "absolute",
        left: side === 1 ? W - 8 : 8,
        top: H * 0.62,
        width: 0,
        height: 0,
        transform: `rotate(${side * deg}deg)`,
      }}
    >
      <svg
        width={120}
        height={40}
        viewBox="-60 -20 120 40"
        style={{ position: "absolute", left: -60, top: -20, overflow: "visible" }}
      >
        <line x1={0} y1={0} x2={side * 50} y2={0} stroke={INK} strokeWidth={9} strokeLinecap="round" />
        <circle cx={side * 54} cy={0} r={10} fill="#fff" stroke={INK} strokeWidth={5} />
      </svg>
      {child && (
        <div style={{ position: "absolute", left: side * 54, top: 0, width: 0, height: 0 }}>
          {child}
        </div>
      )}
    </div>
  );

  const prop = character.prop_src ? (
    <Img
      src={character.prop_src}
      style={{
        position: "absolute",
        width: 92,
        height: 92,
        left: -18,
        top: -86,
        transform: "rotate(20deg)",
        filter: "drop-shadow(0 4px 4px rgba(0,0,0,0.5))",
      }}
    />
  ) : null;

  return (
    <div
      style={{
        position: "absolute",
        left: -W / 2 + dx,
        top: -H / 2 + dy,
        width: W,
        height: H,
        transform: `scale(${scale}) rotate(${tilt}deg)`,
        transformOrigin: "50% 60%",
        filter: "drop-shadow(0 12px 10px rgba(0,0,0,0.55))",
      }}
    >
      {arm(-1, armL)}
      <div
        style={{
          position: "absolute",
          inset: 0,
          borderRadius: R,
          overflow: "hidden",
          border: `7px solid ${INK}`,
          background: "#ddd",
          boxSizing: "border-box",
        }}
      >
        {character.flag_src ? (
          <Img
            src={character.flag_src}
            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          />
        ) : (
          <GeneratedFlag code={character.flag_code} />
        )}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(160deg, rgba(255,255,255,0.28) 0%, rgba(255,255,255,0) 45%, rgba(0,0,0,0.18) 100%)",
          }}
        />
      </div>
      <Face expression={character.expression} blink={blink} />
      {character.hat_src && (
        <Img
          src={character.hat_src}
          style={{
            position: "absolute",
            width: 120,
            height: 120,
            left: W / 2 - 60,
            top: -92,
            filter: "drop-shadow(0 3px 3px rgba(0,0,0,0.45))",
          }}
        />
      )}
      {arm(1, armR, prop)}
    </div>
  );
};
