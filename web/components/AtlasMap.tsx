"use client";

// maplibre draws on a canvas in the browser so this has to be a client component

import { useEffect, useRef } from "react";
// maplibre v6 has no default export anymore, so namespace import instead of `import maplibregl from`
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import styles from "./AtlasMap.module.css";

// called AtlasMap not Map so it doesn't clash with the built in JS Map
export default function AtlasMap() {
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

    // react mounts things twice in dev, without this you end up with two maps
    return () => map.remove();
  }, []); // empty array = only run once

  return <div ref={containerRef} className={styles.map} />;
}
