import React from "react";
import {
  AbsoluteFill,
  Audio,
  Sequence,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { BadgeCluster } from "./components/BadgeCluster";
import { CurvedMapLabel } from "./components/CurvedMapLabel";
import { FlagAvatar } from "./components/FlagAvatar";
import { GeoAnchor } from "./components/GeoAnchor";
import { MapCanvas } from "./components/MapCanvas";
import { SyncedCaptions } from "./components/SyncedCaptions";
import type { Timeline } from "./types";
import { popIn, sceneIndexAt } from "./utils/interpolation";

const MUSIC_DUCKED = 0.08;
const MUSIC_OPEN = 0.3;

const TitleCard: React.FC<{ title: string }> = ({ title }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = popIn(frame, Math.round(fps / 15), fps, 12);
  const out = interpolate(frame, [fps * 2.6, fps * 3], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  if (out <= 0) return null;
  return (
    <div
      style={{
        position: "absolute",
        top: 150,
        left: 60,
        right: 60,
        textAlign: "center",
        opacity: out,
        transform: `scale(${0.8 + 0.2 * s})`,
        fontFamily: "'Arial Black', 'DejaVu Sans', Impact, sans-serif",
        fontWeight: 900,
        fontSize: 64,
        lineHeight: 1.1,
        color: "#fff",
        WebkitTextStroke: "12px #000",
        paintOrder: "stroke fill",
      }}
    >
      {title}
    </div>
  );
};

export const GeoExplainer: React.FC<Timeline> = (timeline) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const si = sceneIndexAt(timeline.scenes, frame);
  const scene = timeline.scenes[si];

  return (
    <AbsoluteFill style={{ backgroundColor: "#061a2e" }}>
      <MapCanvas timeline={timeline}>
        {scene.labels.map((l, i) => (
          <CurvedMapLabel key={`${si}-l${i}`} uid={`${si}-${i}`} label={l} />
        ))}
        {scene.characters.map((c) => (
          <GeoAnchor key={`${si}-${c.id}`} coords={c.coords}>
            <FlagAvatar character={c} />
          </GeoAnchor>
        ))}
      </MapCanvas>

      {/* soft vignette so captions and badges read over bright terrain */}
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(0,0,0,0.38) 0%, rgba(0,0,0,0) 16%, rgba(0,0,0,0) 62%, rgba(0,0,0,0.5) 100%)",
          pointerEvents: "none",
        }}
      />

      <BadgeCluster badges={scene.badges} />
      {timeline.show_title !== false && <TitleCard title={timeline.title} />}
      <SyncedCaptions timings={timeline.word_timings} />

      {timeline.audio_src && <Audio src={staticFile(timeline.audio_src)} />}
      {timeline.sfx_events.map((e, i) => (
        <Sequence key={`sfx-${i}`} from={e.frame} layout="none">
          <Audio src={staticFile(e.src)} volume={e.volume} />
        </Sequence>
      ))}
      {timeline.music_src && (
        <Audio
          loop
          src={staticFile(timeline.music_src)}
          volume={(f) =>
            // ducked under the narration, opens up once it ends
            interpolate(
              f,
              [timeline.narration_end_frame, timeline.narration_end_frame + fps * 0.6],
              [MUSIC_DUCKED, MUSIC_OPEN],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
            )
          }
        />
      )}
    </AbsoluteFill>
  );
};
