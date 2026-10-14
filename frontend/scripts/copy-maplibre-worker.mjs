// Copies MapLibre's ES-module worker (+ shared chunk) into /public so it can be served same-origin
// (works offline and independently of the bundler). Runs on postinstall.
import { copyFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const src = join(root, "node_modules", "maplibre-gl", "dist");
const dst = join(root, "public", "maplibre");
mkdirSync(dst, { recursive: true });
for (const f of ["maplibre-gl-worker.mjs", "maplibre-gl-shared.mjs"]) copyFileSync(join(src, f), join(dst, f));
console.log("maplibre worker copied to public/maplibre");
