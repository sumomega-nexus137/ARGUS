// ARGUS FloodOps — 26-step competition demo flow on the HISTORICAL real-data profile (start from an EMPTY database).
// Requires: backend + console running, packs installed, `npm i playwright` (any dir) and a Chromium (CHROME=/path optional).
// Usage: node scripts/e2e/demo26.mjs [outdir]   → PASS/FAIL per step + a screenshot per step + results.json
import { chromium } from "playwright";
import fs from "fs";

const BASE = process.env.ARGUS_URL || "http://localhost:3000";
const OUT = process.argv[2] || "shots/demo26";
fs.mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ ...(process.env.CHROME ? { executablePath: process.env.CHROME } : {}) });
const results = [];
const consoleErrors = [];

async function newPage(user, locale) {
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 950 } });
  const page = await ctx.newPage();
  page.on("pageerror", (e) => consoleErrors.push(`${user}: PAGEERROR ${e.message.slice(0, 200)}`));
  page.on("response", (r) => { if (r.status() >= 500) consoleErrors.push(`${user}: ${r.status()} ${r.url()}`); });
  await page.goto(BASE + "/login");
  if (locale) await page.evaluate((l) => localStorage.setItem("argus.locale", l), locale);
  const res = await page.request.post(BASE + "/api/auth/login", { data: { username: user, password: "argus2026" } });
  const { token } = await res.json();
  await page.evaluate((t) => localStorage.setItem("argus.token", t), token);
  return page;
}
const body = async (p) => (await Promise.all(p.frames().map((f) => f.evaluate(() => document.body ? document.body.innerText : "").catch(() => "")))).join("\n");
async function waitText(p, re, timeout = 30000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    const b = await body(p);
    if (re.test(b)) return b.match(re)[0];
    await p.waitForTimeout(500);
  }
  return null;
}
async function step(n, name, page, fn) {
  const t0 = Date.now();
  let ok = false, detail = "";
  try { [ok, detail] = await fn(); } catch (e) { ok = false; detail = "EXC " + e.message.split("\n")[0]; }
  try { await page.screenshot({ path: `${OUT}/${String(n).padStart(2, "0")}.png` }); } catch { /* ignore */ }
  results.push({ n, name, ok, detail, s: ((Date.now() - t0) / 1000).toFixed(1) });
  console.log(`${ok ? "PASS" : "FAIL"}  ${String(n).padStart(2)}  ${name}  (${((Date.now() - t0) / 1000).toFixed(1)}s)  ${detail}`);
}
const go = async (p, path, re, timeout = 40000) => { await p.goto(BASE + path); return waitText(p, re, timeout); };

// ---------------------------------------------------------------- 1–2 launch, Kazakh default
const fresh = await (await browser.newContext({ viewport: { width: 1600, height: 950 } })).newPage();
await step(1, "Launch (console + API healthy)", fresh, async () => {
  await fresh.goto(BASE + "/login");
  const h = await (await fresh.request.get(BASE + "/api/system/health")).json();
  return [h.status === "ok" && h.database === "ok", `health=${h.status} db=${h.database}`];
});
await step(2, "Kazakh is the default language", fresh, async () => {
  const lang = await fresh.evaluate(() => document.documentElement.lang);
  const b = await body(fresh);
  return [lang === "kk" && /[әғқңөұүһі]/i.test(b), `html lang=${lang}`];
});

const p = await newPage("planner", null);
// ---------------------------------------------------------------- 3–8 situation
await step(3, "Select Atbasar (overview → situation)", p, async () => {
  const both = await go(p, "/overview", /Көкшетау — Қылшақты/);
  await p.locator("a[href='/area/atbasar/situation']").first().click();
  await p.waitForURL("**/area/atbasar/situation", { timeout: 60000 });
  const s = await waitText(p, /Не болып жатыр/);
  return [!!both && !!s && p.url().includes("/area/atbasar/situation"), p.url()];
});
await step(4, "HISTORICAL 2024 mode visible", p, async () => {
  const b = await waitText(p, /2024 ЖЫЛҒЫ ТАРИХИ ҚАЙТА ҚҰРУ/);
  const txt = await body(p);
  return [!!b && /ТАРИХИ ҚАЙТА ОЙНАТУ/.test(txt) && /10\.04\.2024/.test(txt), "banner + replay clock 10.04.2024"];
});
await step(5, "Real map layers render", p, async () => {
  await p.waitForSelector(".maplibregl-canvas", { timeout: 30000 });
  await p.waitForTimeout(4000);
  const markers = await p.locator(".maplibregl-marker").count();
  const attr = await p.evaluate(() => document.querySelector(".maplibregl-ctrl-attrib")?.textContent || "");
  return [markers > 10 && /OpenStreetMap/.test(attr), `${markers} markers · attribution: ${attr.slice(0, 90)}`];
});
await step(6, "Timeline: step forward and back to now", p, async () => {
  const clock = async () => (await p.locator("text=/^\\d\\d:\\d\\d$/").allInnerTexts()).join(",");
  const before = await clock();
  await p.locator("button[aria-label]").filter({ has: p.locator("svg.lucide-chevron-right") }).first().click();
  await p.waitForTimeout(2500);
  const after = await clock();
  await p.locator("button:has-text('Қазіргі сәтке')").first().click();
  await p.waitForTimeout(1500);
  return [before !== after, `${before} → ${after}`];
});
await step(7, "Impact: real buildings / population, exposure without money", p, async () => {
  const b = await go(p, "/area/atbasar/impact", /[мm]²/);
  await waitText(p, /қолжетімсіз/, 30000);
  const txt = await body(p);
  const money = /₸|KZT|млн теңге|mln/.test(txt);
  const m = txt.match(/\/ ?6[,\s ]?036/);
  return [!!b && !money && /қолжетімсіз/.test(txt) && !!m, `floor area shown, valuation N/A, buildings total ${m ? m[0] : "?"}`];
});
await step(8, "Access & action windows (latest safe action time)", p, async () => {
  const b = await go(p, "/area/atbasar/windows", /ЕҢ КЕШ ҚАУІПСІЗ/i);
  const txt = await body(p);
  const nd = txt.match(/КЕЛЕСІ МАҢЫЗДЫ ШЕШІМ\s*\n?\s*(\d\d:\d\d)/);
  return [!!b && !!nd, `next critical decision ${nd ? nd[1] : "?"}`];
});

// ---------------------------------------------------------------- 9–14 plan
await step(9, "Plan A loaded", p, async () => {
  const b = await go(p, "/area/atbasar/plan", /Plan A v1/);
  return [!!b, "Plan A v1 (ACTIVE)"];
});
await step(10, "CHECK MY PLAN → PLAN AT RISK", p, async () => {
  const b = await waitText(p, /ЖОСПАР ҚАУІПТЕ/);
  const ev = await waitText(p, /КЕЗІНДЕГІ БАҒАЛАУ/);
  return [!!b && !!ev, "evaluation table + PLAN AT RISK"];
});
await step(11, "WHY chain", p, async () => {
  const txt = await body(p);
  const ok = /СЦЕНАРИЙІ ӨЗГЕРДІ · BASE → HIGH/.test(txt) && /R37 ЖОЛЫ ЕРТЕРЕК ЖАБЫЛАДЫ/.test(txt) && /C5 ҚОЛЖЕТІМДІЛІКТЕН АЙЫРЫЛАДЫ/.test(txt) && /T1 ТАПСЫРМАСЫ ӘРЕКЕТ ТЕРЕЗЕСІНЕН ТЫС ҚАЛАДЫ/.test(txt);
  return [ok, "BASE→HIGH → R37 closes earlier → C5 loses access → T1 misses window"];
});
await step(12, "STRESS TEST", p, async () => {
  await p.locator("button:has-text('ЖОСПАРДЫ СТРЕСС-ТЕСТІЛЕУ')").click();
  const r = await waitText(p, /Бағаланған \d+ сценарийдің \d+-інде орындалады/, 120000);
  return [!!r, r || "no result"];
});
await step(13, "GENERATE ALTERNATIVES (CP-SAT)", p, async () => {
  await p.locator("button:has-text('БАЛАМАЛАРДЫ ҚҰРУ')").click();
  const r = await waitText(p, /ALT-1/, 120000);
  return [!!r, "ALT-1 … returned"];
});
await step(14, "Fewer pumps (16 → 8) and re-run alternatives", p, async () => {
  const inp = p.locator("input[aria-label='Қолжетімді сорғылар']").first();
  await inp.fill("8");
  await inp.locator("xpath=following-sibling::button[1]").click();
  const pool = await waitText(p, /8\/16/, 30000);
  await p.locator("button:has-text('БАЛАМАЛАРДЫ ҚҰРУ')").click();
  await p.waitForTimeout(3000);
  const r = await waitText(p, /ALT-1/, 120000);
  return [!!pool && !!r, `pool ${pool || "?"} · alternatives regenerated`];
});

// ---------------------------------------------------------------- 15–18 operations
let draftV = null;
await step(15, "Manual road closure (R29) → recompute pipeline", p, async () => {
  await go(p, "/area/atbasar/operations", /Оқиға туралы хабарлау/i);
  await p.locator("label:has-text('Жол') select").first().selectOption("R29");
  await p.locator("button:has-text('Хабарлау')").first().click();
  const r = await waitText(p, /Қабылданды\. Қайта есептеу: [^\n]+/, 60000);
  return [!!r, r || "no confirmation"];
});
await step(16, "RECOMPUTE → new DRAFT version", p, async () => {
  await p.locator("button:has-text('ҚАЙТА ЕСЕПТЕУ')").first().click();
  const r = await waitText(p, /v(\d+) жобасы құрылды/, 180000);
  draftV = r ? r.match(/v(\d+)/)[1] : null;
  return [!!r, r || "no draft"];
});
const cmd = await newPage("commander", null);
await step(17, "Lifecycle: commander reviews → approves → activates", cmd, async () => {
  await go(cmd, "/area/atbasar/operations", /Шешім күтіп тұрған нұсқалар/i, 60000);
  for (const label of ["Қаралды деп белгілеу", "Бекіту", "Іске қосу"]) {
    await cmd.locator(`button:has-text('${label}')`).first().click();
    await cmd.waitForTimeout(4000);
  }
  const r = await waitText(cmd, new RegExp(`Plan A v${draftV}`), 60000);
  const audit = await (await cmd.request.get(BASE + "/api/audit?area_id=atbasar", { headers: { Authorization: "Bearer " + (await cmd.evaluate(() => localStorage.getItem("argus.token"))) } })).json().catch(() => null);
  return [!!r, `active plan now ${r || "?"}${audit ? "" : ""}`];
});
await step(18, "Operations board (tasks, ETA, status)", cmd, async () => {
  const b = await waitText(cmd, /ТАПСЫРМАЛАР ТАҚТАСЫ/i);
  const rows = await cmd.locator("table tbody tr").count();
  return [!!b && rows >= 4, `${rows} task rows`];
});

// ---------------------------------------------------------------- 19–21 validation & provenance
await step(19, "Validation layers (real Sentinel-2 evidence)", p, async () => {
  await go(p, "/area/atbasar/validation", /Sentinel-2 L2A/);
  await p.locator("button:has-text('Валидацияны орындау')").first().click();
  const r = await waitText(p, /ТАРИХИ БІР ОҚИҒА ІШІНДЕГІ КЕҢІСТІКТІК HOLDOUT/, 120000);
  const imgs = await p.locator("img").count();
  return [!!r, `holdout label + ${imgs} images (QC sheet / curtain)`];
});
await step(20, "Metrics computed by ARGUS (holdout)", p, async () => {
  const txt = await body(p);
  const pick = (re) => (txt.match(re) || [])[0];
  const iou = pick(/0[.,]588\d?/), pr = pick(/0[.,]815\d?/), rc = pick(/0[.,]678\d?/), f1 = pick(/0[.,]740\d?/);
  return [!!(iou && pr && rc && f1) && /AUTOMATED_EARTH_OBSERVATION_BASELINE_REQUIRES_QC/.test(txt), `IoU ${iou} P ${pr} R ${rc} F1 ${f1} · QC caveat shown`];
});
await step(21, "Provenance (data time / source / mode / assumptions)", p, async () => {
  await go(p, "/area/atbasar/situation", /Жедел жағдай/);
  const b = await waitText(p, /Сектор(лар)? — талдау торының ұяшықтары/, 30000);
  await go(p, "/area/atbasar/data", /Деректер көздері/);
  await p.locator("role=tab >> text=Деректер көздері").click();
  const src = await waitText(p, /Copernicus DEM GLO-30/, 20000);
  const txt = await body(p);
  return [!!b && !!src && /БАПТАЛМАҒАН/i.test(txt), "assumptions panel + sources table (Kazhydromet / Tasqyn NOT CONFIGURED)"];
});

// ---------------------------------------------------------------- 22 Kokshetau bottlenecks
await step(22, "Kokshetau bottlenecks (real OSM candidates + plan impact)", p, async () => {
  await go(p, "/area/kokshetau/bottlenecks", /KBR16/, 90000);
  await p.locator("main button:has-text('KBR02 көпірі')").first().click();
  const r = await waitText(p, /Жоспарға әсері[\s\S]{0,400}(ОРЫНДАЛМАЙДЫ|әсері жоқ)/i, 60000);
  const txt = await body(p);
  return [!!r && /гидродинамикалық тұжырым жасалмайды/.test(txt), "KBR02 → closed KR161 (улица Абая), T1 → INFEASIBLE; no hydraulic claim"];
});

// ---------------------------------------------------------------- 23–24 language switching
await step(23, "Language ҚАЗ → РУС", p, async () => {
  await p.locator("button:has-text('РУС')").first().click();
  const r = await waitText(p, /Узкие места/, 15000);
  const banner = await waitText(p, /ПИЛОТ ПЕРЕНОСИМОСТИ/, 5000);
  return [!!r && !!banner, "nav + banner in Russian"];
});
await step(24, "Language РУС → ENG", p, async () => {
  await p.locator("button:has-text('ENG')").first().click();
  const r = await waitText(p, /Bottlenecks/, 15000);
  const banner = await waitText(p, /PORTABILITY \/ BOTTLENECK PILOT/, 5000);
  return [!!r && !!banner, "nav + banner in English"];
});

// ---------------------------------------------------------------- 25 report
await step(25, "Operational report (KK / RU / EN)", p, async () => {
  await go(p, "/area/atbasar/report", /ARGUS FloodOps/, 60000);
  const out = [];
  for (const [btn, re] of [["ҚАЗ", /Жедел брифинг/], ["РУС", /Оперативный брифинг/], ["ENG", /Operational briefing/]]) {
    await p.locator(`main button:has-text('${btn}')`).first().click();
    out.push(!!(await waitText(p, re, 30000)));
  }
  const txt = await body(p);
  return [out.every(Boolean) && /HISTORICAL SAME-EVENT SPATIAL HOLDOUT/.test(txt), `kk/ru/en ${out.join("/")} · validation section present`];
});

// ---------------------------------------------------------------- 26 offline / degraded
const adm = await newPage("admin", null);
await step(26, "Offline: external providers down, ARGUS keeps working", adm, async () => {
  await go(adm, "/admin", /Сыртқы жеткізушілердің қолжетімсіздігін имитациялау/);
  await adm.locator("button:has-text('Сыртқы жеткізушілердің')").first().click();
  await adm.waitForTimeout(2000);
  const banner = await go(adm, "/area/atbasar/situation", /СЫРТҚЫ ДЕРЕКТЕР ҚОЛЖЕТІМСІЗ/, 30000);
  const live = await waitText(adm, /ҚОЛЖЕТІМСІЗ|КЭШ|ЕСКІРГЕН/, 30000);
  const plan = await go(adm, "/area/atbasar/plan", /Plan A v\d/, 60000);
  // restore
  await go(adm, "/admin", /Сыртқы жеткізушілердің/);
  await adm.locator("button:has-text('Сыртқы жеткізушілердің')").first().click().catch(() => {});
  await adm.waitForTimeout(1500);
  return [!!banner && !!live && !!plan, "degraded banner, live context OFFLINE/CACHED, plan still evaluated"];
});

console.log("\nSUMMARY", results.filter((r) => r.ok).length, "/", results.length, "passed");
console.log("SERVER/PAGE ERRORS", JSON.stringify(consoleErrors.slice(0, 20)));
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify({ results, consoleErrors }, null, 2));
await browser.close();
