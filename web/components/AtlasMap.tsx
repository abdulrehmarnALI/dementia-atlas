"use client";

// maplibre draws on a canvas in the browser so this has to be a client component

import { useEffect, useRef } from "react";
// maplibre v6 has no default export anymore, so namespace import instead of `import maplibregl from`
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import styles from "./AtlasMap.module.css";
import type { FeatureCollection } from "geojson";

// called AtlasMap not Map so it doesn't clash with the built in JS Map
export default function AtlasMap({ level }: { level: string }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // turbopack doesn't serve maplibre's worker file, so the browser was getting the 404 page back
    // and the map stayed blank. copied the worker into public/maplibre and pointing at it here
    maplibregl.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: "https://tiles.openfreemap.org/styles/positron", // free, no key, nice and muted
      center: [-1.5, 52.8], // lng first, lat second
      zoom: 5.5,
    });

    map.on("load", async () => {
      const res = await fetch(`/api/map?period=2026-06&level=${level}`);
      if (!res.ok) {
        // fetch doesn't throw on 400/500
        console.error(`map data failed: ${res.status}`);
        return;
      }
      const geojson: FeatureCollection = await res.json();

      // Colour scale from the data itself, not hard-coded
      const rates = geojson.features
        .map((f) => f.properties?.diag_rate)
        .filter((r): r is number => typeof r === "number");
      const min = Math.min(...rates);
      const max = Math.max(...rates);

      map.addSource("areas", { type: "geojson", data: geojson });

      // Put our layers underneath the basemap's place labels, so town names stay readable
      const firstLabelId = map
        .getStyle()
        .layers.find((l) => l.type === "symbol")?.id;

      map.addLayer(
        {
          id: "areas-fill",
          type: "fill",
          source: "areas",
          paint: {
            "fill-color": [
              "interpolate",
              ["linear"],
              ["get", "diag_rate"],
              min,
              "#ffffcc",
              (min + max) / 2,
              "#41b6c4",
              max,
              "#253494",
            ],
            "fill-opacity": 0.8,
          },
        },
        firstLabelId,
      );

      map.addLayer(
        {
          id: "areas-line",
          type: "line",
          source: "areas",
          paint: { "line-color": "#ffffff", "line-width": 0.5 },
        },
        firstLabelId,
      );
    });

    // react mounts things twice in dev, without this you end up with two maps
    return () => map.remove();
  }, [level]); // re-run effect if the level changes

  return <div ref={containerRef} className={styles.map} />;
}
