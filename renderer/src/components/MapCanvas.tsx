import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import React, {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  continueRender,
  delayRender,
  interpolate,
  interpolateColors,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { feature as topoFeature, mesh as topoMesh } from "topojson-client";
import land50 from "world-atlas/countries-50m.json";
import type { CompiledPolygon, LonLat, Timeline } from "../types";
import { cameraAtFrame, sceneIndexAt } from "../utils/interpolation";

type Projector = (lonLat: LonLat) => [number, number] | null;

interface MapCtx {
  project: Projector;
  ready: boolean;
}

const Ctx = createContext<MapCtx>({ project: () => null, ready: false });
export const useMapProjection = () => useContext(Ctx);

const IDLE_TIMEOUT_MS = 8000;
// authored at 60 fps; scaled to the composition frame rate
const FADE_FRAMES_60 = 14;
const BLEND_FRAMES_60 = 24;

const ESRI =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";

const polyKey = (p: CompiledPolygon) => `${p.geojson_file}::${p.feature_id}`;
const finalColor = (p: CompiledPolygon) => p.transition_to_color ?? p.fill_color;

// Rings that cross the antimeridian (Russia, Fiji, ...) would otherwise be
// filled the long way round the globe; unwrap them into 0..360 longitudes.
const unwrapAntimeridian = (fc: any) => {
  const fixPoly = (rings: number[][][]) => {
    const lons = rings[0].map((p) => p[0]);
    if (Math.min(...lons) < -90 && Math.max(...lons) > 90) {
      return rings.map((r) => r.map(([x, y]) => [x < 0 ? x + 360 : x, y]));
    }
    return rings;
  };
  for (const f of fc.features) {
    const g = f.geometry;
    if (!g) continue;
    if (g.type === "Polygon") g.coordinates = fixPoly(g.coordinates);
    if (g.type === "MultiPolygon") g.coordinates = g.coordinates.map(fixPoly);
  }
  return fc;
};

const buildStyle = (timeline: Timeline): maplibregl.StyleSpecification => {
  const topo = land50 as any;
  // Per-country polygons tessellate cleanly; the merged `land` object does not.
  const land = unwrapAntimeridian(topoFeature(topo, topo.objects.countries));
  const borders = topoMesh(topo, topo.objects.countries, (a: any, b: any) => a !== b);
  const satellite = timeline.basemap === "satellite";
  const sources: maplibregl.StyleSpecification["sources"] = {
    land: { type: "geojson", data: land as any },
    borders: { type: "geojson", data: borders as any },
  };
  const layers: maplibregl.LayerSpecification[] = [
    {
      id: "bg",
      type: "background",
      paint: { "background-color": satellite ? "#061a2e" : "#0d3554" },
    },
  ];
  if (satellite) {
    sources.sat = {
      type: "raster",
      tiles: [
        // tile_url is the local caching proxy started by worker.py (fast, never stalls)
        timeline.tile_url
          ? timeline.tile_url
          : timeline.maptiler_key
            ? `https://api.maptiler.com/tiles/satellite-v2/{z}/{x}/{y}.jpg?key=${timeline.maptiler_key}`
            : ESRI,
      ],
      tileSize: 256,
      maxzoom: 17,
      attribution: timeline.maptiler_key ? "© MapTiler" : "Imagery © Esri",
    };
    layers.push({
      id: "sat",
      type: "raster",
      source: "sat",
      paint: { "raster-fade-duration": 0, "raster-saturation": 0.15 },
    });
  } else {
    layers.push({
      id: "land",
      type: "fill",
      source: "land",
      paint: { "fill-color": "#3f6b4a", "fill-antialias": true },
    });
  }
  layers.push({
    id: "borders",
    type: "line",
    source: "borders",
    paint: {
      "line-color": satellite ? "rgba(255,255,255,0.55)" : "rgba(20,40,30,0.55)",
      "line-width": 1.5,
    },
  });
  return { version: 8, sources, layers };
};

interface PolyLayer {
  id: string;
  poly: CompiledPolygon;
  sceneEnd: number;
  continues: boolean; // same feature was on screen in the previous scene
  fromColor: string;
  persists: boolean; // stays visible at scene end (same feature continues, or last scene)
}

const collectPolyLayers = (timeline: Timeline): PolyLayer[] => {
  const out: PolyLayer[] = [];
  timeline.scenes.forEach((scene, si) => {
    const prev = si > 0 ? timeline.scenes[si - 1] : null;
    const next = timeline.scenes[si + 1] ?? null;
    scene.polygons.forEach((poly, pi) => {
      const before = prev?.polygons.find((q) => polyKey(q) === polyKey(poly));
      out.push({
        id: `poly-${si}-${pi}`,
        poly,
        sceneEnd: scene.end_frame,
        continues: Boolean(before),
        fromColor: before ? finalColor(before) : poly.fill_color,
        // no fade-out on the final scene: the video should end on a full frame
        persists: !next || next.polygons.some((q) => polyKey(q) === polyKey(poly)),
      });
    });
  });
  return out;
};

const polyPaintAt = (l: PolyLayer, frame: number, fps: number) => {
  const { poly } = l;
  const k = fps / 60;
  const FADE_FRAMES = Math.max(1, Math.round(FADE_FRAMES_60 * k));
  const BLEND_FRAMES = Math.max(1, Math.round(BLEND_FRAMES_60 * k));
  const start = poly.start_frame;
  if (frame < start || frame >= l.sceneEnd) return { color: poly.fill_color, alpha: 0 };
  let alpha = l.continues
    ? 1
    : interpolate(frame, [start, start + FADE_FRAMES], [0, 1], {
        extrapolateRight: "clamp",
      });
  if (!l.persists) {
    alpha *= interpolate(frame, [l.sceneEnd - Math.max(1, Math.round(8 * k)), l.sceneEnd], [1, 0], {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    });
  }
  let color = l.continues
    ? interpolateColors(frame, [start, start + BLEND_FRAMES], [l.fromColor, poly.fill_color])
    : poly.fill_color;
  if (poly.transition_to_color && poly.trigger_frame !== null && frame >= poly.trigger_frame) {
    color = interpolateColors(
      frame,
      [poly.trigger_frame, poly.trigger_frame + BLEND_FRAMES],
      [poly.fill_color, poly.transition_to_color],
    );
  }
  return { color, alpha };
};

export const MapCanvas: React.FC<{
  timeline: Timeline;
  children?: React.ReactNode;
}> = ({ timeline, children }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const paintCache = useRef<Record<string, string | number>>({});
  const [ready, setReady] = useState(false);
  const [, setProjectedFrame] = useState(-1);

  const polyLayers = useMemo(() => collectPolyLayers(timeline), [timeline]);

  // --- create the map exactly once per browser tab ------------------------
  useEffect(() => {
    const handle = delayRender("maplibre: initial load", {
      timeoutInMilliseconds: 120000,
    });
    const cam0 = cameraAtFrame(timeline.scenes, 0, fps);
    const map = new maplibregl.Map({
      container: container.current!,
      style: buildStyle(timeline),
      center: cam0.center,
      zoom: cam0.zoom,
      pitch: cam0.pitch,
      bearing: cam0.bearing,
      interactive: false,
      attributionControl: false,
      fadeDuration: 0,
      maxPitch: 75,
      // Follows Remotion's --scale, times map_detail: software WebGL cost scales with map pixels,
      // so drawing the map a little below output resolution is the cheapest speed-up there is.
      pixelRatio: (window.devicePixelRatio || 1) * Math.min(1, Math.max(0.3, timeline.map_detail ?? 1)),
      // MSAA off: in software WebGL it cost ~40% of render time; lines are anti-aliased in-shader anyway
      canvasContextAttributes: { preserveDrawingBuffer: true, antialias: false },
    });
    mapRef.current = map;
    map.on("error", (e) => {
      // Tile failures (offline, rate limits) must not abort the render.
      console.warn("maplibre error:", e?.error?.message ?? e);
    });
    map.once("load", () => {
      for (const l of polyLayers) {
        map.addSource(l.id, { type: "geojson", data: l.poly.feature as any });
        map.addLayer({
          id: `${l.id}-fill`,
          type: "fill",
          source: l.id,
          paint: { "fill-color": l.poly.fill_color, "fill-opacity": 0 },
        });
        if (false) map.addLayer({
          id: `${l.id}-glow`,
          type: "line",
          source: l.id,
          layout: { "line-join": "round" },
          paint: {
            "line-color": "#000000",
            "line-width": 9,
            "line-opacity": 0,
            "line-blur": 6,
          },
        });
        map.addLayer({
          id: `${l.id}-line`,
          type: "line",
          source: l.id,
          layout: { "line-join": "round" },
          paint: {
            "line-color": l.poly.border_color,
            "line-width": 4,
            "line-opacity": 0,
          },
        });
      }
      setReady(true);
      continueRender(handle);
    });
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- per frame: move camera, restyle polygons, wait for WebGL to settle --
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const handle = delayRender(`maplibre: frame ${frame}`, {
      timeoutInMilliseconds: 120000,
    });
    let finished = false;
    const t0 = performance.now();
    const finish = (timedOut = false) => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      // parsed by worker.py to report where render time goes
      console.log(`geo-timing ${frame} ${Math.round(performance.now() - t0)} ${timedOut === true ? 1 : 0}`);
      // One more animation frame so React's overlay commit is painted too.
      requestAnimationFrame(() => continueRender(handle));
    };
    const timer = setTimeout(() => {
      finish(true);
    }, IDLE_TIMEOUT_MS);

    const cam = cameraAtFrame(timeline.scenes, frame, fps);
    map.jumpTo({
      center: cam.center,
      zoom: cam.zoom,
      pitch: cam.pitch,
      bearing: cam.bearing,
    });

    const set = (layer: string, prop: string, value: string | number) => {
      const k = `${layer}|${prop}`;
      if (paintCache.current[k] === value) return;
      paintCache.current[k] = value;
      map.setPaintProperty(layer, prop, value);
    };
    for (const l of polyLayers) {
      const { color, alpha } = polyPaintAt(l, frame, fps);
      set(`${l.id}-fill`, "fill-color", color);
      set(`${l.id}-fill`, "fill-opacity", +(alpha * l.poly.opacity).toFixed(4));
      set(`${l.id}-line`, "line-opacity", +alpha.toFixed(4));
      // glow off
    }

    // Camera transform is updated synchronously by jumpTo, so overlays can be
    // re-projected right now, inside the delayRender window.
    setProjectedFrame(frame);

    const onIdle = () => finish(false);
    map.once("idle", onIdle);
    map.triggerRepaint();
    return () => {
      map.off("idle", onIdle);
      finish(false);
    };
  }, [frame, ready, fps, timeline, polyLayers]);

  const ctx: MapCtx = {
    ready,
    project: (lonLat) => {
      const map = mapRef.current;
      if (!map || !ready) return null;
      const p = map.project(lonLat);
      return [p.x, p.y];
    },
  };

  return (
    <Ctx.Provider value={ctx}>
      <div ref={container} style={{ position: "absolute", left: 0, top: 0, width, height }} />
      {children}
    </Ctx.Provider>
  );
};

export const currentSceneIndex = sceneIndexAt;
