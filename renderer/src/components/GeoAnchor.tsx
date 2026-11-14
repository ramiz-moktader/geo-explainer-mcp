import React from "react";
import type { LonLat } from "../types";
import { useMapProjection } from "./MapCanvas";

/**
 * Projects [lon, lat] -> screen pixels every frame (after MapCanvas has
 * positioned the camera) and places its children at that point.
 */
export const GeoAnchor: React.FC<{
  coords: LonLat;
  children: React.ReactNode;
  zIndex?: number;
}> = ({ coords, children, zIndex }) => {
  const { project } = useMapProjection();
  const p = project(coords);
  if (!p) return null;
  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        transform: `translate(${p[0].toFixed(2)}px, ${p[1].toFixed(2)}px)`,
        zIndex,
      }}
    >
      {children}
    </div>
  );
};

/** Hook form, for components that need several projected points. */
export const useProjected = (coords: LonLat | null | undefined) => {
  const { project } = useMapProjection();
  return coords ? project(coords) : null;
};
