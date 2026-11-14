import React from "react";
import { Img, useCurrentFrame, useVideoConfig } from "remotion";
import type { CompiledBadge } from "../types";
import { popIn } from "../utils/interpolation";

export const BadgeCluster: React.FC<{ badges: CompiledBadge[] }> = ({ badges }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  return (
    <>
      {badges.map((b, i) => {
        if (frame < b.start_frame) return null;
        const s = popIn(frame, b.start_frame, fps, 9);
        const wobble = Math.sin((frame - b.start_frame) / fps * 2 + i) * 2;
        return (
          <div
            key={`${b.icon}-${i}`}
            style={{
              position: "absolute",
              left: (b.screen_pos[0] / 100) * width,
              top: (b.screen_pos[1] / 100) * height,
              transform: `translate(-50%, -50%) scale(${s}) rotate(${wobble}deg)`,
              display: "flex",
              alignItems: "center",
              gap: 14,
              padding: "12px 26px 12px 14px",
              borderRadius: 60,
              background: "rgba(255,255,255,0.96)",
              border: "6px solid #14161c",
              boxShadow: "0 10px 0 rgba(0,0,0,0.35)",
              fontFamily: "'Arial Black', 'DejaVu Sans', sans-serif",
              fontWeight: 900,
              fontSize: 38,
              color: "#14161c",
              whiteSpace: "nowrap",
            }}
          >
            <div
              style={{
                width: 76,
                height: 76,
                borderRadius: 40,
                background: "#ffd84a",
                border: "5px solid #14161c",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 40,
              }}
            >
              {b.icon_src ? (
                <Img src={b.icon_src} style={{ width: 58, height: 58 }} />
              ) : (
                "★"
              )}
            </div>
            {b.label}
          </div>
        );
      })}
    </>
  );
};
