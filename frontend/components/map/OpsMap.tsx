"use client";

import type * as ML from "maplibre-gl";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslations } from "use-intl";

import { useAreaCtx } from "@/components/area/AreaContext";
import { absUrl, mapTransformRequest } from "@/lib/api";
import { countdown, pickName } from "@/lib/format";
import { useLocale } from "@/lib/i18n";
import { getMaplibre } from "@/lib/maplibre";
import { useUi } from "@/lib/store";
import { toneOf, type Tone } from "@/lib/status";

import { mapHandle } from "@/lib/mapRef";

import { countdownMarker, declutter, esc, featureMarker, roadLabel } from "./markers";

// road classes that get a state label (DEMO classes + real OSM classes) with label priority / min zoom
const LABELED_CLASSES: Record<string, { p: number; z: number }> = {
  highway: { p: 60, z: 0 }, urban_main: { p: 50, z: 0 }, rural: { p: 40, z: 13 }, track: { p: 20, z: 14.5 },
  motorway: { p: 60, z: 0 }, trunk: { p: 58, z: 0 }, primary: { p: 52, z: 0 }, secondary: { p: 44, z: 13.2 }, tertiary: { p: 36, z: 14.2 },
};
// casing / line widths by class (DEMO + real OSM)
const CASE_W = ["match", ["get", "road_class"], ["highway", "motorway"], 9, ["urban_main", "trunk"], 8, "primary", 7.5, ["rural", "secondary"], 6.5, "tertiary", 6, 4.6];
const LINE_W = ["match", ["get", "road_class"], ["highway", "motorway"], 5.5, ["urban_main", "trunk"], 4.8, "primary", 4.4, ["rural", "secondary"], 3.8, ["track", "tertiary"], 3.2, 2.2];
// building visualization height: OSM building:levels × 3 m (1 level when untagged) — NOT a surveyed height
const EMPTY_FC: GeoJSON.FeatureCollection = { type: "FeatureCollection", features: [] };

type Markers = Record<string, ML.Marker[]>;

function lineMid(coords: [number, number][]): [number, number] {
  if (coords.length === 2) return [(coords[0][0] + coords[1][0]) / 2, (coords[0][1] + coords[1][1]) / 2];
  return coords[Math.floor(coords.length / 2)];
}

export function OpsMap() {
  const ctx = useAreaCtx();
  const { areaId, area, scenario, layers, accessTl, impactTl, access, t, frameIndex, overlays } = ctx;
  const { locale } = useLocale();
  const tr = useTranslations("road");
  const tf = useTranslations("facilityType");
  const tk = useTranslations("siteKind");
  const tmap = useTranslations("map");
  const mapMode = useUi((s) => s.mapMode);
  const lay = useUi((s) => s.layers);
  const el = useRef<HTMLDivElement>(null);
  const mapRef = useRef<ML.Map | null>(null);
  const markers = useRef<Markers>({});
  const [ready, setReady] = useState(false);
  const floodSlot = useRef<"a" | "b">("a");
  const floodUrl = useRef<string>("");
  const wetBuildings = useRef<Set<string>>(new Set());
  const hlSegs = useRef<Set<string>>(new Set());
  const localeRef = useRef(locale);
  localeRef.current = locale;
  const tb = useTranslations("buildingUse");
  const popupRef = useRef<ML.Popup | null>(null);
  // latest per-frame state for event handlers registered once
  const live = useRef({ access, t, fmt: ctx.fmt, tmap, tr, tf, tb });
  live.current = { access, t, fmt: ctx.fmt, tmap, tr, tf, tb };
  const areaReady = !!area;
  const centerRef = useRef<[number, number] | null>(null);
  if (area) centerRef.current = area.center;

  // ------------------------------------------------------------------ init
  useEffect(() => {
    if (!el.current || mapRef.current || !areaReady || !centerRef.current) return;
    const maplibregl = getMaplibre();
    const demUrl = absUrl(`/api/tiles/terrain/${areaId}/{z}/{x}/{y}.png`);
    const m = new maplibregl.Map({
      container: el.current,
      transformRequest: (url) => mapTransformRequest(url),
      attributionControl: { compact: true, customAttribution: area?.attribution || (area?.is_demo === false
        ? "© OpenStreetMap contributors (ODbL) · Copernicus DEM GLO-30 · WorldPop · JRC GSW"
        : "ARGUS FloodOps · DEMO synthetic geometry") },
      center: centerRef.current,
      zoom: 12.3,
      maxPitch: 75,
      style: {
        version: 8,
        sources: {
          dem: { type: "raster-dem", tiles: [demUrl], tileSize: 256, encoding: "terrarium", maxzoom: 14 },
          demhs: { type: "raster-dem", tiles: [demUrl], tileSize: 256, encoding: "terrarium", maxzoom: 14 },
          carto: {
            type: "raster", tileSize: 256, attribution: "© OpenStreetMap contributors",
            tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
          },
        },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#0c1219" } },
          { id: "carto", type: "raster", source: "carto", layout: { visibility: "none" }, paint: { "raster-opacity": 0.55, "raster-brightness-max": 0.45, "raster-saturation": -0.6, "raster-contrast": 0.12 } },
          {
            id: "hillshade", type: "hillshade", source: "demhs",
            paint: { "hillshade-exaggeration": 0.55, "hillshade-shadow-color": "#05080c", "hillshade-highlight-color": "#3a4a5c", "hillshade-accent-color": "#1d2835" },
          },
        ],
      },
    });
    m.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "top-right");
    mapHandle.set(m, { center: centerRef.current, zoom: 12.3, bbox: area?.bbox as [number, number, number, number] | undefined });
    popupRef.current = new maplibregl.Popup({ closeButton: true, closeOnClick: true, maxWidth: "300px", className: "argus-popup" });
    m.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-right");
    m.on("error", () => { /* offline basemap / transient tile errors must never break the operational map */ });
    m.on("load", () => setReady(true));
    mapRef.current = m;
    return () => {
      Object.values(markers.current).flat().forEach((mk) => mk.remove());
      markers.current = {};
      m.remove();
      mapRef.current = null;
      mapHandle.set(null);
      setReady(false);
    };
  }, [areaId, areaReady]);

  // ------------------------------------------------------------------ static layers
  useEffect(() => {
    const m = mapRef.current;
    if (!ready || !m || !scenario) return;
    const corners = scenario.image_corners as [[number, number], [number, number], [number, number], [number, number]];
    const blank = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=";
    const add = (id: string, src: ML.SourceSpecification) => { if (!m.getSource(id)) m.addSource(id, src); };
    add("sectors", { type: "geojson", data: (layers.sectors as unknown as GeoJSON.FeatureCollection) || EMPTY_FC });
    add("river", { type: "geojson", data: (layers.river as unknown as GeoJSON.FeatureCollection) || EMPTY_FC });
    add("waterways", { type: "geojson", data: (layers.waterways as unknown as GeoJSON.FeatureCollection) || EMPTY_FC });
    add("flood-a", { type: "image", url: blank, coordinates: corners });
    add("flood-b", { type: "image", url: blank, coordinates: corners });
    add("extent", { type: "geojson", data: EMPTY_FC });
    add("roads", { type: "geojson", data: (layers.roads as unknown as GeoJSON.FeatureCollection) || EMPTY_FC, promoteId: "id" });
    add("buildings", { type: "geojson", data: (layers.buildings as unknown as GeoJSON.FeatureCollection) || EMPTY_FC, promoteId: "id" });
    add("routes", { type: "geojson", data: EMPTY_FC });
    const addLayer = (spec: ML.LayerSpecification) => { if (!m.getLayer(spec.id)) m.addLayer(spec); };
    addLayer({ id: "sectors-fill", type: "fill", source: "sectors", paint: { "fill-color": "#7aa2c7", "fill-opacity": 0.05 } });
    addLayer({ id: "sectors-line", type: "line", source: "sectors", paint: { "line-color": "#7aa2c7", "line-width": 1, "line-dasharray": [3, 3], "line-opacity": 0.6 } });
    addLayer({ id: "flood-a", type: "raster", source: "flood-a", paint: { "raster-opacity": 0.9, "raster-fade-duration": 0, "raster-opacity-transition": { duration: 650, delay: 0 }, "raster-resampling": "linear" } });
    addLayer({ id: "flood-b", type: "raster", source: "flood-b", paint: { "raster-opacity": 0, "raster-fade-duration": 0, "raster-opacity-transition": { duration: 650, delay: 0 }, "raster-resampling": "linear" } });
    addLayer({ id: "water-fill", type: "fill", source: "waterways", filter: ["==", ["geometry-type"], "Polygon"],
      paint: { "fill-color": "#2a6fb0", "fill-opacity": 0.35 } });
    addLayer({ id: "water-line", type: "line", source: "waterways", filter: ["==", ["geometry-type"], "LineString"],
      paint: { "line-color": "#3d8fd6", "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.6, 15, 2], "line-opacity": 0.6 } });
    addLayer({ id: "river", type: "line", source: "river", paint: { "line-color": "#5fb4ff", "line-width": ["interpolate", ["linear"], ["zoom"], 10, 1, 15, 3], "line-opacity": 0.35 } });
    addLayer({ id: "extent", type: "line", source: "extent", paint: { "line-color": "#c8ecff", "line-width": 1.3, "line-opacity": 0.85, "line-dasharray": [2, 2] } });
    // 3D only: translucent water slab over the modelled extent — a VISUALIZATION of the same frame, not extra physics
    addLayer({ id: "water-3d", type: "fill-extrusion", source: "extent", filter: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
      layout: { visibility: "none" },
      paint: { "fill-extrusion-color": "#2f86d8", "fill-extrusion-opacity": 0.32, "fill-extrusion-height": 0.8, "fill-extrusion-base": 0 } });
    addLayer({
      id: "roads-case", type: "line", source: "roads", layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": "#05080c", "line-width": ["interpolate", ["linear"], ["zoom"], 11, 2.2, 15, CASE_W as unknown as number] },
    });
    addLayer({
      id: "roads-line", type: "line", source: "roads", layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": ["case", ["boolean", ["feature-state", "hl"], false], "#3fb3ff",
          ["match", ["coalesce", ["feature-state", "state"], 0], 2, "#ef4d4d", 1, "#f59e2b", "#8aa2b8"]],
        "line-width": ["interpolate", ["linear"], ["zoom"], 11, 1.1, 15,
          ["+", LINE_W, ["case", ["boolean", ["feature-state", "hl"], false], 2.5, 0]]] as unknown as number,
        "line-opacity": ["match", ["coalesce", ["feature-state", "state"], 0], 0, 0.75, 1],
      },
    });
    addLayer({
      id: "roads-closed", type: "line", source: "roads",
      paint: {
        "line-color": "#ffe1e1", "line-dasharray": [1.2, 1.4],
        "line-width": ["interpolate", ["linear"], ["zoom"], 11, 0.8, 15, 2],
        "line-opacity": ["case", ["==", ["coalesce", ["feature-state", "state"], 0], 2], 0.95, 0],
      },
    });
    addLayer({ id: "routes-line", type: "line", source: "routes", filter: ["!", ["get", "dashed"]], layout: { "line-cap": "round", "line-join": "round" },
      paint: { "line-color": ["get", "color"], "line-width": ["get", "width"], "line-opacity": 0.95 } });
    addLayer({ id: "routes-dash", type: "line", source: "routes", filter: ["get", "dashed"],
      paint: { "line-color": ["get", "color"], "line-width": ["get", "width"], "line-dasharray": [2, 1.5], "line-opacity": 0.95 } });
    addLayer({
      id: "buildings", type: "fill-extrusion", source: "buildings", minzoom: 11,
      paint: {
        "fill-extrusion-color": ["case", [">", ["coalesce", ["feature-state", "depth"], 0], 5],
          ["interpolate", ["linear"], ["coalesce", ["feature-state", "depth"], 0], 10, "#f2c14e", 50, "#f59e2b", 100, "#ef6b3b", 200, "#c81d3d"],
          ["interpolate", ["linear"], ["get", "height_m"], 3, "#2b3746", 9, "#36475b", 18, "#425a74", 30, "#4f6d8c"]],
        "fill-extrusion-height": ["get", "height_m"],
        "fill-extrusion-base": 0,
        "fill-extrusion-opacity": 0.9,
        "fill-extrusion-vertical-gradient": true,
      },
    });
  }, [ready, scenario, layers]);


  // ------------------------------------------------------------------ interactions (registered once)
  useEffect(() => {
    const m = mapRef.current;
    const popup = popupRef.current;
    if (!ready || !m || !popup) return;
    const row = (k: string, v: string) => `<div class="argus-pop-row"><span>${esc(k)}</span><b>${esc(v)}</b></div>`;
    const card = (kind: string, title: string, rows: string[], note?: string) =>
      `<div class="argus-pop"><div class="argus-pop-kind">${esc(kind)}</div><div class="argus-pop-title">${esc(title)}</div>${rows.join("")}${note ? `<div class="argus-pop-note">${esc(note)}</div>` : ""}</div>`;
    const parse = (v: unknown) => (typeof v === "string" ? JSON.parse(v) : v) as Record<string, string>;
    m.on("click", "roads-line", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const { access: acc, t: tt, fmt, tmap: T, tr: TR } = live.current;
      const p = f.properties as Record<string, unknown>;
      const edge = acc?.edges[String(p.id)];
      const road = acc?.roads.find((r) => r.road_id === p.road_id);
      const st = edge?.state ?? "OPEN";
      const rows = [row(T("popup.state", { time: fmt(tt) }), TR.has(st) ? TR(st) : st)];
      if (road?.state === "CLOSES_IN" && road.closes_in_min !== null) rows.push(row(T("popup.closesIn"), countdown(road.closes_in_min)));
      rows.push(row(T("popup.length"), `${Math.round(Number(p.length_m))} ${T("popup.m")}`));
      rows.push(row(T("popup.roadId"), `${p.road_id} · ${p.id}`));
      popup.setLngLat(e.lngLat).setHTML(card(T("popup.road"), pickName(parse(p.names), localeRef.current, String(p.road_id)), rows, T("popup.osmSource"))).addTo(m);
    });
    m.on("click", "buildings", (e) => {
      const f = e.features?.[0];
      if (!f) return;
      const { t: tt, fmt, tmap: T, tb: TB } = live.current;
      const st = m.getFeatureState({ source: "buildings", id: f.id as string }) as { depth?: number };
      const p = f.properties as Record<string, unknown>;
      const use = String(p.use || "unknown");
      const kind = TB.has(use) ? TB(use) : TB("unknown");
      const rows = [
        row(T("popup.floors"), String(p.floors ?? 1)),
        row(T("popup.vizHeight"), `≈ ${Number(p.height_m).toFixed(0)} ${T("popup.m")}`),
        st.depth && st.depth > 5 ? row(T("popup.depth", { time: fmt(tt) }), `${(st.depth / 100).toFixed(2)} ${T("popup.m")}`) : row(T("popup.floodAt", { time: fmt(tt) }), T("popup.dry")),
      ];
      popup.setLngLat(e.lngLat).setHTML(card(T("popup.building"), `${kind} · #${String(p.id).replace(/^K?B/, "")}`, rows, T("popup.heightNote"))).addTo(m);
    });
    for (const id of ["roads-line", "buildings"]) {
      m.on("mouseenter", id, () => (m.getCanvas().style.cursor = "pointer"));
      m.on("mouseleave", id, () => (m.getCanvas().style.cursor = ""));
    }
    const onMove = () => declutter(m.getContainer(), m.getZoom());
    m.on("moveend", onMove);
    return () => { m.off("moveend", onMove); };
  }, [ready]);

  const facilityPopup = useCallback((id: string, lngLat: [number, number], names: Record<string, string>, kind: string, crit: number) => {
    const m = mapRef.current;
    const popup = popupRef.current;
    if (!m || !popup) return;
    const { access: acc, t: tt, fmt, tmap: T, tf: TF } = live.current;
    const fs = acc?.facilities.find((x) => x.id === id);
    const row = (k: string, v: string) => `<div class="argus-pop-row"><span>${esc(k)}</span><b>${esc(v)}</b></div>`;
    const rows = [row(T("popup.criticality"), String(crit))];
    if (fs) {
      rows.push(row(T("popup.floodAt", { time: fmt(tt) }), fs.flooded_now ? T("popup.flooded") : fs.flood_in_min !== null ? T("popup.floodIn", { t: countdown(fs.flood_in_min) }) : T("popup.dry")));
      rows.push(row(T("popup.access"), !fs.accessible_now ? T("popup.noAccess") : fs.access_lost_in_min !== null ? T("popup.accessLostIn", { t: countdown(fs.access_lost_in_min) }) : T("popup.accessible")));
    }
    popup.setLngLat(lngLat).setHTML(`<div class="argus-pop"><div class="argus-pop-kind">${esc(TF.has(kind) ? TF(kind) : kind)}</div><div class="argus-pop-title">${esc(pickName(names, localeRef.current, id))}</div>${rows.join("")}<div class="argus-pop-note">${esc(T("popup.facilitySource"))}</div></div>`).addTo(m);
  }, []);

  // keep GeoJSON sources in sync when layer data arrives
  useEffect(() => {
    const m = mapRef.current;
    if (!ready || !m) return;
    const set = (id: string, fc: unknown) => { const s = m.getSource(id) as ML.GeoJSONSource | undefined; if (s && fc) s.setData(fc as GeoJSON.FeatureCollection); };
    set("roads", layers.roads);
    set("buildings", layers.buildings);
    set("sectors", layers.sectors);
    set("river", layers.river);
    set("waterways", layers.waterways);
  }, [ready, layers]);

  // ------------------------------------------------------------------ flood surface (crossfade)
  // One image load in flight at a time; when it finishes we crossfade to it and immediately load the newest
  // requested frame. Fast playback therefore never cancels itself into a frozen picture.
  const tRounded = t === null ? null : Math.round(t / 10) * 10;
  const floodLoading = useRef(false);
  const floodWanted = useRef<string>("");
  const floodOn = useRef(lay.flood);
  useEffect(() => { floodOn.current = lay.flood; }, [lay.flood]);
  useEffect(() => {
    const m = mapRef.current;
    if (!ready || !m || !scenario || tRounded === null) return;
    const corners = scenario.image_corners as [[number, number], [number, number], [number, number], [number, number]];
    function load(map: ML.Map, url: string) {
      const next = floodSlot.current === "a" ? "b" : "a";
      const src = map.getSource(`flood-${next}`) as ML.ImageSource | undefined;
      if (!src) return;
      floodLoading.current = true;
      floodUrl.current = url;
      src.updateImage({ url, coordinates: corners });
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        map.off("sourcedata", onData);
        clearTimeout(fallback);
        if (mapRef.current === map) {
          map.setPaintProperty(`flood-${next}`, "raster-opacity", floodOn.current ? 0.9 : 0);
          map.setPaintProperty(`flood-${floodSlot.current}`, "raster-opacity", 0);
          floodSlot.current = next;
        }
        floodLoading.current = false;
        if (floodWanted.current && floodWanted.current !== url && mapRef.current === map) load(map, floodWanted.current);
      };
      const onData = (e: ML.MapSourceDataEvent) => { if (e.sourceId === `flood-${next}` && e.isSourceLoaded) finish(); };
      map.on("sourcedata", onData);
      const fallback = setTimeout(finish, 2500);
    }
    const url = absUrl(`/api/scenarios/${scenario.id}/frames/${tRounded}/depth.png?member=${scenario.active_member}`);
    floodWanted.current = url;
    if (url === floodUrl.current || floodLoading.current) return;
    load(m, url);
  }, [ready, scenario, tRounded]);
  useEffect(() => {
    const m = mapRef.current;
    if (!ready || !m?.getLayer(`flood-${floodSlot.current}`)) return;
    m.setPaintProperty(`flood-${floodSlot.current}`, "raster-opacity", lay.flood ? 0.9 : 0);
  }, [ready, lay.flood]);

  // extent outline (fetched per frame, cached by the browser/react-query layer below)
  useEffect(() => {
    const m = mapRef.current;
    if (!ready || !m || !scenario || tRounded === null || !lay.extent) return;
    let alive = true;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      const { url, headers } = mapTransformRequest(`/api/scenarios/${scenario.id}/frames/${tRounded}/extent?member=${scenario.active_member}`);
      fetch(url, { headers, signal: ctrl.signal }).then((r) => (r.ok ? r.json() : null)).then((fc) => {
        if (!alive || !fc) return;
        (m.getSource("extent") as ML.GeoJSONSource | undefined)?.setData(fc);
      }).catch(() => {});
    }, 150);
    return () => { alive = false; clearTimeout(timer); ctrl.abort(); };
  }, [ready, scenario, tRounded, lay.extent]);

  // ------------------------------------------------------------------ feature states: roads + buildings per frame
  useEffect(() => {
    const m = mapRef.current;
    if (!ready || !m || !accessTl) return;
    const useExact = access && t !== null && Math.abs(access.as_of - t) < 1e-6;
    for (const [sid, arr] of Object.entries(accessTl.states)) {
      let st = arr[frameIndex] ?? 0;
      if (useExact && access?.edges[sid]) st = access.edges[sid].state === "CLOSED" ? 2 : access.edges[sid].state === "RESTRICTED" ? 1 : 0;
      m.setFeatureState({ source: "roads", id: sid }, { state: st });
    }
  }, [ready, accessTl, frameIndex, access, t]);

  useEffect(() => {
    const m = mapRef.current;
    if (!ready || !m || !impactTl || !m.getSource("buildings")) return;
    const ids = impactTl.buildings.ids;
    const next = new Set<string>();
    ids.forEach((id, i) => {
      const d = impactTl.buildings.depth_cm[i][frameIndex] ?? 0;
      if (d > 5) next.add(id);
      if (d > 5 || wetBuildings.current.has(id)) m.setFeatureState({ source: "buildings", id }, { depth: d });
    });
    wetBuildings.current = next;
  }, [ready, impactTl, frameIndex, layers.buildings]);

  // ------------------------------------------------------------------ overlays: routes + highlighted segments
  useEffect(() => {
    const m = mapRef.current;
    if (!ready || !m) return;
    const feats: GeoJSON.Feature[] = overlays.routes.flatMap((r) =>
      ctx.segmentCoords(r.segments).map((c) => ({ type: "Feature" as const, geometry: { type: "LineString" as const, coordinates: c },
        properties: { color: r.color, dashed: !!r.dashed, width: r.width ?? 4 } })));
    (m.getSource("routes") as ML.GeoJSONSource | undefined)?.setData({ type: "FeatureCollection", features: feats });
    hlSegs.current.forEach((s) => m.setFeatureState({ source: "roads", id: s }, { hl: false }));
    overlays.highlightSegments.forEach((s) => m.setFeatureState({ source: "roads", id: s }, { hl: true }));
    hlSegs.current = new Set(overlays.highlightSegments);
    if (overlays.focus) m.easeTo({ center: [overlays.focus.lon, overlays.focus.lat], zoom: overlays.focus.zoom ?? m.getZoom(), duration: 700 });
  }, [ready, overlays, ctx]);

  // ------------------------------------------------------------------ HTML markers
  const roadStates = useMemo(() => {
    const out: Record<string, { state: string; closes_in_min: number | null }> = {};
    access?.roads.forEach((r) => (out[r.road_id] = { state: r.state, closes_in_min: r.closes_in_min }));
    return out;
  }, [access]);
  const facilityStates = useMemo(() => {
    const out: Record<string, { ring: Tone | null; sub?: string }> = {};
    access?.facilities.forEach((f) => {
      if (f.flooded_now) out[f.id] = { ring: "info", sub: undefined };
      else if (!f.accessible_now) out[f.id] = { ring: "crit" };
      else if (f.access_lost_in_min !== null || f.flood_in_min !== null) out[f.id] = { ring: "warn" };
      else out[f.id] = { ring: null };
    });
    return out;
  }, [access]);

  const rebuild = useCallback((group: string, list: ML.Marker[]) => {
    (markers.current[group] || []).forEach((mk) => mk.remove());
    markers.current[group] = list;
  }, []);

  useEffect(() => {
    const m = mapRef.current;
    if (!ready || !m) return;
    const maplibregl = getMaplibre();
    const make = (elm: HTMLElement, ll: [number, number], anchor: ML.PositionAnchor = "center") => new maplibregl.Marker({ element: elm, anchor }).setLngLat(ll).addTo(m);
    // facilities
    rebuild("facilities", !lay.facilities ? [] : (layers.facilities?.features || []).map((f) => {
      const p = f.properties as { id: string; facility_type: string; names: Record<string, string>; criticality: number };
      const st = facilityStates[p.id];
      const name = pickName(p.names, locale);
      // HTML markers have no label collision: on real (dense) data label only the most critical facilities and
      // those with an active state ring; every marker keeps its icon and accessible name
      const ll = f.geometry.coordinates as [number, number];
      const elm = featureMarker({ kind: p.facility_type, label: name, tone: p.criticality >= 90 ? "info" : "muted", showLabel: lay.labels, ring: st?.ring ?? null,
        ariaLabel: `${tf.has(p.facility_type) ? tf(p.facility_type) : p.facility_type}: ${name}`,
        priority: p.criticality + (st?.ring ? 100 : 0), minZoom: st?.ring || p.criticality >= 90 ? 0 : p.criticality >= 60 ? 14 : 15.2 });
      elm.addEventListener("click", (ev) => { ev.stopPropagation(); facilityPopup(p.id, ll, p.names, p.facility_type, p.criticality); });
      return make(elm, ll, "left");
    }));
    rebuild("sites", !lay.sites ? [] : (layers.task_sites?.features || []).map((f) => {
      const p = f.properties as { id: string; kind: string; names: Record<string, string> };
      return make(featureMarker({ kind: "SITE", label: pickName(p.names, locale), tone: "sim", showLabel: false,
        ariaLabel: `${tk.has(p.kind) ? tk(p.kind) : p.kind}: ${pickName(p.names, locale)}` }), f.geometry.coordinates as [number, number]);
    }));
    rebuild("bases", (layers.bases?.features || []).map((f) => {
      const p = f.properties as { id: string; names: Record<string, string> };
      return make(featureMarker({ kind: "BASE", label: pickName(p.names, locale), tone: "ok", showLabel: lay.labels, ariaLabel: `${tmap("base")}: ${pickName(p.names, locale)}`, priority: 300 }),
        f.geometry.coordinates as [number, number], "left");
    }));
    rebuild("bridges", (layers.bridges?.features || []).map((f) => {
      const p = f.properties as { id: string; segment_ids: string[]; names: Record<string, string> };
      const st = access?.edges[p.segment_ids?.[0]]?.state || "OPEN";
      const elm = featureMarker({ kind: "BRIDGE", label: p.id, tone: toneOf(st === "OPEN" ? "OPEN" : st), showLabel: true, ariaLabel: `${tmap("bridge")} ${p.id}`,
        priority: st === "OPEN" ? 120 : 260, minZoom: st === "OPEN" ? 13.5 : 0 });
      const ll = f.geometry.coordinates as [number, number];
      elm.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const T = live.current.tmap;
        popupRef.current?.setLngLat(ll).setHTML(`<div class="argus-pop"><div class="argus-pop-kind">${esc(T("bridge"))}</div><div class="argus-pop-title">${esc(pickName(p.names, localeRef.current, p.id))}</div><div class="argus-pop-row"><span>${esc(T("popup.state", { time: live.current.fmt(live.current.t) }))}</span><b>${esc(live.current.tr.has(st) ? live.current.tr(st) : st)}</b></div><div class="argus-pop-note">${esc(T("popup.bridgeNote"))}</div></div>`).addTo(mapRef.current as ML.Map);
      });
      return make(elm, ll, "left");
    }));
    // named-road labels with state + countdown (status is text, not colour only)
    const byRoad = new Map<string, { coords: [number, number][]; cls: string; names?: Record<string, string>; named: boolean }>();
    (layers.roads?.features || []).forEach((f) => {
      const p = f.properties as { road_id: string; road_class: string; names?: Record<string, string> };
      const rs = roadStates[p.road_id];
      const named = !!p.names?.original;
      if (!LABELED_CLASSES[p.road_class] && !(rs && rs.state !== "OPEN") && !named) return;
      const prev = byRoad.get(p.road_id);
      const coords = f.geometry.coordinates as [number, number][];
      if (!prev) byRoad.set(p.road_id, { coords: [...coords], cls: p.road_class, names: p.names, named });
      else prev.coords.push(...coords);
    });
    rebuild("roadLabels", !lay.labels ? [] : [...byRoad.entries()].map(([rid, v]) => {
      const rs = roadStates[rid] || { state: "OPEN", closes_in_min: null };
      const tone = toneOf(rs.state);
      const cls = LABELED_CLASSES[v.cls] || { p: 10, z: 15.3 };
      const active = rs.state !== "OPEN";
      return make(roadLabel({ id: rid, name: v.named ? pickName(v.names, locale, rid) : undefined, state: rs.state, stateText: tr(rs.state),
        countdown: rs.state === "CLOSES_IN" ? countdown(rs.closes_in_min) : undefined, tone,
        priority: cls.p + (active ? 200 : 0) + (v.named ? 5 : 0), minZoom: active ? 0 : cls.z }), lineMid(v.coords));
    }));
    requestAnimationFrame(() => declutter(m.getContainer(), m.getZoom()));
    rebuild("sectorLabels", !lay.sectors ? [] : (layers.sectors?.features || []).map((f) => {
      const p = f.properties as { id: string; names: Record<string, string> };
      const ring = (f.geometry.coordinates as [number, number][][])[0];
      const cx = ring.reduce((s, c) => s + c[0], 0) / ring.length;
      const cy = ring.reduce((s, c) => s + c[1], 0) / ring.length;
      const d = document.createElement("div");
      d.innerHTML = `<div style="font:700 11px Inter,Segoe UI,sans-serif;color:#7aa2c7;opacity:.9;text-shadow:0 1px 2px #000">${pickName(p.names, locale)}</div>`;
      return make(d, [cx, cy]);
    }));
  }, [ready, layers, lay.facilities, lay.sites, lay.labels, lay.sectors, facilityStates, roadStates, access, locale, rebuild, tr, tf, tk, tmap, facilityPopup]);

  useEffect(() => {
    const m = mapRef.current;
    if (!ready || !m) return;
    const maplibregl = getMaplibre();
    rebuild("points", overlays.points.map((p) => new maplibregl.Marker({ element: countdownMarker({ label: p.label, sub: p.sub, tone: p.tone }), anchor: "bottom" })
      .setLngLat([p.lon, p.lat]).addTo(m)));
  }, [ready, overlays.points, rebuild]);

  // ------------------------------------------------------------------ 2D / 3D + layer visibility
  useEffect(() => {
    const m = mapRef.current;
    if (!ready || !m) return;
    if (mapMode === "3d") {
      m.setTerrain({ source: "dem", exaggeration: 1.8 });
      try {
        m.setSky({ "sky-color": "#0d1b2c", "horizon-color": "#22384f", "fog-color": "#0c1219", "sky-horizon-blend": 0.6, "horizon-fog-blend": 0.7, "fog-ground-blend": 0.4 });
      } catch { /* older style spec */ }
      m.setLight({ anchor: "viewport", color: "#ffffff", intensity: 0.38, position: [1.3, 210, 35] });
      m.easeTo({ pitch: 60, bearing: -20, zoom: Math.max(m.getZoom(), 13.4), duration: 1200 });
    } else {
      m.setTerrain(null);
      m.easeTo({ pitch: 0, bearing: 0, duration: 800 });
    }
    if (m.getLayer("water-3d")) m.setLayoutProperty("water-3d", "visibility", mapMode === "3d" && lay.flood ? "visible" : "none");
  }, [ready, mapMode, lay.flood]);

  useEffect(() => {
    const m = mapRef.current;
    if (!ready || !m) return;
    const vis = (id: string, on: boolean) => m.getLayer(id) && m.setLayoutProperty(id, "visibility", on ? "visible" : "none");
    vis("carto", lay.basemap);
    vis("hillshade", lay.hillshade);
    vis("extent", lay.extent);
    vis("buildings", lay.buildings);
    ["roads-case", "roads-line", "roads-closed"].forEach((id) => vis(id, lay.roads));
    ["sectors-fill", "sectors-line"].forEach((id) => vis(id, lay.sectors));
    if (!lay.flood) { vis("flood-a", false); vis("flood-b", false); } else { vis("flood-a", true); vis("flood-b", true); }
  }, [ready, lay]);

  // decorative shoreline animation (visual effect only — see legend)
  useEffect(() => {
    const m = mapRef.current;
    if (!ready || !m || !lay.waterFx || !lay.extent) return;
    if (typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const seq: number[][] = [[0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0], [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2], [0, 2.5, 3, 1.5], [0, 3, 3, 1], [0, 3.5, 3, 0.5]];
    let i = 0;
    const id = setInterval(() => {
      if (!m.getLayer("extent")) return;
      m.setPaintProperty("extent", "line-dasharray", seq[i % seq.length]);
      i++;
    }, 110);
    return () => clearInterval(id);
  }, [ready, lay.waterFx, lay.extent]);

  return (
    <div className="absolute inset-0">
      <div ref={el} className="h-full w-full" aria-label={tmap("surface", { mode: scenario?.mode ?? "", member: scenario?.active_member ?? "" })} />
    </div>
  );
}
