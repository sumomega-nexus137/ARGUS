"""Transparent value model for candidate tasks.

ARGUS never decides moral priorities. It computes three *policy-independent* benefit components
per candidate task from scenario data, and the HUMAN chooses the policy weights:

* life      — people in protected sectors exposed at the scenario peak (+ vulnerable facility occupants)
* infra     — expert-defined criticality of protected facilities, scaled by how threatened they are
* economic  — expected damage (mid-range) in protected assets at the scenario peak

Each component is normalised to 0–100 across the candidate set. Action-type benefit shares are
DEMO assumptions stated below and shown in every explanation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from app.repositories.context import AreaContext
from app.services.impact import assumptions as A
from app.services.impact.engine import building_levels, point_levels
from app.services.routing.access import AccessModel, safe_base_nodes
from app.services.routing.intervals import INF
from app.services.scenario.runtime import ScenarioRuntime

POLICIES: dict[str, dict[str, int]] = {
    "LIFE_SAFETY": {"life": 70, "infra": 20, "economic": 10},
    "CRITICAL_INFRASTRUCTURE": {"life": 20, "infra": 65, "economic": 15},
    "ECONOMIC_LOSS": {"life": 15, "infra": 20, "economic": 65},
    "BALANCED": {"life": 40, "infra": 35, "economic": 25},
}

# share of the protected benefit attributed to an action type (DEMO assumption, configurable)
BENEFIT_SHARE: dict[str, dict[str, float]] = {
    "PUMP_DEPLOYMENT": {"life": 0.5, "infra": 0.8, "economic": 0.35},
    "LEVEE_REINFORCEMENT": {"life": 0.8, "infra": 0.8, "economic": 0.55},
    "RESOURCE_PREPOSITIONING": {"life": 0.6, "infra": 0.0, "economic": 0.0},
    "SUPPLY_DELIVERY": {"life": 0.4, "infra": 0.5, "economic": 0.0},
    "ROAD_CLOSURE": {"life": 0.3, "infra": 0.0, "economic": 0.0},
    "CULVERT_CLEARING": {"life": 0.4, "infra": 0.6, "economic": 0.45},
}
DEFAULT_SHARE = {"life": 0.3, "infra": 0.3, "economic": 0.3}

# people directly at risk inside facilities (DEMO factors)
FACILITY_OCCUPANTS = {"CARE_HOME": 3.0, "HOSPITAL": 0.012, "CLINIC": 0.01, "SHELTER": 0.3, "SCHOOL": 0.3}
# nominal asset value of a critical facility at criticality 100 (DEMO assumption, KZT)
FACILITY_ASSET_VALUE_KZT = 50_000_000


@dataclass
class ValueComponents:
    code: str
    life_raw: float
    infra_raw: float
    economic_raw: float
    life: float = 0.0
    infra: float = 0.0
    economic: float = 0.0
    threatened_facilities: list[str] | None = None
    protected_sectors: list[str] | None = None
    exposed_population: int = 0
    expected_damage_mid: float = 0.0

    def score(self, weights: dict[str, float]) -> float:
        tot = sum(weights.values()) or 1.0
        return (weights.get("life", 0) * self.life + weights.get("infra", 0) * self.infra
                + weights.get("economic", 0) * self.economic) / tot

    def as_dict(self) -> dict:
        return asdict(self)


def normalise_weights(w: dict | None, policy: str) -> dict[str, float]:
    base = dict(POLICIES.get(policy, POLICIES["BALANCED"]))
    if w:
        base.update({k: float(v) for k, v in w.items() if k in ("life", "infra", "economic")})
    tot = sum(base.values()) or 1.0
    return {k: round(100.0 * v / tot, 2) for k, v in base.items()}


def compute_values(ctx: AreaContext, rt: ScenarioRuntime, model: AccessModel, candidates: list[dict]) -> dict[str, ValueComponents]:
    member = rt.member
    times = tuple(float(x) for x in rt.frame_offsets if x >= model.now)
    if not times:
        times = (float(rt.frame_offsets[-1]),)
    lv = building_levels(ctx, rt, member, times)
    depth = np.where(np.isfinite(lv), np.clip(lv, 0, None), 0.0)
    peak = depth.max(axis=1) if depth.size else np.array([])
    b = ctx.buildings
    affected = peak >= A.AFFECTED_DEPTH_M
    lo, hi = A.unit_values(b.use)
    dmg_mid = b.floor_area * (lo + hi) / 2 * A.damage_fraction(peak)
    sec = np.array([s or "" for s in b.sector])

    pop_exposed: dict[str, float] = {}
    for z in ctx.zones:
        if not z.sector or z.residential_idx.size == 0:
            continue
        fa = b.floor_area[z.residential_idx]
        tot = float(fa.sum())
        if tot > 0:
            share = float(fa[affected[z.residential_idx]].sum()) / tot
            pop_exposed[z.sector] = pop_exposed.get(z.sector, 0.0) + z.population * share * (1 + z.vulnerable_share)

    fac_ids = list(ctx.facilities)
    fl = point_levels(rt, member, [ctx.facilities[f].x for f in fac_ids], [ctx.facilities[f].y for f in fac_ids],
                      np.asarray(times))
    fac_peak = {f: float(np.nanmax(np.where(np.isfinite(fl[i]), fl[i], -9.0))) if fl.size else -9.0
                for i, f in enumerate(fac_ids)}
    loss = model.access_loss(safe_base_nodes(ctx))
    fac_threat = {}
    for f in fac_ids:
        if fac_peak[f] >= A.FACILITY_EXPOSED_DEPTH_M:
            fac_threat[f] = 1.0
        elif loss.get(ctx.facilities[f].node, INF) <= rt.horizon_end:
            fac_threat[f] = 0.5
        else:
            fac_threat[f] = 0.1

    out: dict[str, ValueComponents] = {}
    for c in candidates:
        tpl = ctx.templates.get(c["template"])
        site = ctx.sites.get(c["site"])
        if tpl is None or site is None:
            continue
        share = BENEFIT_SHARE.get(tpl.action_type, DEFAULT_SHARE)
        prot = site.attrs.get("protects") or {}
        sectors = list(prot.get("sector_ids") or [])
        facs = list(prot.get("facility_ids") or [])
        life = sum(pop_exposed.get(s, 0.0) for s in sectors)
        infra = 0.0
        econ = float(dmg_mid[np.isin(sec, sectors) & affected].sum()) if sectors else 0.0
        for f in facs:
            fi = ctx.facilities.get(f)
            if fi is None:
                continue
            infra += float(fi.attrs.get("criticality") or 0) * fac_threat.get(f, 0.1)
            life += FACILITY_OCCUPANTS.get(fi.kind, 0.0) * float(fi.attrs.get("population_served") or 0) * fac_threat.get(f, 0.1)
            econ += FACILITY_ASSET_VALUE_KZT * fac_threat.get(f, 0.1) * (float(fi.attrs.get("criticality") or 0) / 100)
        out[c["code"]] = ValueComponents(
            c["code"], life * share["life"], infra * share["infra"], econ * share["economic"],
            threatened_facilities=[f for f in facs if fac_threat.get(f, 0) >= 0.5], protected_sectors=sectors,
            exposed_population=int(round(sum(pop_exposed.get(s, 0.0) for s in sectors), -1)),
            expected_damage_mid=A.round_sig(econ),
        )
    for comp in ("life", "infra", "economic"):
        mx = max((getattr(v, f"{comp}_raw") for v in out.values()), default=0.0)
        for v in out.values():
            setattr(v, comp, round(100.0 * getattr(v, f"{comp}_raw") / mx, 1) if mx > 0 else 0.0)
    return out
