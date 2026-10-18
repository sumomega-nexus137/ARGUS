"""Impact assumptions. ALL values are DEMO / illustrative and are exposed to users verbatim.

Replace them with an approved valuation and depth–damage methodology for real deployments.
Economic outputs are always ranges: ASSET EXPOSURE ≠ EXPECTED DAMAGE ≠ MODELLED AVOIDABLE LOSS.
"""

from __future__ import annotations

import numpy as np

CURRENCY = "KZT"
AFFECTED_DEPTH_M = 0.10
FACILITY_EXPOSED_DEPTH_M = 0.10
DEPTH_CLASSES = [(0.10, 0.5), (0.5, 1.0), (1.0, 2.0), (2.0, 99.0)]

# replacement value per m² floor area (low, high) — DEMO assumption, not an official valuation
UNIT_VALUE_KZT_M2 = {
    "residential": (180_000, 260_000),
    "commercial": (230_000, 330_000),
    "public": (250_000, 360_000),
    "industrial": (140_000, 220_000),
}

# illustrative generic depth–damage curve (fraction of replacement value), with ±30 % uncertainty
DAMAGE_CURVE = [(0.0, 0.0), (0.1, 0.05), (0.5, 0.20), (1.0, 0.35), (1.5, 0.45), (2.0, 0.55), (3.0, 0.70), (5.0, 0.85)]
DAMAGE_UNCERTAINTY = 0.30
PERSONS_PER_M2 = 1 / 32.0

METHODOLOGY = {
    "status": "DEMO",
    "exposure": "Asset exposure = Σ (floor area × replacement value per m²) over buildings whose sampled flood depth ≥ "
                f"{AFFECTED_DEPTH_M} m. Range from low/high unit values.",
    "damage": "Expected damage = Σ (replacement value × damage fraction(depth)). Damage fraction from an illustrative "
              f"generic depth–damage curve with ±{int(DAMAGE_UNCERTAINTY * 100)} % uncertainty.",
    "avoidable": "Modelled avoidable loss = expected damage in assets protected by completed actions × expert-defined "
                 "damage-reduction range of the action template. Reported only for plans.",
    "population": "Exposed population = zone population × (affected residential floor area ÷ residential floor area "
                  "in zone). Aggregated; no personal data.",
    "depth_sampling": "Depth sampled at building centroids from the scenario surface (grid resolution applies).",
    "limitations": [
        "Unit values and damage curve are DEMO placeholders, not an approved methodology.",
        "Contents, business interruption and indirect losses are not included.",
        "Point sampling can miss partial inundation of large footprints.",
    ],
}


def damage_fraction(depth: np.ndarray) -> np.ndarray:
    xs = np.array([p[0] for p in DAMAGE_CURVE])
    ys = np.array([p[1] for p in DAMAGE_CURVE])
    return np.interp(np.clip(depth, 0, None), xs, ys)


def unit_values(uses: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    lo = np.array([UNIT_VALUE_KZT_M2.get(u, UNIT_VALUE_KZT_M2["residential"])[0] for u in uses], dtype=float)
    hi = np.array([UNIT_VALUE_KZT_M2.get(u, UNIT_VALUE_KZT_M2["residential"])[1] for u in uses], dtype=float)
    return lo, hi


def as_dict() -> dict:
    return {
        "currency": CURRENCY,
        "affected_depth_m": AFFECTED_DEPTH_M,
        "facility_exposed_depth_m": FACILITY_EXPOSED_DEPTH_M,
        "depth_classes_m": DEPTH_CLASSES,
        "unit_value_kzt_m2": UNIT_VALUE_KZT_M2,
        "damage_curve": DAMAGE_CURVE,
        "damage_uncertainty": DAMAGE_UNCERTAINTY,
        "persons_per_m2": PERSONS_PER_M2,
        "methodology": METHODOLOGY,
    }


def round_sig(x: float, sig: int = 2) -> float:
    if not x or not np.isfinite(x):
        return 0.0
    return float(round(x, -int(np.floor(np.log10(abs(x)))) + (sig - 1)))
