"""Server-side, print-ready HTML briefing (kk / ru / en). Integration point for headless PDF rendering
(e.g. WeasyPrint or Chromium ``--print-to-pdf``) in production deployments."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jinja2 import Environment, select_autoescape

LABELS = {
    "kk": {"title": "Жедел брифинг", "area": "Операциялық аймақ", "status": "Жағдай", "scenario": "Сценарий",
           "time": "Операциялық уақыт", "demo": "DEMO ДЕРЕКТЕРІ / СИМУЛЯЦИЯ — нақты өлшемдер емес", "impact": "Ағымдағы әсер",
           "peak": "Болжамды шың", "buildings": "Зардап шеккен ғимараттар", "population": "Қауіпке ұшыраған халық (жиынтық)",
           "facilities": "Қауіп төнген маңызды нысандар", "exposure": "Активтердің ұшырауы", "damage": "Күтілетін залал",
           "roads": "Маңызды жолдар", "closes": "Жабылады", "closed": "Жабық", "restricted": "Шектелген",
           "sectors": "Секторларға қолжетімділік", "access_lost": "Қолжетімділік жоғалады", "isolated": "Оқшауланған",
           "plan": "Таңдалған жоспар", "health": "Жоспар күйі", "why": "Себеп тізбегі", "tasks": "Тапсырмалар",
           "latest": "Ең кеш қауіпсіз шығу", "stress": "Стресс-тест", "feasible_in": "орындалады",
           "alternatives": "Баламалар", "sources": "Деректер көздері", "assumptions": "Болжамдар", "models": "Модель нұсқалары",
           "none": "жоқ", "conflicts": "Ресурс қайшылықтары", "generated": "Құрастырылды", "range": "диапазон",
           "status_NORMAL": "ҚАЛЫПТЫ", "status_WATCH": "БАҚЫЛАУ", "status_WARNING": "ЕСКЕРТУ", "status_CRITICAL": "СЫНИ",
           "PLAN_VALID": "ЖОСПАР ЖАРАМДЫ", "PLAN_AT_RISK": "ЖОСПАР ҚАУІПТЕ"},
    "ru": {"title": "Оперативный брифинг", "area": "Операционный район", "status": "Обстановка", "scenario": "Сценарий",
           "time": "Операционное время", "demo": "ДЕМО-ДАННЫЕ / МОДЕЛИРОВАНИЕ — не реальные измерения", "impact": "Текущее воздействие",
           "peak": "Прогнозный пик", "buildings": "Затронутые здания", "population": "Население в зоне воздействия (агрегировано)",
           "facilities": "Критические объекты под угрозой", "exposure": "Подверженность активов", "damage": "Ожидаемый ущерб",
           "roads": "Критические дороги", "closes": "Закроется", "closed": "Закрыта", "restricted": "Ограничена",
           "sectors": "Доступ к секторам", "access_lost": "Потеря доступа", "isolated": "Изолирован",
           "plan": "Выбранный план", "health": "Состояние плана", "why": "Причинная цепочка", "tasks": "Задачи",
           "latest": "Последний безопасный выезд", "stress": "Стресс-тест", "feasible_in": "выполним в",
           "alternatives": "Альтернативы", "sources": "Источники данных", "assumptions": "Допущения", "models": "Версии моделей",
           "none": "нет", "conflicts": "Конфликты ресурсов", "generated": "Сформировано", "range": "диапазон",
           "status_NORMAL": "НОРМА", "status_WATCH": "НАБЛЮДЕНИЕ", "status_WARNING": "ПРЕДУПРЕЖДЕНИЕ", "status_CRITICAL": "КРИТИЧНО",
           "PLAN_VALID": "ПЛАН ВЫПОЛНИМ", "PLAN_AT_RISK": "ПЛАН ПОД УГРОЗОЙ"},
    "en": {"title": "Operational briefing", "area": "Operational area", "status": "Situation", "scenario": "Scenario",
           "time": "Operational time", "demo": "DEMO DATA / SIMULATION — not real measurements", "impact": "Current impact",
           "peak": "Forecast peak", "buildings": "Buildings affected", "population": "Population exposed (aggregated)",
           "facilities": "Critical facilities exposed", "exposure": "Asset exposure", "damage": "Expected damage",
           "roads": "Critical roads", "closes": "Closes", "closed": "Closed", "restricted": "Restricted",
           "sectors": "Sector access", "access_lost": "Access lost", "isolated": "Isolated",
           "plan": "Selected plan", "health": "Plan status", "why": "Causal chain", "tasks": "Tasks",
           "latest": "Latest safe departure", "stress": "Stress test", "feasible_in": "feasible in",
           "alternatives": "Alternatives", "sources": "Data sources", "assumptions": "Assumptions", "models": "Model versions",
           "none": "none", "conflicts": "Resource conflicts", "generated": "Generated", "range": "range",
           "status_NORMAL": "NORMAL", "status_WATCH": "WATCH", "status_WARNING": "WARNING", "status_CRITICAL": "CRITICAL",
           "PLAN_VALID": "PLAN VALID", "PLAN_AT_RISK": "PLAN AT RISK"},
}

TEMPLATE = """<!doctype html><html lang="{{ lang }}"><head><meta charset="utf-8"><title>ARGUS FloodOps — {{ L.title }}</title>
<style>
body{font-family:"Inter","Segoe UI",Arial,sans-serif;color:#111;margin:24px;font-size:12px}
h1{font-size:20px;margin:0}h2{font-size:14px;border-bottom:1px solid #999;margin-top:18px;padding-bottom:2px}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:3px 5px;text-align:left;vertical-align:top}
.demo{background:#fff4d6;border:1px solid #d9a400;padding:4px 8px;font-weight:600}.muted{color:#555}
.badge{display:inline-block;padding:1px 6px;border:1px solid #333;font-weight:700}
@media print{body{margin:10mm}}
</style></head><body>
<h1>ARGUS FloodOps — {{ L.title }}</h1>
<div class="muted">{{ L.area }}: <b>{{ area_name }}</b> · {{ L.time }}: {{ fmt(r.op_time) }} ({{ r.clock_mode }}) · {{ L.generated }}: {{ fmt(r.generated_at) }}</div>
{% if r.area.is_demo %}<p class="demo">{{ L.demo }}</p>{% endif %}
<p>{{ L.status }}: <span class="badge">{{ L['status_' + r.status] }}</span> · {{ L.scenario }}: {{ r.scenario.name }} ({{ r.scenario.mode }}, {{ r.scenario.member }}, {{ r.scenario.model_version }})</p>
<h2>{{ L.impact }} / {{ L.peak }}</h2>
<table><tr><th></th><th>{{ L.impact }}</th><th>{{ L.peak }} ({{ rel(r.impact_peak.t_min) }})</th></tr>
<tr><td>{{ L.buildings }}</td><td>{{ r.impact_now.buildings.affected }}</td><td>{{ r.impact_peak.buildings.affected }}</td></tr>
<tr><td>{{ L.population }}</td><td>{{ r.impact_now.population.exposed }}</td><td>{{ r.impact_peak.population.exposed }}</td></tr>
<tr><td>{{ L.facilities }}</td><td>{{ r.impact_now.facilities_exposed }}</td><td>{{ r.impact_peak.facilities_exposed }}</td></tr>
<tr><td>{{ L.exposure }} ({{ L.range }}, KZT)</td><td>{{ money(r.impact_now.economic.asset_exposure) }}</td><td>{{ money(r.impact_peak.economic.asset_exposure) }}</td></tr>
<tr><td>{{ L.damage }} ({{ L.range }}, KZT)</td><td>{{ money(r.impact_now.economic.expected_damage) }}</td><td>{{ money(r.impact_peak.economic.expected_damage) }}</td></tr></table>
<h2>{{ L.roads }}</h2><table>{% for x in r.critical_roads %}<tr><td>{{ x.road_id }}</td><td>{{ name(x.names) }}</td><td>{{ x.state }}</td><td>{% if x.closes_at is not none %}{{ L.closes }} {{ rel(x.closes_at) }}{% endif %}</td></tr>{% else %}<tr><td>{{ L.none }}</td></tr>{% endfor %}</table>
<h2>{{ L.sectors }}</h2><table>{% for s in r.sectors %}<tr><td>{{ name(s.names) }}</td><td>{% if s.isolated_now %}{{ L.isolated }}{% elif s.access_lost_at is not none %}{{ L.access_lost }} {{ rel(s.access_lost_at) }}{% else %}—{% endif %}</td><td>{{ s.population }}</td></tr>{% endfor %}</table>
{% if r.plan %}<h2>{{ L.plan }}: {{ r.plan.name }} v{{ r.plan.version }} — {{ L[r.plan.health] if r.plan.health else '' }}</h2>
{% for c in r.plan.chains %}<p><b>{{ L.why }} ({{ c.task }}):</b> {% for n in c.nodes %}{{ n.type }}{% if n.params.road %} {{ n.params.road }}{% endif %}{% if n.params.resource %} {{ n.params.resource }}{% endif %}{% if n.params.task %} {{ n.params.task }}{% endif %}{% if not loop.last %} → {% endif %}{% endfor %}</p>{% endfor %}
<table><tr><th>{{ L.tasks }}</th><th>{{ L.status }}</th><th>{{ L.latest }}</th><th>ETA</th></tr>{% for t in r.plan.tasks %}<tr><td>{{ t.code }} · {{ t.template_id }} · {{ t.site_id }}</td><td>{{ t.status }}</td><td>{{ rel(t.latest_departure) }}</td><td>{{ rel(t.arrival) }}</td></tr>{% endfor %}</table>
{% endif %}
{% if r.stress_test %}<h2>{{ L.stress }}</h2><p>{{ r.stress_test.n_feasible }} / {{ r.stress_test.n_scenarios }} ({{ L.feasible_in }})</p>{% endif %}
{% if r.alternatives %}<h2>{{ L.alternatives }} ({{ r.alternatives.policy }})</h2><table>{% for a in r.alternatives.alternatives %}<tr><td>{{ a.id }} {{ a.label }}</td><td>{{ a.status }}</td><td>{{ a.metrics.tasks_selected }}</td><td>{% if a.robustness %}{{ a.robustness.n_feasible }}/{{ a.robustness.n_scenarios }}{% endif %}</td></tr>{% endfor %}</table>{% endif %}
<h2>{{ L.sources }}</h2><table>{% for s in r.data_sources %}<tr><td>{{ s.layer }}</td><td>{{ s.source }}</td><td>{{ s.mode }}</td><td>{{ s.freshness }}</td><td>{{ fmt(s.last_success_at) if s.last_success_at else '—' }}</td></tr>{% endfor %}</table>
<h2>{{ L.assumptions }}</h2><ul>{% for n in r.assumptions.notes %}<li>{{ n }}</li>{% endfor %}</ul>
<h2>{{ L.models }}</h2><p>{% for m in r.model_versions %}{{ m.component }} {{ m.version }}{% if not loop.last %} · {% endif %}{% endfor %}</p>
</body></html>"""


def render(report: dict, lang: str) -> str:
    lang = lang if lang in LABELS else "kk"
    tz = timezone(timedelta(minutes=report["area"].get("utc_offset_min") or 0))
    ref = datetime.fromisoformat(report["reference_time"])

    def fmt(iso: str | None) -> str:
        if not iso:
            return "—"
        return datetime.fromisoformat(iso).astimezone(tz).strftime("%d.%m.%Y %H:%M")

    def rel(m: float | None) -> str:
        if m is None:
            return "—"
        return (ref + timedelta(minutes=float(m))).astimezone(tz).strftime("%H:%M")

    def money(r: dict) -> str:
        return f"{r['low'] / 1e6:,.0f}–{r['high'] / 1e6:,.0f} mln"

    def name(n: dict) -> str:
        return n.get(lang) or n.get("kk") or n.get("ru") or n.get("original") or ""

    env = Environment(autoescape=select_autoescape(["html"]))
    tpl = env.from_string(TEMPLATE)
    return tpl.render(r=report, L=LABELS[lang], lang=lang, fmt=fmt, rel=rel, money=money, name=name,
                      area_name=name(report["area"]["names"]))
