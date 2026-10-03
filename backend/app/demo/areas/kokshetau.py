"""KOKSHETAU / KYLSHAKTY — DEMO area specification (portability demonstration).

Archetype: urban snowmelt ponding + river overflow + bridge / underpass / culvert bottlenecks.
EVERYTHING here is SYNTHETIC DEMO DATA. No claim is made about the real city's hydraulics;
in particular ARGUS does not model Lake Kopa and makes no claim that it causes flooding.
"""

from __future__ import annotations

import numpy as np

from app.demo.terrain import Bowl


def river_y(x):  # type: ignore[no-untyped-def]
    x = np.asarray(x, dtype=float)
    return 250.0 * np.sin((x + 6000.0) / 1800.0) + 0.08 * x - 200.0 + 120.0 * np.sin((x + 900.0) / 520.0)


XS = [-3600, -2400, -1200, 0, 1200, 2400, 3600]
YN = [500, 1200, 2400, 3000]  # north bank rows (railway between 1200 and 2400 at y=1800)
YS = [-900, -1600, -2400]  # south bank rows


def _nodes() -> dict[str, tuple[float, float]]:
    nodes: dict[str, tuple[float, float]] = {}
    for x in XS:
        for y in YN + YS:
            nodes[f"K{x}_{y}"] = (float(x), float(y))
    extra = {
        # bridge heads
        "B1N": (0, 150), "B1S": (0, -560), "B2N": (1200, 180), "B2S": (1200, -620),
        "B3N": (3600, 250), "B3S": (3600, -560), "B4N": (-2400, 130), "B4S": (-2400, -560),
        # railway underpass (main avenue) and level crossings
        "UPN": (0, 1950), "UPS": (0, 1650), "LXW": (-2400, 1800), "LXE": (2400, 1800),
        # culvert on western ring road
        "CVN": (-3600, 1500), "CVS": (-3600, 900),
        # base / depot / facilities access
        "KB": (0, 800), "KD": (-2000, 3500),
        "WTP": (4300, -350),
    }
    nodes.update(extra)
    return nodes


NODES = _nodes()


def _row(y: int, name_prefix: str) -> dict:
    return {"id": f"{name_prefix}{abs(y)}", "class": "urban", "speed": 35, "embankment": 0.25,
            "names": {"kk": f"Көше {name_prefix}{abs(y)}", "ru": f"Улица {name_prefix}{abs(y)}",
                      "en": f"Street {name_prefix}{abs(y)}"},
            "nodes": [f"K{x}_{y}" for x in XS]}


ROADS: list[dict] = [
    # main avenue (x=0) with railway underpass and central bridge
    {"id": "KA1", "class": "urban_main", "speed": 45,
     "names": {"kk": "KA1 Абай даңғылы (DEMO)", "ru": "KA1 проспект Абая (DEMO)", "en": "KA1 Abay avenue (DEMO)"},
     "nodes": ["K0_3000", "K0_2400", "UPN", "UPS", "K0_1200", "KB", "K0_500", "B1N", "B1S", "K0_-900", "K0_-1600",
               "K0_-2400"],
     "segment_embankment": {"UPN>UPS": 0.0},
     "bridges": {"B1N>B1S": {"id": "KB1", "clearance": 2.3,
                              "names": {"kk": "KB1 орталық көпір", "ru": "KB1 центральный мост",
                                        "en": "KB1 central bridge"}}},
     "embankment": 0.4},
    {"id": "KA2", "class": "urban_main", "speed": 40,
     "names": {"kk": "KA2 Әуезов көшесі (DEMO)", "ru": "KA2 улица Ауэзова (DEMO)", "en": "KA2 Auezov street (DEMO)"},
     "nodes": ["K1200_500", "B2N", "B2S", "K1200_-900"],
     "segment_close_at_h": {"K1200_500>B2N": 1.45, "B2S>K1200_-900": 1.4},
     "bridges": {"B2N>B2S": {"id": "KB2", "clearance": 1.5,
                              "names": {"kk": "KB2 Әуезов көпірі", "ru": "KB2 мост по Ауэзова",
                                        "en": "KB2 Auezov bridge"}}}},
    {"id": "KA3", "class": "urban_main", "speed": 45,
     "names": {"kk": "KA3 шығыс даңғылы (DEMO)", "ru": "KA3 восточный проспект (DEMO)", "en": "KA3 eastern avenue (DEMO)"},
     "nodes": ["K3600_500", "B3N", "B3S", "K3600_-900"],
     "segment_close_at_h": {"K3600_500>B3N": 2.0, "B3S>K3600_-900": 1.95},
     "bridges": {"B3N>B3S": {"id": "KB3", "clearance": 1.9,
                              "names": {"kk": "KB3 шығыс көпірі", "ru": "KB3 восточный мост",
                                        "en": "KB3 eastern bridge"}}}},
    {"id": "KA4", "class": "urban_main", "speed": 40,
     "names": {"kk": "KA4 батыс көшесі (DEMO)", "ru": "KA4 западная улица (DEMO)", "en": "KA4 western street (DEMO)"},
     "nodes": ["K-2400_500", "B4N", "B4S", "K-2400_-900"],
     "segment_close_at_h": {"K-2400_500>B4N": 1.25, "B4S>K-2400_-900": 1.3},
     "bridges": {"B4N>B4S": {"id": "KB4", "clearance": 1.3,
                              "names": {"kk": "KB4 батыс көпірі", "ru": "KB4 западный мост",
                                        "en": "KB4 western bridge"}}}},
    {"id": "KR", "class": "urban_main", "speed": 50,
     "names": {"kk": "KR батыс айналма жолы (DEMO)", "ru": "KR западная объездная (DEMO)",
               "en": "KR western ring road (DEMO)"},
     "nodes": ["K-3600_3000", "K-3600_2400", "CVN", "CVS", "K-3600_500"], "embankment": 0.6,
     "segment_embankment": {"CVN>CVS": 0.15}},
    {"id": "KL", "class": "urban", "speed": 35,
     "names": {"kk": "KL деңгейлік өткелдер (DEMO)", "ru": "KL переезды (DEMO)", "en": "KL level crossings (DEMO)"},
     "nodes": ["K-2400_2400", "LXW", "K-2400_1200"], "embankment": 0.4},
    {"id": "KE", "class": "urban", "speed": 35,
     "names": {"kk": "KE шығыс өткел (DEMO)", "ru": "KE восточный переезд (DEMO)", "en": "KE eastern crossing (DEMO)"},
     "nodes": ["K2400_2400", "LXE", "K2400_1200"], "embankment": 0.4},
    {"id": "KD1", "class": "rural", "speed": 50,
     "names": {"kk": "KD1 қойма жолы", "ru": "KD1 дорога к складу", "en": "KD1 depot road"},
     "nodes": ["KD", "K-2400_3000"], "embankment": 1.0},
    {"id": "KW", "class": "urban", "speed": 35,
     "names": {"kk": "KW су тазарту жолы", "ru": "KW дорога к очистным", "en": "KW treatment plant road"},
     "nodes": ["K3600_500", "WTP", "B3S"], "segment_close_at_h": {"K3600_500>WTP": 1.45, "WTP>B3S": 1.4}},
]
for _y in YN:
    ROADS.append(_row(_y, "N"))
for _y in YS:
    ROADS.append(_row(_y, "S"))
for _x in XS:
    if _x == 0:
        continue
    north = [f"K{_x}_{y}" for y in YN if not (_x in (-2400, 2400) and y in (1200, 2400))]
    # columns ±2400 cross the railway via level crossings (KL/KE) so split them
    if _x in (-2400, 2400):
        ROADS.append({"id": f"C{_x}", "class": "urban", "speed": 35, "embankment": 0.25,
                      "names": {"kk": f"Көше C{_x}", "ru": f"Улица C{_x}", "en": f"Street C{_x}"},
                      "nodes": [f"K{_x}_500", f"K{_x}_1200"]})
        ROADS.append({"id": f"C{_x}", "class": "urban", "speed": 35, "embankment": 0.25,
                      "names": {"kk": f"Көше C{_x}", "ru": f"Улица C{_x}", "en": f"Street C{_x}"},
                      "nodes": [f"K{_x}_2400", f"K{_x}_3000"]})
    elif _x == -3600:
        pass  # ring road KR
    else:
        # columns without a railway crossing stop at 1200 and restart at 2400
        ROADS.append({"id": f"C{_x}", "class": "urban", "speed": 35, "embankment": 0.25,
                      "names": {"kk": f"Көше C{_x}", "ru": f"Улица C{_x}", "en": f"Street C{_x}"},
                      "nodes": [f"K{_x}_500", f"K{_x}_1200"]})
        ROADS.append({"id": f"C{_x}", "class": "urban", "speed": 35, "embankment": 0.25,
                      "names": {"kk": f"Көше C{_x}", "ru": f"Улица C{_x}", "en": f"Street C{_x}"},
                      "nodes": [f"K{_x}_2400", f"K{_x}_3000"]})
    ROADS.append({"id": f"C{_x}", "class": "urban", "speed": 35, "embankment": 0.25,
                  "names": {"kk": f"Көше C{_x}", "ru": f"Улица C{_x}", "en": f"Street C{_x}"},
                  "nodes": [f"K{_x}_{y}" for y in YS]})
ROADS.append({"id": "C0", "class": "urban", "speed": 35, "embankment": 0.25,
              "names": {"kk": "Көше C0", "ru": "Улица C0", "en": "Street C0"}, "nodes": []})
ROADS = [r for r in ROADS if len(r["nodes"]) >= 2]

SECTORS = [
    {"id": "KC", "names": {"kk": "Орталық", "ru": "Центр", "en": "City centre"},
     "polygon": [(-1800, 300), (1800, 300), (1800, 1750), (-1800, 1750)]},
    {"id": "KS", "names": {"kk": "Сол жағалау", "ru": "Левобережье", "en": "Left bank"},
     "polygon": [(-3000, -700), (3000, -700), (3000, -2700), (-3000, -2700)]},
    {"id": "KE", "names": {"kk": "Шығыс аудан", "ru": "Восточный район", "en": "Eastern district"},
     "polygon": [(1800, 300), (4600, 300), (4600, 1750), (1800, 1750)]},
    {"id": "KW", "names": {"kk": "Батыс аудан", "ru": "Западный район", "en": "Western district"},
     "polygon": [(-4200, 300), (-1800, 300), (-1800, 1750), (-4200, 1750)]},
    {"id": "KN", "names": {"kk": "Теміржолдың солтүстігі", "ru": "За железной дорогой", "en": "North of railway"},
     "polygon": [(-4200, 1850), (4200, 1850), (4200, 3300), (-4200, 3300)]},
]

BUILDING_ZONES = [
    {"sector": "KC", "spacing": 48, "floors": [2, 3, 5, 5, 9], "core": [(-900, 400), (900, 1600)], "core_floors": [5, 9, 9, 12]},
    {"sector": "KS", "spacing": 46, "floors": [1, 1, 2, 5]},
    {"sector": "KE", "spacing": 50, "floors": [1, 2, 5, 9]},
    {"sector": "KW", "spacing": 50, "floors": [1, 1, 2]},
    {"sector": "KN", "spacing": 55, "floors": [1, 2, 5]},
]

BASES = [
    {"id": "K-BASE", "names": {"kk": "ТЖД жедел әрекет ету орталығы (DEMO)", "ru": "Центр оперативного реагирования ДЧС (DEMO)",
                               "en": "Emergency response centre (DEMO)"}, "xy": (0, 800), "safe": True},
    {"id": "K-DEPOT", "names": {"kk": "Қалалық қойма (DEMO)", "ru": "Городской склад (DEMO)", "en": "City depot (DEMO)"},
     "xy": (-2000, 3500), "safe": True},
]

FACILITIES = [
    {"id": "KF-HOSP", "type": "HOSPITAL", "xy": (-600, 2700), "criticality": 100, "served": 150000, "sector": "KN",
     "names": {"kk": "Облыстық аурухана (DEMO)", "ru": "Областная больница (DEMO)", "en": "Regional hospital (DEMO)"}},
    {"id": "KF-MAT", "type": "HOSPITAL", "xy": (600, -1500), "criticality": 95, "served": 40000, "sector": "KS",
     "names": {"kk": "Перзентхана (DEMO)", "ru": "Родильный дом (DEMO)", "en": "Maternity hospital (DEMO)"}},
    {"id": "KF-WTP", "type": "WATER_SUPPLY", "xy": (4300, -350), "criticality": 90, "served": 140000, "sector": None,
     "names": {"kk": "Су тазарту құрылыстары (DEMO)", "ru": "Очистные сооружения (DEMO)",
               "en": "Water treatment plant (DEMO)"}},
    {"id": "KF-CHP", "type": "HEATING", "xy": (3000, -2400), "criticality": 85, "served": 120000, "sector": "KS",
     "names": {"kk": "ЖЭО (DEMO)", "ru": "ТЭЦ (DEMO)", "en": "Combined heat & power plant (DEMO)"}},
    {"id": "KF-FIRE", "type": "FIRE_STATION", "xy": (60, 860), "criticality": 90, "served": 150000, "sector": "KC",
     "names": {"kk": "Өрт сөндіру бөлімі (DEMO)", "ru": "Пожарная часть (DEMO)", "en": "Fire station (DEMO)"}},
    {"id": "KF-SCH", "type": "SHELTER", "xy": (-1200, -1600), "criticality": 70, "served": 1200, "sector": "KS",
     "names": {"kk": "№12 мектеп — пана (DEMO)", "ru": "Школа №12 — пункт размещения (DEMO)",
               "en": "School No. 12 — shelter (DEMO)"}},
    {"id": "KF-SUB", "type": "POWER", "xy": (-2400, -500), "criticality": 85, "served": 60000, "sector": None,
     "names": {"kk": "Батыс қосалқы станциясы (DEMO)", "ru": "Западная подстанция (DEMO)",
               "en": "Western substation (DEMO)"}},
]

TERRAIN = {
    "north_slope": 0.0035, "south_slope": 0.0030, "terrace_start": 2600.0, "terrace_slope": 0.006,
    "bankfull_ws_at_x0": 226.0, "ws_slope": 0.0006, "channel_half_width": 18.0, "channel_depth": 2.0,
    "noise_amp": 0.10, "noise_sigma": 4.0, "seed": 11,
    "bowls": [
        Bowl(0, 1800, 160, 110, -0.9),        # railway underpass dip
        Bowl(-3600, 1200, 220, 260, -0.7),    # culvert backwater hollow
        Bowl(900, -1300, 500, 350, -0.35),    # left-bank low district
        Bowl(4300, -350, 110, 90, 0.10),      # treatment plant pad
        Bowl(-2400, -500, 90, 90, 0.0),       # substation pad
    ],
}

# Snowmelt ponding: capacity (m) of urban depressions; filled by a SIMULATION snowmelt index.
PONDING = [
    {"x": 0, "y": 1800, "rx": 140, "ry": 90, "cap": 1.1},       # underpass
    {"x": -3600, "y": 1200, "rx": 200, "ry": 240, "cap": 0.7},  # culvert hollow
    {"x": 900, "y": -1300, "rx": 420, "ry": 300, "cap": 0.35},  # left-bank low district
    {"x": -1200, "y": 900, "rx": 260, "ry": 200, "cap": 0.25},  # centre courtyard hollows
    {"x": 2600, "y": 1000, "rx": 260, "ry": 220, "cap": 0.3},   # eastern hollow
]

TASK_SITES = [
    {"id": "KS-UNDERPASS", "kind": "DRAINAGE_POINT", "xy": (0, 1800), "sector": "KC", "work_limit": 0.60,
     "protects": {"sector_ids": ["KN"], "facility_ids": ["KF-HOSP"]},
     "names": {"kk": "Теміржол астындағы өткел", "ru": "Путепровод под железной дорогой", "en": "Railway underpass"}},
    {"id": "KS-CULVERT", "kind": "CULVERT", "xy": (-3600, 1200), "sector": "KW", "work_limit": 0.30,
     "protects": {"sector_ids": ["KW"]},
     "names": {"kk": "Батыс су өткізгіш құбыры", "ru": "Западная водопропускная труба", "en": "Western culvert"}},
    {"id": "KS-MAT", "kind": "FACILITY", "xy": (600, -1500), "sector": "KS", "work_limit": 0.25,
     "protects": {"facility_ids": ["KF-MAT"]},
     "names": {"kk": "Перзентхана", "ru": "Роддом", "en": "Maternity hospital"}},
    {"id": "KS-WTP", "kind": "FACILITY", "xy": (4300, -350), "sector": None, "work_limit": 0.20,
     "protects": {"facility_ids": ["KF-WTP"]},
     "names": {"kk": "Су тазарту құрылыстары", "ru": "Очистные сооружения", "en": "Water treatment plant"}},
    {"id": "KS-SUB", "kind": "FACILITY", "xy": (-2400, -500), "sector": None, "work_limit": 0.20,
     "protects": {"facility_ids": ["KF-SUB"]},
     "names": {"kk": "Батыс қосалқы станциясы", "ru": "Западная подстанция", "en": "Western substation"}},
    {"id": "KS-LEFT", "kind": "DRAINAGE_POINT", "xy": (900, -1300), "sector": "KS", "work_limit": 0.25,
     "protects": {"sector_ids": ["KS"]},
     "names": {"kk": "Сол жағалау ойпаңы", "ru": "Понижение левобережья", "en": "Left-bank low district"}},
    {"id": "KS-SCH", "kind": "FACILITY", "xy": (-1200, -1600), "sector": "KS", "work_limit": 0.30,
     "protects": {"facility_ids": ["KF-SCH"]},
     "names": {"kk": "№12 мектеп — пана", "ru": "Школа №12 — пункт размещения", "en": "School No. 12 — shelter"}},
]

STATIONS = [
    {"id": "HP-KYLSHAKTY-KOK", "xy": (-600, -180), "river": "Kylshakty", "bankfull": 300, "watch": 330,
     "warning": 380, "critical": 440,
     "names": {"kk": "Қылшықты — Көкшетау гидробекеті (DEMO)", "ru": "Кылшакты — гидропост Кокшетау (DEMO)",
               "en": "Kylshakty — Kokshetau hydropost (DEMO)"}},
]

HYDROLOGY = {
    "bankfull_cm": 300,
    "common": [(-6, 318), (-5, 322), (-4, 327)],
    "recession_base_cm": 320, "recession_tau_h": 10.0,
    "members": [
        {"id": "M1", "label": "Low", "s0": 342, "peak": 395, "tp": 12.0, "snow": 0.55},
        {"id": "M2", "label": "Below median", "s0": 346, "peak": 415, "tp": 11.0, "snow": 0.7},
        {"id": "M3", "label": "Median (issuance P50)", "s0": 350, "peak": 435, "tp": 10.0, "snow": 0.8},
        {"id": "M4", "label": "Above median", "s0": 355, "peak": 460, "tp": 9.0, "snow": 0.9},
        {"id": "M5", "label": "High", "s0": 361, "peak": 485, "tp": 8.5, "snow": 1.0},
        {"id": "M6", "label": "Extreme", "s0": 367, "peak": 510, "tp": 8.0, "snow": 1.0},
    ],
    "snowmelt_start_h": -3.0, "snowmelt_full_h": 9.0,
    "issued_member": "M3",
    "conditioned_member": "M3",
    "observations": [
        (-4.0, 327, "HYDROPOST", "VERIFIED", "Automatic hydropost (DEMO)"),
        (-3.0, 333, "HYDROPOST", "VERIFIED", "Automatic hydropost (DEMO)"),
        (-2.0, 339, "HYDROPOST", "VERIFIED", "Automatic hydropost (DEMO)"),
        (-1.0, 345, "HYDROPOST", "VERIFIED", "Automatic hydropost (DEMO)"),
        (-10 / 60, 349, "HYDROPOST", "VERIFIED", "Automatic hydropost (DEMO)"),
    ],
}

RESOURCES = [
    {"id": "KC1", "type": "CREW", "subtype": "ENGINEERING", "base": "K-BASE", "capacity": 6, "unit": "persons"},
    {"id": "KC2", "type": "CREW", "subtype": "GENERAL", "base": "K-BASE", "capacity": 4, "unit": "persons"},
    {"id": "KC3", "type": "CREW", "subtype": "RESCUE", "base": "K-BASE", "capacity": 5, "unit": "persons"},
    {"id": "KC4", "type": "CREW", "subtype": "ENGINEERING", "base": "K-DEPOT", "capacity": 6, "unit": "persons"},
    {"id": "KV1", "type": "VEHICLE", "subtype": "TRUCK", "base": "K-BASE", "capacity": 8, "unit": "t"},
    {"id": "KV2", "type": "VEHICLE", "subtype": "TRUCK", "base": "K-DEPOT", "capacity": 10, "unit": "t"},
    {"id": "KV3", "type": "VEHICLE", "subtype": "HIGH_CLEARANCE", "base": "K-BASE", "capacity": 3, "unit": "t"},
    {"id": "KV4", "type": "VEHICLE", "subtype": "PICKUP", "base": "K-BASE", "capacity": 1, "unit": "t"},
    {"id": "KEQ1", "type": "EQUIPMENT", "subtype": "EXCAVATOR", "base": "K-DEPOT", "capacity": None, "unit": None},
    {"id": "KEQ2", "type": "EQUIPMENT", "subtype": "SANDBAG_FILLER", "base": "K-BASE", "capacity": 600, "unit": "bags/h"},
] + [
    {"id": f"KP{i:02d}", "type": "PUMP", "subtype": "MOBILE_PUMP", "base": "K-BASE" if i <= 6 else "K-DEPOT",
     "capacity": 250, "unit": "m3/h"}
    for i in range(1, 11)
]

PLANS = [
    {"id": "plan-k1", "name": "Plan K-1", "description": "Kokshetau snowmelt response plan (DEMO)",
     "tasks": [
         {"code": "K1", "template": "ACT-PUMP-L", "site": "KS-UNDERPASS", "resources": ["KC1", "KV1", "KP01", "KP02", "KP03", "KP04"], "depart": "10:20"},
         {"code": "K2", "template": "ACT-CULVERT", "site": "KS-CULVERT", "resources": ["KC4", "KV2", "KEQ1"], "depart": "10:30"},
         {"code": "K3", "template": "ACT-SUPPLY", "site": "KS-MAT", "resources": ["KC3", "KV3"], "depart": "11:00"},
         {"code": "K4", "template": "ACT-PUMP-S", "site": "KS-WTP", "resources": ["KC2", "KV4", "KP05", "KP06"], "depart": "11:30"},
     ]},
]

EXTRA_CANDIDATES = [
    {"code": "K5", "template": "ACT-PUMP-M", "site": "KS-LEFT"},
    {"code": "K6", "template": "ACT-PUMP-S", "site": "KS-SUB"},
    {"code": "K7", "template": "ACT-PREPOS", "site": "KS-SCH"},
]

SPEC = {
    "id": "kokshetau",
    "sort_order": 2,
    "names": {"kk": "Көкшетау — Қылшықты", "ru": "Кокшетау — Кылшакты", "en": "Kokshetau — Kylshakty",
              "original": "Көкшетау"},
    "river_names": {"kk": "Қылшықты өзені", "ru": "река Кылшакты", "en": "Kylshakty River", "original": "Қылшықты"},
    "archetype": "URBAN_SNOWMELT_RIVER",
    "center": (69.3960, 53.2830),
    "epsg": 32642,
    "grid": {"x0": -6000.0, "y1": 5000.0, "res": 40.0, "nx": 300, "ny": 250},
    "river_y": river_y,
    "terrain": TERRAIN,
    "nodes": NODES,
    "roads": ROADS,
    "sectors": SECTORS,
    "building_zones": BUILDING_ZONES,
    "bases": BASES,
    "facilities": FACILITIES,
    "task_sites": TASK_SITES,
    "stations": STATIONS,
    "hydrology": HYDROLOGY,
    "resources": RESOURCES,
    "plans": PLANS,
    "extra_candidates": EXTRA_CANDIDATES,
    "bottlenecks": [
        {"id": "KBN-B1", "kind": "BRIDGE", "segments": ["B1N>B1S"], "bridge": "KB1",
         "names": {"kk": "KB1 орталық көпір", "ru": "Центральный мост KB1", "en": "Central bridge KB1"}},
        {"id": "KBN-B2", "kind": "BRIDGE", "segments": ["B2N>B2S"], "bridge": "KB2",
         "names": {"kk": "KB2 Әуезов көпірі", "ru": "Мост KB2 по Ауэзова", "en": "Auezov bridge KB2"}},
        {"id": "KBN-B3", "kind": "BRIDGE", "segments": ["B3N>B3S"], "bridge": "KB3",
         "names": {"kk": "KB3 шығыс көпірі", "ru": "Восточный мост KB3", "en": "Eastern bridge KB3"}},
        {"id": "KBN-B4", "kind": "BRIDGE", "segments": ["B4N>B4S"], "bridge": "KB4",
         "names": {"kk": "KB4 батыс көпірі", "ru": "Западный мост KB4", "en": "Western bridge KB4"}},
        {"id": "KBN-UP", "kind": "LOW_ROAD", "segments": ["UPN>UPS"],
         "names": {"kk": "Теміржол астындағы өткел", "ru": "Путепровод под ж/д", "en": "Railway underpass"}},
        {"id": "KBN-CV", "kind": "CULVERT", "segments": ["CVN>CVS"],
         "names": {"kk": "Батыс су өткізгіш құбыры", "ru": "Западная водопропускная труба", "en": "Western culvert"}},
        {"id": "KBN-CH", "kind": "CHANNEL_CONSTRAINT", "segments": ["K1200_500>B2N", "B2S>K1200_-900"],
         "names": {"kk": "KB2 маңындағы арна тарылуы", "ru": "Сужение русла у моста KB2",
                   "en": "Channel narrowing near KB2"},
         "notes": "Operational element only: if flagged constrained, the adjacent KB2 approaches are treated as unavailable. "
                  "ARGUS makes no hydrodynamic claim about the constraint."},
    ],
    "ponding": PONDING,
    "reference_time_local": "2026-04-12T10:00:00",
    "utc_offset_min": 300,
}
