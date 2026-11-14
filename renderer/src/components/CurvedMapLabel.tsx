import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import type { CompiledLabel } from "../types";
import { fade, popIn } from "../utils/interpolation";
import { useProjected } from "./GeoAnchor";

const FONT = "'Arial Black', 'DejaVu Sans', Impact, sans-serif";

export const CurvedMapLabel: React.FC<{ label: CompiledLabel; uid: string }> = ({
  label,
  uid,
}) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const anchor = useProjected(label.coords);
  const target = useProjected(label.pointer_to ?? null);
  if (frame < label.start_frame || !anchor) return null;

  const callout = label.style === "callout";
  const text = callout ? label.text : label.text.toUpperCase();
  const fontSize = callout ? 46 : 58;
  const spacing = callout ? 1 : 7;
  const half = Math.max(90, (text.length * (fontSize * 0.66 + spacing)) / 2 + 20);
  const curve = Math.max(-1, Math.min(1, label.curve));
  const sag = -curve * half * 0.55; // positive curve arches upward
  const [x, y] = anchor;
  const pathId = `label-path-${uid}`;
  const d = `M ${x - half} ${y - sag / 2} Q ${x} ${y + sag * 1.5 - sag / 2} ${x + half} ${y - sag / 2}`;
  const appear = popIn(frame, label.start_frame, fps, 14);
  const opacity = fade(frame, label.start_frame, 8);
  const fill = callout ? "#ffe45c" : "#ffffff";

  let pointer: React.ReactNode = null;
  if (target) {
    const [tx, ty] = target;
    const sx = x;
    const sy = y + (ty > y ? fontSize * 0.45 : -fontSize * 0.75);
    const len = Math.hypot(tx - sx, ty - sy);
    if (len > 30) {
      const ux = (tx - sx) / len;
      const uy = (ty - sy) / len;
      const grow = Math.min(1, appear);
      const ex = sx + ux * (len - 14) * grow;
      const ey = sy + uy * (len - 14) * grow;
      const a = 18;
      const head = `M ${ex + ux * 14} ${ey + uy * 14} L ${ex - uy * a * 0.6} ${ey + ux * a * 0.6} L ${ex + uy * a * 0.6} ${ey - ux * a * 0.6} Z`;
      pointer = (
        <g>
          <line x1={sx} y1={sy} x2={ex} y2={ey} stroke="#000" strokeWidth={13} strokeLinecap="round" />
          <path d={head} fill={fill} stroke="#000" strokeWidth={6} strokeLinejoin="round" />
          <line x1={sx} y1={sy} x2={ex} y2={ey} stroke={fill} strokeWidth={6} strokeLinecap="round" />
        </g>
      );
    }
  }

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      style={{ position: "absolute", left: 0, top: 0, overflow: "visible", opacity }}
    >
      <defs>
        <path id={pathId} d={d} />
      </defs>
      {pointer}
      <g
        style={{
          transformOrigin: `${x}px ${y}px`,
          transform: `scale(${0.6 + 0.4 * appear})`,
        }}
      >
        <text
          fontFamily={FONT}
          fontWeight={900}
          fontSize={fontSize}
          letterSpacing={spacing}
          fill={fill}
          stroke="#000"
          strokeWidth={callout ? 11 : 13}
          strokeLinejoin="round"
          style={{ paintOrder: "stroke fill" }}
          textAnchor="middle"
        >
          <textPath href={`#${pathId}`} startOffset="50%">
            {text}
          </textPath>
        </text>
      </g>
    </svg>
  );
};
