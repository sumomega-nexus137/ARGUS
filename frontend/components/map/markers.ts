// DOM marker builders (no glyph server needed → labels work offline and are translatable).
import { TONE_HEX, type Tone } from "@/lib/status";

const ICONS: Record<string, string> = {
  HOSPITAL: '<path d="M10 4h4v6h6v4h-6v6h-4v-6H4v-4h6z"/>',
  CLINIC: '<path d="M10 4h4v6h6v4h-6v6h-4v-6H4v-4h6z"/>',
  CARE_HOME: '<path d="M12 3l9 8h-3v9h-5v-6h-2v6H6v-9H3z"/>',
  SCHOOL: '<path d="M12 3l10 5-10 5L2 8zm-6 8v4c0 2 3 4 6 4s6-2 6-4v-4l-6 3z"/>',
  SHELTER: '<path d="M12 3l10 9h-3v8H5v-8H2z"/>',
  WATER_SUPPLY: '<path d="M12 2c3 5 6 8 6 12a6 6 0 01-12 0c0-4 3-7 6-12z"/>',
  POWER: '<path d="M13 2L4 14h6l-1 8 9-12h-6z"/>',
  HEATING: '<path d="M12 2c2 4 6 6 6 11a6 6 0 01-12 0c0-3 2-5 3-7 0 2 1 3 2 3 0-3 0-5 1-7z"/>',
  FIRE_STATION: '<path d="M4 20V9l8-5 8 5v11h-6v-5h-4v5z"/>',
  ADMINISTRATION: '<path d="M3 20h18v-2H3zm2-3h2v-6H5zm4 0h2v-6H9zm4 0h2v-6h-2zm4 0h2v-6h-2zM12 2L2 8v2h20V8z"/>',
  BASE: '<path d="M4 4h16v16H4z" fill="none" stroke="currentColor" stroke-width="3"/><path d="M8 8h8v8H8z"/>',
  SITE: '<path d="M12 2l10 10-10 10L2 12z"/>',
  BRIDGE: '<path d="M2 14h20v2H2zm2-6c3 0 5 3 8 3s5-3 8-3v3c-3 0-5 3-8 3s-5-3-8-3z"/>',
  BOTTLENECK: '<path d="M4 4h16l-6 8 6 8H4l6-8z"/>',
  STATION: '<path d="M11 2h2v20h-2zM7 6h4v2H7zm0 4h4v2H7zm0 4h4v2H7z"/>',
  DEFAULT: '<circle cx="12" cy="12" r="6"/>',
};

function esc(s: string): string {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c] as string);
}

export function iconSvg(kind: string, color: string, size = 14): string {
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="${color}" style="color:${color};flex-shrink:0">${ICONS[kind] || ICONS.DEFAULT}</svg>`;
}

export function featureMarker(opts: { kind: string; label?: string; tone: Tone; showLabel: boolean; ring?: Tone | null; sub?: string; ariaLabel: string }): HTMLElement {
  const el = document.createElement("div");
  el.className = "argus-marker";
  el.setAttribute("role", "img");
  el.setAttribute("aria-label", opts.ariaLabel);
  const color = TONE_HEX[opts.tone];
  const ring = opts.ring ? `box-shadow:0 0 0 2px ${TONE_HEX[opts.ring]}, 0 0 10px ${TONE_HEX[opts.ring]};` : "";
  el.innerHTML = `<div style="display:flex;align-items:center;gap:4px;pointer-events:auto">
    <div style="display:grid;place-items:center;width:20px;height:20px;border-radius:4px;background:#0e141bf0;border:1px solid ${color};${ring}">${iconSvg(opts.kind, color, 13)}</div>
    ${opts.showLabel && opts.label ? `<div style="background:#0e141bd9;border:1px solid #2d3e52;border-radius:3px;padding:1px 5px;font:600 10.5px Inter,Segoe UI,sans-serif;color:#dbe4ee;white-space:nowrap;max-width:190px;overflow:hidden;text-overflow:ellipsis">${esc(opts.label)}${opts.sub ? `<span style="color:${opts.ring ? TONE_HEX[opts.ring] : "#a9b6c4"};font-weight:700"> · ${esc(opts.sub)}</span>` : ""}</div>` : ""}
  </div>`;
  return el;
}

export function roadLabel(opts: { id: string; state: string; stateText: string; countdown?: string; tone: Tone }): HTMLElement {
  const el = document.createElement("div");
  el.className = "argus-marker";
  const color = TONE_HEX[opts.tone];
  const open = opts.state === "OPEN";
  el.innerHTML = `<div style="display:flex;align-items:center;gap:0;font:700 10.5px Inter,Segoe UI,sans-serif;white-space:nowrap;border-radius:3px;overflow:hidden;border:1px solid ${open ? "#2d3e52" : color};background:#0e141be6">
    <span style="padding:1px 5px;color:#dbe4ee;background:#1b2531">${esc(opts.id)}</span>
    ${open ? "" : `<span style="padding:1px 5px;color:${color}">${esc(opts.stateText)}${opts.countdown ? ` ${esc(opts.countdown)}` : ""}</span>`}
  </div>`;
  return el;
}

export function countdownMarker(opts: { label: string; sub?: string; tone: Tone }): HTMLElement {
  const el = document.createElement("div");
  el.className = "argus-marker";
  const color = TONE_HEX[opts.tone];
  el.innerHTML = `<div style="transform:translateY(-18px);display:flex;flex-direction:column;align-items:center">
    <div style="background:#0b1016f2;border:1px solid ${color};border-radius:3px;padding:2px 6px;text-align:center;box-shadow:0 0 12px ${color}55">
      <div style="font:800 12px 'JetBrains Mono',Consolas,monospace;color:${color}">${esc(opts.label)}</div>
      ${opts.sub ? `<div style="font:600 9.5px Inter,Segoe UI,sans-serif;color:#a9b6c4;white-space:nowrap">${esc(opts.sub)}</div>` : ""}
    </div>
    <div style="width:1px;height:10px;background:${color}"></div>
  </div>`;
  return el;
}
