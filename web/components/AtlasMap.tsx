"use client";

// MapLibre draws on a canvas in the browser so this has to be a client component

import { useEffect, useRef, useState } from "react";
// MapLibre v6 has no default export anymore, so namespace import instead of `import maplibregl from`
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import styles from "./AtlasMap.module.css";
import type { FeatureCollection } from "geojson";
import type { AtlasMapProps } from "@/types/atlas";

// Used by both the map fill and the legend
const COLOURS = ["#ffffcc", "#41b6c4", "#253494"];

export default function AtlasMap({
  level,
  values,
  boundaryVintage,
}: AtlasMapProps) {
  // The real <div> MapLibre will draw into.
  const containerRef = useRef<HTMLDivElement>(null);

  // Imperative MapLibre object — changing this should not cause a React render
  const mapRef = useRef<maplibregl.Map | null>(null);

  // Geometry is state because when new boundaries arrive, other React logic needs to react and synchronise those boundaries with MapLibre
  const [boundaryGeoJSON, setBoundaryGeoJSON] =
    useState<FeatureCollection | null>(null);

  // Range is derived directly from values rather than stored as separate state
  const rates = values.map(({ rate }) => rate);

  const range =
    rates.length > 0
      ? {
          min: Math.min(...rates),
          max: Math.max(...rates),
        }
      : null;

  // ------------------------------------------------------------
  // 1. MAP LIFECYCLE
  // Create MapLibre once when the component mounts
  // ------------------------------------------------------------
  useEffect(() => {
    if (!containerRef.current) return;

    // Turbopack doesn't serve MapLibre's worker file correctly in this setup, so point MapLibre at the copy stored in public/maplibre
    maplibregl.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");

    const atlasMap = new maplibregl.Map({
      container: containerRef.current,
      style: "https://tiles.openfreemap.org/styles/positron",
      center: [-1.5, 52.8], // longitude first, latitude second
      zoom: 5.5,
    });

    // Store the MapLibre instance so other effects can access the same map
    mapRef.current = atlasMap;

    // Remove MapLibre's resources when this component is unmounted.
    return () => {
      atlasMap.remove();
      mapRef.current = null;
    };
  }, []);

  // ------------------------------------------------------------
  // 2. GEOMETRY LIFECYCLE
  // Fetch new boundaries when geography/vintage changes
  // ------------------------------------------------------------
  useEffect(() => {
    const atlasMap = mapRef.current;
    if (!atlasMap) return;

    const loadGeometry = async () => {
      try {
        // Fetch geometry via API route
        const geometryRes = await fetch(
          `/api/geometry/${level}/${boundaryVintage}`,
        );

        // fetch() doesn't throw automatically for HTTP 400/500 responses.
        if (!geometryRes.ok) {
          console.error(`geometry fetch failed: ${geometryRes.status}`);
          return;
        }

        const geometry: FeatureCollection = await geometryRes.json();

        // Updating this state causes React to render again, after which the map data effect below runs with the new geometry
        setBoundaryGeoJSON(geometry);
      } catch (error) {
        console.error("Failed to load geometry", error);
      }
    };

    // On initial mount the MapLibre style may still be loading. Later geography changes can load immediately
    if (atlasMap.loaded()) {
      loadGeometry();
    } else {
      atlasMap.once("load", loadGeometry);
    }

    return () => {
      // Remove a pending initial-load listener if this effect is cleaned up before MapLibre has finished loading
      atlasMap.off("load", loadGeometry);
    };
  }, [level, boundaryVintage]);

  // ------------------------------------------------------------
  // 3. MAP DATA LIFECYCLE
  // Whenever either the boundaries or values change, join them together
  // and synchronise the result with the existing MapLibre map.
  // ------------------------------------------------------------
  useEffect(() => {
    const atlasMap = mapRef.current;

    if (!atlasMap || !boundaryGeoJSON) return;

    // Convert the rates into a code → rate lookup so we don't search the
    // whole values array separately for every boundary feature.
    const rateByCode: Record<string, number> = Object.fromEntries(
      values.map(({ code, rate }) => [code, rate]),
    );

    // Keep the original polygon geometry/properties and add the matching rate to each feature for MapLibre styling and hover information
    const mapGeoJSON: FeatureCollection = {
      ...boundaryGeoJSON,
      features: boundaryGeoJSON.features.map((feature) => {
        const code = feature.properties?.code as string | undefined;

        return {
          ...feature,
          properties: {
            ...feature.properties,
            rate: code ? (rateByCode[code] ?? null) : null,
          },
        };
      }),
    };

    const existingSource = atlasMap.getSource("areas") as
      | maplibregl.GeoJSONSource
      | undefined;

    if (existingSource) {
      // The source already exists so replace only its data
      existingSource.setData(mapGeoJSON);
    } else {
      // First data load: create the source
      atlasMap.addSource("areas", {
        type: "geojson",
        data: mapGeoJSON,
      });
    }

    // Put polygons underneath the basemap's place labels so town and city names remain readable
    const firstLabelId = atlasMap
      .getStyle()
      .layers.find((layer) => layer.type === "symbol")?.id;

    // Layers only need creating once. Afterwards they continue drawing whatever data is currently stored in the "areas" source
    if (!atlasMap.getLayer("areas-fill")) {
      atlasMap.addLayer(
        {
          id: "areas-fill",
          type: "fill",
          source: "areas",
          paint: {
            "fill-color": "#d1d5db",
            "fill-opacity": 0.8,
          },
        },
        firstLabelId,
      );
    }

    if (!atlasMap.getLayer("areas-line")) {
      atlasMap.addLayer(
        {
          id: "areas-line",
          type: "line",
          source: "areas",
          paint: {
            "line-color": "#ffffff",
            "line-width": 0.5,
          },
        },
        firstLabelId,
      );
    }

    const currentRates = values.map(({ rate }) => rate);

    // If there are no values, leave the polygons in their neutral colour
    if (currentRates.length === 0) {
      atlasMap.setPaintProperty("areas-fill", "fill-color", "#d1d5db");
      return;
    }

    const min = Math.min(...currentRates);
    const max = Math.max(...currentRates);
    const midPoint = (min + max) / 2;

    // Update the existing fill layer's colour expression rather than recreating the layer or the whole map
    atlasMap.setPaintProperty(
      "areas-fill",
      "fill-color",
      min === max
        ? COLOURS[1]
        : [
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
    );
  }, [boundaryGeoJSON, values]);

  // ------------------------------------------------------------
  // 4. MAP INTERACTION
  // Add hover behaviour once the atlas layers exist.
  // ------------------------------------------------------------
  useEffect(() => {
    const atlasMap = mapRef.current;
    if (!atlasMap) return;

    const setupInteractions = () => {
      if (!atlasMap.getLayer("areas-fill")) return;

      // One popup is reused on every mouse move rather than creating a new popup each time
      const popup = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
      });

      const handleMouseMove = (event: maplibregl.MapLayerMouseEvent) => {
        const feature = event.features?.[0];
        if (!feature) return;

        const name = feature.properties?.name as string;
        const rate = feature.properties?.rate as number | null;

        atlasMap.getCanvas().style.cursor = "pointer";

        popup
          .setLngLat(event.lngLat)
          .setHTML(
            `<strong>${name}</strong><br/>${
              rate == null ? "No data" : rate.toFixed(1) + "%"
            }`,
          )
          .addTo(atlasMap);
      };

      const handleMouseLeave = () => {
        atlasMap.getCanvas().style.cursor = "";
        popup.remove();
      };

      atlasMap.on("mousemove", "areas-fill", handleMouseMove);

      atlasMap.on("mouseleave", "areas-fill", handleMouseLeave);

      return () => {
        atlasMap.off("mousemove", "areas-fill", handleMouseMove);

        atlasMap.off("mouseleave", "areas-fill", handleMouseLeave);

        popup.remove();
      };
    };

    // The interaction effect can run before the asynchronous geometry request has created the atlas layers so wait until they exist
    if (atlasMap.getLayer("areas-fill")) {
      return setupInteractions();
    }

    let interactionCleanup: (() => void) | undefined;

    const cleanupSourceListener = () => {
      atlasMap.off("sourcedata", handleSourceData);
    };

    const handleSourceData = () => {
      if (!atlasMap.getLayer("areas-fill")) return;

      cleanupSourceListener();
      interactionCleanup = setupInteractions();
    };

    atlasMap.on("sourcedata", handleSourceData);

    return () => {
      cleanupSourceListener();
      interactionCleanup?.();
    };
  }, []);

  return (
    <div className={styles.wrapper}>
      <div ref={containerRef} className={styles.map} />

      {/* Only render the legend when there are values to describe */}
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
