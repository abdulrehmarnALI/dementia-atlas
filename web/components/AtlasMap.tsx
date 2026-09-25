"use client";

// maplibre draws on a canvas in the browser so this has to be a client component

import { useEffect, useRef, useState } from "react";
// maplibre v6 has no default export anymore, so namespace import instead of `import maplibregl from`
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import styles from "./AtlasMap.module.css";
import type { FeatureCollection } from "geojson";
import type { AtlasMapProps } from "@/types/atlas";

// used by both the map fill and the legend so they can't drift apart
const COLOURS = ["#ffffcc", "#41b6c4", "#253494"];

// called AtlasMap not Map so it doesn't clash with the built in JS Map
export default function AtlasMap({
  level,
  values,
  boundaryVintage,
}: AtlasMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  const [range, setRange] = useState<{ min: number; max: number } | null>(null);

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
      try {
        const res = await fetch(`/api/geometry/${level}/${boundaryVintage}`);
        if (!res.ok) {
          // fetch doesn't throw on 400/500
          console.error(`map data failed: ${res.status}`);
          return;
        }
        const geometry: FeatureCollection = await res.json();

        // This makes looking up the rate for each polygon cheap.
        const rateByCode: Record<string, number> = Object.fromEntries(
          values.map(({ code, rate }) => [code, rate]),
        );

        const geojson: FeatureCollection = {
          ...geometry,
          features: geometry.features.map((f) => {
            const code = f.properties?.code as string | undefined;
            return {
              ...f,
              properties: {
                ...f.properties,
                rate: code ? (rateByCode[code] ?? null) : null,
              },
            };
          }),
        };

        // Colour scale from the data itself, not hard-coded
        const rates = values.map(({ rate }) => rate);

        const min = Math.min(...rates);
        const max = Math.max(...rates);
        const midPoint = (min + max) / 2;
        setRange({ min, max });

        map.addSource("areas", { type: "geojson", data: geojson });

        // Put layers underneath the basemap's place labels, so town names stay readable
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
                "case",
                ["==", ["get", "rate"], null],
                "#d1d5db",
                [
                  "interpolate",
                  ["linear"],
                  ["get", "rate"],
                  min,
                  COLOURS[0],
                  midPoint,
                  COLOURS[1],
                  max,
                  COLOURS[2],
                ],
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

        // one popup reused on every move, not a new one each time
        const popup = new maplibregl.Popup({
          closeButton: false,
          closeOnClick: false,
        });

        map.on("mousemove", "areas-fill", (e) => {
          const feature = e.features?.[0];
          if (!feature) return;

          const name = feature.properties.name as string;
          const rate = feature.properties.rate as number | null;

          map.getCanvas().style.cursor = "pointer";
          popup
            .setLngLat(e.lngLat)
            .setHTML(
              `<strong>${name}</strong><br/>${rate == null ? "No data" : rate.toFixed(1) + "%"}`,
            )
            .addTo(map);
        });

        map.on("mouseleave", "areas-fill", () => {
          map.getCanvas().style.cursor = "";
          popup.remove();
        });
      } catch (error) {
        console.error("Failed to load map data", error);
      }
    });

    // react mounts things twice in dev, without this we end up with two maps
    return () => map.remove();
  }, [level, values]); // re-run effect if the level changes

  return (
    <div className={styles.wrapper}>
      <div ref={containerRef} className={styles.map} />

      {/* only render once the data has loaded */}
      {range && (
        <div className={styles.legend}>
          <div className={styles.legendTitle}>
            Dementia diagnosis rate (65+)
          </div>
          <div
            className={styles.legendBar}
            style={{
              background: `linear-gradient(to right, ${COLOURS.join(", ")})`,
            }}
          />
          <div className={styles.legendLabels}>
            <span>{range.min.toFixed(1)}%</span>
            <span>{range.max.toFixed(1)}%</span>
          </div>
        </div>
      )}
    </div>
  );
}
