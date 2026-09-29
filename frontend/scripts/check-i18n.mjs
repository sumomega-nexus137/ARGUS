// i18n completeness check: identical key sets in kk / ru / en, no empty values, and every static
// t("key") used in the source resolves to an existing message. Run: npm run i18n:check
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";

const root = new URL("..", import.meta.url).pathname;
const locales = ["kk", "ru", "en"];
const msgs = Object.fromEntries(locales.map((l) => [l, JSON.parse(readFileSync(join(root, "messages", `${l}.json`), "utf8"))]));

function flatten(obj, prefix = "") {
  const out = {};
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object") Object.assign(out, flatten(v, key));
    else out[key] = v;
  }
  return out;
}

const flat = Object.fromEntries(locales.map((l) => [l, flatten(msgs[l])]));
let problems = 0;
const ref = new Set(Object.keys(flat.en));
for (const l of locales) {
  const keys = new Set(Object.keys(flat[l]));
  for (const k of ref) if (!keys.has(k)) { console.error(`[${l}] missing key: ${k}`); problems++; }
  for (const k of keys) if (!ref.has(k)) { console.error(`[${l}] extra key (not in en): ${k}`); problems++; }
  for (const [k, v] of Object.entries(flat[l])) {
    if (typeof v !== "string" || !v.trim()) { console.error(`[${l}] empty value: ${k}`); problems++; }
  }
}

// ICU placeholders must match across locales (except plural-internal '#')
const ph = (s) => new Set([...String(s).matchAll(/\{(\w+)\s*[,}]/g)].map((m) => m[1]));
for (const k of ref) {
  const base = ph(flat.en[k]);
  for (const l of ["kk", "ru"]) {
    const other = ph(flat[l][k] ?? "");
    for (const p of base) if (!other.has(p)) { console.error(`[${l}] placeholder {${p}} missing in ${k}`); problems++; }
  }
}

// static usage check
function walk(dir, files = []) {
  for (const f of readdirSync(dir)) {
    if (["node_modules", ".next", "scripts", "messages"].includes(f)) continue;
    const p = join(dir, f);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, files);
    else if (/\.(tsx|ts)$/.test(f)) files.push(p);
  }
  return files;
}
let used = 0;
for (const file of walk(root)) {
  const src = readFileSync(file, "utf8");
  // resolve each call to the nearest preceding binding of the same name (function-scope approximation)
  const bindings = [...src.matchAll(/const\s+(\w+)\s*=\s*useTranslations\(\s*"([\w.]+)"\s*\)/g)].map((m) => ({ name: m[1], ns: m[2], at: m.index }));
  for (const name of new Set(bindings.map((b) => b.name))) {
    const re = new RegExp(`\\b${name}(?:\\.rich|\\.has)?\\(\\s*"([\\w.]+)"`, "g");
    for (const m of src.matchAll(re)) {
      const b = bindings.filter((x) => x.name === name && x.at < m.index).pop();
      if (!b) continue;
      used++;
      const key = `${b.ns}.${m[1]}`;
      if (!ref.has(key)) { console.error(`${file.replace(root, "")}: unknown key ${key}`); problems++; }
    }
  }
}
console.log(`i18n: ${ref.size} keys × ${locales.length} locales, ${used} static usages checked, ${problems} problem(s)`);
process.exit(problems ? 1 : 0);
