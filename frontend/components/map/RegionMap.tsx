"use client";

import type * as MLType from "maplibre-gl";

import { getMaplibre } from "@/lib/maplibre";
import { useEffect, useRef } from "react";

import { TONE_HEX, toneOf } from "@/lib/status";
import type { AreaOverview } from "@/lib/types";

/** Regional context map: operational area extents and status markers (real geography basemap optional). */
export function RegionMap({ areas, labels, onSelect }: { areas: AreaOverview[]; labels: Record<string, string>; onSelect: (id: string) => void }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLType.Map | null>(null);
  const markers = useRef<MLType.Marker[]>([]);

  useEffect(() => {
    if (!el.current || map.current) return;
    const maplibregl = getMaplibre();
    const m = new maplibregl.Map({
      container: el.current,
      attributionControl: { compact: true },
      style: {
        version: 8,
        sources: {
          carto: {
            type: "raster",
            tiles: ["https://a.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png", "https://b.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}.png"],
            tileSize: 256,
            attribution: "© OpenStreetMap contributors © CARTO",
          },
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#0b1118" } },
          { id: "carto", type: "raster", source: "carto", paint: { "raster-opacity": 0.75 } },
        ],
      },
      center: [68.9, 52.6],
      zoom: 6.3,
    });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("error", () => { /* basemap tiles may be unreachable offline — operational layers still render */ });
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const maplibregl = getMaplibre();
    const draw = () => {
      const fc: GeoJSON.FeatureCollection = {
        type: "FeatureCollection",
        features: areas.map((a) => ({
          type: "Feature",
          properties: { id: a.id, color: TONE_HEX[toneOf(a.status)] },
          geometry: {
            type: "Polygon",
            coordinates: [[[a.bbox[0], a.bbox[1]], [a.bbox[2], a.bbox[1]], [a.bbox[2], a.bbox[3]], [a.bbox[0], a.bbox[3]], [a.bbox[0], a.bbox[1]]]],
          },
        })),
      };
      const src = m.getSource("areas") as MLType.GeoJSONSource | undefined;
      if (src) src.setData(fc);
      else {
        m.addSource("areas", { type: "geojson", data: fc });
        m.addLayer({ id: "areas-fill", type: "fill", source: "areas", paint: { "fill-color": ["get", "color"], "fill-opacity": 0.12 } });
        m.addLayer({ id: "areas-line", type: "line", source: "areas", paint: { "line-color": ["get", "color"], "line-width": 2 } });
      }
      markers.current.forEach((mk) => mk.remove());
      markers.current = areas.map((a) => {
        const d = document.createElement("button");
        d.className = "argus-marker";
        d.setAttribute("aria-label", labels[a.id] || a.id);
        const color = TONE_HEX[toneOf(a.status)];
        d.innerHTML = `<div style="display:flex;align-items:center;gap:6px;background:#10161ee6;border:1px solid ${color};border-radius:3px;padding:3px 7px;color:#dbe4ee;font:600 12px Inter,Segoe UI,sans-serif;white-space:nowrap"><span style="width:9px;height:9px;border-radius:50%;background:${color};box-shadow:0 0 8px ${color}"></span>${labels[a.id] || a.id}</div>`;
        d.onclick = () => onSelect(a.id);
        return new maplibregl.Marker({ element: d }).setLngLat(a.center).addTo(m);
      });
      if (areas.length) {
        const b = new maplibregl.LngLatBounds();
        areas.forEach((a) => { b.extend([a.bbox[0], a.bbox[1]]); b.extend([a.bbox[2], a.bbox[3]]); });
        m.fitBounds(b, { padding: 80, duration: 0, maxZoom: 8 });
      }
    };
    if (m.isStyleLoaded()) draw();
    else m.once("load", draw);
  }, [areas, labels, onSelect]);

  return <div ref={el} className="h-full w-full" />;
}
