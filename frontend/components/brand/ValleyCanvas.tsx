"use client";

import { useEffect, useRef } from "react";

import s from "./valley.module.css";

/**
 * Illustrative valley model for the landing hero: a height field with contour lines, water that rises and falls between
 * them, and one road whose lowest point floods first. The countdown is computed from the animated rise rate — it is an
 * illustration (labelled as such on the page), not a forecast.
 */

const GW = 264;
const GH = 176;
const LEVELS = Array.from({ length: 15 }, (_, i) => 0.1 + i * 0.055);
const CYCLE_S = 22; // one rise-and-fall
const MODEL_MIN_PER_S = 36; // illustrative clock: 1 real second ≈ 36 model minutes

function hash(x: number, y: number) {
  const h = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return h - Math.floor(h);
}
function noise(x: number, y: number) {
  const xi = Math.floor(x), yi = Math.floor(y);
  const xf = x - xi, yf = y - yi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
  const a = hash(xi, yi), b = hash(xi + 1, yi), c = hash(xi, yi + 1), d = hash(xi + 1, yi + 1);
  return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
}
function fbm(x: number, y: number) {
  let f = 0, amp = 0.5, fr = 1;
  for (let i = 0; i < 4; i++) { f += amp * noise(x * fr, y * fr); amp *= 0.5; fr *= 2.03; }
  return f;
}
const riverY = (x: number) => 0.54 + 0.13 * Math.sin(x * 5.6 + 0.4) + 0.045 * Math.sin(x * 14 + 1.1);
function height(x: number, y: number) {
  const d = Math.abs(y - riverY(x));
  return 0.06 + d * 1.25 + 0.16 * fbm(x * 3.2 + 4, y * 3.2 + 1) + 0.05 * (1 - x);
}

// road: crosses the valley diagonally, on a low embankment
const ROAD: [number, number][] = Array.from({ length: 40 }, (_, i) => {
  const x = 0.03 + (i / 39) * 0.94;
  return [x, 0.16 + 0.72 * x + 0.035 * Math.sin(x * 9)];
});
const roadH = (x: number, y: number) => height(x, y) + 0.1;

const levelAt = (t: number) => 0.13 + 0.25 * (0.5 - 0.5 * Math.cos((2 * Math.PI * t) / CYCLE_S));
const rateAt = (t: number) => 0.25 * 0.5 * Math.sin((2 * Math.PI * t) / CYCLE_S) * ((2 * Math.PI) / CYCLE_S);

export function ValleyCanvas({ labels }: { labels: { closesIn: string; closed: string; open: string; level: string; site: string } }) {
  const wrap = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const chip = useRef<HTMLDivElement>(null);
  const gauge = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const cv = canvas.current, box = wrap.current;
    if (!cv || !box) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    // height grid + contours (marching squares), computed once
    const hg = new Float32Array(GW * GH);
    for (let j = 0; j < GH; j++) for (let i = 0; i < GW; i++) hg[j * GW + i] = height(i / (GW - 1), j / (GH - 1));
    const segs: { major: boolean; pts: number[] }[] = LEVELS.map((lv, li) => {
      const pts: number[] = [];
      const lerp = (a: number, b: number) => (lv - a) / (b - a);
      for (let j = 0; j < GH - 1; j++) for (let i = 0; i < GW - 1; i++) {
        const a = hg[j * GW + i], b = hg[j * GW + i + 1], c = hg[(j + 1) * GW + i + 1], d = hg[(j + 1) * GW + i];
        const e: number[] = [];
        if ((a < lv) !== (b < lv)) e.push(i + lerp(a, b), j);
        if ((b < lv) !== (c < lv)) e.push(i + 1, j + lerp(b, c));
        if ((d < lv) !== (c < lv)) e.push(i + lerp(d, c), j + 1);
        if ((a < lv) !== (d < lv)) e.push(i, j + lerp(a, d));
        if (e.length >= 4) pts.push(e[0], e[1], e[2], e[3]);
        if (e.length === 8) pts.push(e[4], e[5], e[6], e[7]);
      }
      return { major: li % 4 === 0, pts };
    });

    const water = document.createElement("canvas");
    water.width = GW; water.height = GH;
    const wctx = water.getContext("2d")!;
    const img = wctx.createImageData(GW, GH);
    const base = document.createElement("canvas");
    const contourLayer = document.createElement("canvas");
    let w = 0, h = 0, dpr = 1;

    const paintBase = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = box.clientWidth; h = box.clientHeight;
      cv.width = base.width = contourLayer.width = Math.round(w * dpr); cv.height = base.height = contourLayer.height = Math.round(h * dpr);
      const cl = contourLayer.getContext("2d")!;
      cl.setTransform(dpr, 0, 0, dpr, 0, 0); cl.clearRect(0, 0, w, h);
      const b = base.getContext("2d")!;
      b.setTransform(dpr, 0, 0, dpr, 0, 0);
      b.fillStyle = "#f4f7fb"; b.fillRect(0, 0, w, h);
      const sx = w / (GW - 1), sy = h / (GH - 1);
      for (const s of segs) {
        b.beginPath();
        for (let k = 0; k < s.pts.length; k += 4) { b.moveTo(s.pts[k] * sx, s.pts[k + 1] * sy); b.lineTo(s.pts[k + 2] * sx, s.pts[k + 3] * sy); }
        b.strokeStyle = s.major ? "rgba(15,34,56,0.32)" : "rgba(15,34,56,0.14)";
        b.lineWidth = s.major ? 1.1 : 0.7; b.stroke();
        cl.beginPath();
        for (let k = 0; k < s.pts.length; k += 4) { cl.moveTo(s.pts[k] * sx, s.pts[k + 1] * sy); cl.lineTo(s.pts[k + 2] * sx, s.pts[k + 3] * sy); }
        cl.strokeStyle = "rgba(255,255,255,0.9)"; cl.lineWidth = s.major ? 1 : 0.6; cl.stroke();
      }
      // graticule ticks on the frame
      b.fillStyle = "rgba(15,34,56,0.45)";
      for (let k = 1; k < 8; k++) { b.fillRect((w * k) / 8, 0, 1, 7); b.fillRect((w * k) / 8, h - 7, 1, 7); }
      for (let k = 1; k < 6; k++) { b.fillRect(0, (h * k) / 6, 7, 1); b.fillRect(w - 7, (h * k) / 6, 7, 1); }
    };

    const draw = (t: number) => {
      const lv = levelAt(t), rate = rateAt(t);
      // water, shaded by depth
      const d = img.data;
      for (let p = 0, q = 0; p < hg.length; p++, q += 4) {
        const depth = lv - hg[p];
        if (depth <= 0) { d[q + 3] = 0; continue; }
        const k = Math.min(depth / 0.22, 1);
        const edge = Math.min(depth / 0.012, 1); // feathered shoreline
        d[q] = 150 - 131 * k; d[q + 1] = 205 - 143 * k; d[q + 2] = 245 - 120 * k; d[q + 3] = (170 + 60 * k) * edge;
      }
      wctx.putImageData(img, 0, 0);
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.drawImage(base, 0, 0);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.imageSmoothingEnabled = true;
      ctx.drawImage(water, 0, 0, w, h);
      // contours stay readable through the water (bathymetry feel)
      ctx.globalAlpha = 0.35; ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.drawImage(contourLayer, 0, 0); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.globalAlpha = 1;

      // road: casing, then open / flooded spans
      let minH = Infinity, minPt: [number, number] = ROAD[0];
      ctx.lineCap = "round"; ctx.lineJoin = "round";
      ctx.beginPath(); ROAD.forEach(([x, y], i) => (i ? ctx.lineTo(x * w, y * h) : ctx.moveTo(x * w, y * h)));
      ctx.strokeStyle = "#0f2238"; ctx.lineWidth = 6.5; ctx.stroke();
      ctx.strokeStyle = "#ffffff"; ctx.lineWidth = 3.6; ctx.stroke();
      for (let i = 1; i < ROAD.length; i++) {
        const [x0, y0] = ROAD[i - 1], [x1, y1] = ROAD[i];
        const rh = roadH((x0 + x1) / 2, (y0 + y1) / 2);
        if (rh < minH) { minH = rh; minPt = [(x0 + x1) / 2, (y0 + y1) / 2]; }
        if (rh < lv) {
          ctx.beginPath(); ctx.moveTo(x0 * w, y0 * h); ctx.lineTo(x1 * w, y1 * h);
          ctx.strokeStyle = "#d9480f"; ctx.lineWidth = 4.2; ctx.setLineDash([5, 4]); ctx.stroke(); ctx.setLineDash([]);
        }
      }
      // work site on the far bank
      const [sxp, syp] = [0.66 * w, 0.17 * h];
      ctx.save(); ctx.translate(sxp, syp); ctx.rotate(Math.PI / 4);
      ctx.fillStyle = "#ffffff"; ctx.strokeStyle = "#0f2238"; ctx.lineWidth = 1.5;
      ctx.fillRect(-6, -6, 12, 12); ctx.strokeRect(-6, -6, 12, 12); ctx.restore();
      ctx.font = "600 11px 'Onest Variable', 'Segoe UI', sans-serif"; ctx.fillStyle = "#0f2238";
      ctx.fillText(`T1 · ${labels.site}`, sxp + 12, syp + 4);
      // marker at the lowest point of the road
      ctx.beginPath(); ctx.arc(minPt[0] * w, minPt[1] * h, 5, 0, Math.PI * 2);
      ctx.fillStyle = minH < lv ? "#d9480f" : "#0f2238"; ctx.fill();

      // HUD (DOM, crisp text)
      if (chip.current) {
        let text: string, state: string;
        if (minH < lv) { text = `R37 · ${labels.closed}`; state = "closed"; }
        else if (rate > 1e-4) {
          const mins = Math.round(((minH - lv) / rate) * MODEL_MIN_PER_S);
          text = `R37 · ${labels.closesIn} ${String(Math.floor(mins / 60)).padStart(2, "0")}:${String(mins % 60).padStart(2, "0")}`;
          state = mins < 90 ? "soon" : "open";
        } else { text = `R37 · ${labels.open}`; state = "open"; }
        if (chip.current.textContent !== text) chip.current.textContent = text;
        chip.current.dataset.state = state;
      }
      if (gauge.current) gauge.current.style.setProperty("--lv", String((lv - 0.13) / 0.25));
    };

    paintBase();
    let raf = 0, visible = true, last = performance.now(), clock = CYCLE_S * 0.18;
    const loop = (now: number) => {
      clock += Math.min((now - last) / 1000, 0.1);
      last = now;
      draw(clock);
      raf = visible ? requestAnimationFrame(loop) : 0;
    };
    if (reduce) draw(CYCLE_S * 0.42);
    else raf = requestAnimationFrame(loop);

    const io = new IntersectionObserver(([e]) => {
      visible = e.isIntersecting;
      if (visible && !raf && !reduce) { last = performance.now(); raf = requestAnimationFrame(loop); }
    });
    io.observe(box);
    const ro = new ResizeObserver(() => { paintBase(); draw(reduce ? CYCLE_S * 0.42 : clock); });
    ro.observe(box);
    return () => { cancelAnimationFrame(raf); io.disconnect(); ro.disconnect(); };
  }, [labels]);

  return (
    <div ref={wrap} className={s.valley}>
      <canvas ref={canvas} className={s.valleyCanvas} aria-hidden />
      <div ref={chip} className={s.chip} data-state="open" aria-live="off" />
      <div className={s.gauge} aria-hidden>
        <span className={s.gaugeLabel}>{labels.level}</span>
        <div ref={gauge} className={s.gaugeTrack}><div className={s.gaugeFill} /></div>
      </div>
    </div>
  );
}
