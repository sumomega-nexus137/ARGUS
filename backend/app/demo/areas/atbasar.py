"""ATBASAR / ZHABAI — DEMO area specification.

EVERYTHING in this file is SYNTHETIC DEMO DATA placed around the real town location for
geographic context only. Geometry, terrain, populations, resources and hydrographs are NOT
surveyed or measured values. Real datasets replace these via the provider / import contracts.

Coordinates are local metres (x east, y north) relative to the area centre.
"""

from __future__ import annotations

import numpy as np

from app.demo.terrain import Bowl


def river_y(x):  # type: ignore[no-untyped-def]
    x = np.asarray(x, dtype=float)
    return 350.0 * np.sin((x + 7000.0) / 2600.0) - 0.04 * x - 100.0 + 110.0 * np.sin((x + 400.0) / 620.0)


def _n(*names: str) -> list[str]:
    return list(names)


GRID_X = [-1500, -1000, -500, 0, 500, 1000, 1500]
GRID_Y = [700, 1100, 1500, 1900]


def _grid_nodes() -> dict[str, tuple[float, float]]:
    nodes = {}
    for x in GRID_X:
        for y in GRID_Y:
            nodes[f"G{x}_{y}"] = (float(x), float(y))
    return nodes


NODES: dict[str, tuple[float, float]] = {
    # R1 northern highway
    "W1": (-7800, 2250), "D1": (-5000, 2450), "N2": (-2000, 2420), "N3": (-1500, 2410),
    "N4": (0, 2400), "N5": (1500, 2390), "N6": (3500, 2360), "N7": (6500, 2300), "E1": (7800, 2280),
    "DP": (-5000, 2620),
    # R2 main street / bridge B1 / south
    "BA": (0, 1700), "R2a": (0, 320), "B1S": (0, -200), "R2b": (0, -900), "R2c": (0, -2200), "S0": (0, -4200),
    # R4 riverside street (Sector A)
    "R4w": (-1500, 520), "R4b": (-1000, 460), "R4c": (-500, 400), "R4d": (500, 240), "R4e": (1000, 160),
    "R4f": (1500, 80),
    # R7 floodplain road → Sector B
    "R7a": (700, -620), "R7b": (1400, -960), "R7c": (2100, -1180), "SB": (2600, -1300),
    # Sector B streets
    "SB1": (2300, -1560), "SB2": (2950, -1520), "SB3": (2700, -1080),
    # R9 south terrace field road, R8 east road, bridge B2
    "R9a": (3800, -1760), "R9b": (5200, -1600), "R8b": (6500, -1180), "B2S": (6500, -840), "B2N": (6500, -520),
    "R8a": (6500, 900),
    # R3 / R11 west (Sector C, depot)
    "R3a": (-2200, 1100), "R3b": (-3000, 900), "SC": (-3400, 800), "SC1": (-3700, 640), "R3c": (-4200, 1000),
    "R11b": (-5000, 1500),
    # industrial access
    "IN1": (2600, 2250),
    **_grid_nodes(),
}

# Road definitions. ``close_at_h`` = bankfull-relative water level (m) at which the segment's
# lowest point reaches the closure depth (tunes a DEMO embankment height). ``None`` → default
# embankment. Bridge segments close when the water level exceeds deck clearance.
ROADS: list[dict] = [
    {"id": "R1", "class": "highway", "speed": 80,
     "names": {"kk": "R1 солтүстік тас жолы", "ru": "R1 северная трасса", "en": "R1 northern highway"},
     "nodes": _n("W1", "D1", "N2", "N3", "N4", "N5", "IN1", "N6", "N7", "E1"), "embankment": 1.5},
    {"id": "R11", "class": "rural", "speed": 50,
     "names": {"kk": "R11 қойма жолы", "ru": "R11 дорога к складу", "en": "R11 depot road"},
     "nodes": _n("DP", "D1"), "embankment": 1.0},
    {"id": "R2", "class": "urban_main", "speed": 40,
     "names": {"kk": "R2 орталық көше", "ru": "R2 центральная улица", "en": "R2 main street"},
     "nodes": _n("N4", "G0_1900", "BA", "G0_1500", "G0_1100", "G0_700", "R2a", "B1S", "R2b", "R2c", "S0"),
     "segment_close_at_h": {"G0_700>R2a": 2.75, "B1S>R2b": 2.45, "R2b>R2c": 2.9},
     "bridges": {"R2a>B1S": {"id": "B1", "clearance": 3.4,
                              "names": {"kk": "B1 орталық көпір", "ru": "B1 центральный мост",
                                        "en": "B1 central bridge"}}}},
    {"id": "R4", "class": "urban", "speed": 30,
     "names": {"kk": "R4 жағалау көшесі", "ru": "R4 набережная", "en": "R4 riverside street"},
     "nodes": _n("R4w", "R4b", "R4c", "R2a", "R4d", "R4e", "R4f"), "close_at_h": 2.15},
    {"id": "R7", "class": "rural", "speed": 50,
     "names": {"kk": "R7 жайылма жолы", "ru": "R7 пойменная дорога", "en": "R7 floodplain road"},
     "nodes": _n("B1S", "R7a", "R7b", "R7c", "SB"),
     "segment_close_at_h": {"B1S>R7a": 2.4, "R7a>R7b": 2.02, "R7b>R7c": 2.05, "R7c>SB": 2.3}},
    {"id": "R10", "class": "urban", "speed": 30,
     "names": {"kk": "R10 B секторының көшелері", "ru": "R10 улицы сектора B", "en": "R10 Sector B streets"},
     "nodes": _n("SB3", "SB", "SB1", "SB2", "SB"), "embankment": 0.5},
    {"id": "R9", "class": "track", "speed": 25,
     "names": {"kk": "R9 террасалық дала жолы", "ru": "R9 полевая дорога по террасе",
               "en": "R9 terrace field road"},
     "nodes": _n("SB2", "R9a", "R9b", "R8b"), "embankment": 1.0},
    {"id": "R8", "class": "rural", "speed": 60,
     "names": {"kk": "R8 шығыс жолы", "ru": "R8 восточная дорога", "en": "R8 eastern road"},
     "nodes": _n("N7", "R8a", "B2N", "B2S", "R8b"),
     "segment_close_at_h": {"R8a>B2N": 2.5, "B2S>R8b": 2.5},
     "bridges": {"B2N>B2S": {"id": "B2", "clearance": 2.1,
                             "names": {"kk": "B2 ескі шығыс көпірі", "ru": "B2 старый восточный мост",
                                       "en": "B2 old eastern bridge"}}}},
    {"id": "R3", "class": "rural", "speed": 50,
     "names": {"kk": "R3 батыс жолы", "ru": "R3 западная дорога", "en": "R3 western road"},
     "nodes": _n("N2", "R3a", "R3b", "SC", "SC1"), "segment_close_at_h": {"SC>SC1": 1.9}, "embankment": 0.6},
    {"id": "R12", "class": "rural", "speed": 50,
     "names": {"kk": "R12 қойма айналма жолы", "ru": "R12 объездная к складу", "en": "R12 depot bypass"},
     "nodes": _n("SC", "R3c", "R11b", "D1"), "embankment": 0.8},
    {"id": "U1", "class": "urban", "speed": 30,
     "names": {"kk": "U1 қала көшесі", "ru": "U1 городская улица", "en": "U1 town street"},
     "nodes": _n("G-1500_1100", "R3a")},
]

# town grid streets
for _y in GRID_Y:
    ROADS.append({"id": f"U{_y}", "class": "urban", "speed": 30, "embankment": 0.3,
                  "names": {"kk": f"Қала көшесі {_y}", "ru": f"Городская улица {_y}", "en": f"Town street {_y}"},
                  "nodes": [f"G{x}_{_y}" for x in GRID_X]})
for _x in GRID_X:
    if _x == 0:
        continue
    seq = [f"G{_x}_{y}" for y in GRID_Y]
    ROADS.append({"id": f"V{_x}", "class": "urban", "speed": 30, "embankment": 0.3,
                  "names": {"kk": f"Көлденең көше {_x}", "ru": f"Поперечная улица {_x}", "en": f"Cross street {_x}"},
                  "nodes": seq})
# connectors: grid ↔ riverside street, grid ↔ R1
_RIVERSIDE = {-1500: "R4w", -1000: "R4b", -500: "R4c", 500: "R4d", 1000: "R4e", 1500: "R4f"}
for _x, _node in _RIVERSIDE.items():
    ROADS.append({"id": f"V{_x}", "class": "urban", "speed": 30, "close_at_h": 2.3,
                  "names": {"kk": f"Көлденең көше {_x}", "ru": f"Поперечная улица {_x}", "en": f"Cross street {_x}"},
                  "nodes": [_node, f"G{_x}_700"]})
ROADS.append({"id": "V-1500", "class": "urban", "speed": 30, "embankment": 0.5,
              "names": {"kk": "Көлденең көше -1500", "ru": "Поперечная улица -1500", "en": "Cross street -1500"},
              "nodes": ["G-1500_1900", "N3"]})
ROADS.append({"id": "V1500", "class": "urban", "speed": 30, "embankment": 0.5,
              "names": {"kk": "Көлденең көше 1500", "ru": "Поперечная улица 1500", "en": "Cross street 1500"},
              "nodes": ["G1500_1900", "N5"]})


def sector_a_polygon() -> list[tuple[float, float]]:
    xs = np.linspace(-1700, 1700, 18)
    lower = [(float(x), float(river_y(x) + 45)) for x in xs]
    return lower + [(1700.0, 760.0), (-1700.0, 760.0)]


def sector_c_polygon() -> list[tuple[float, float]]:
    xs = np.linspace(-4300, -2300, 12)
    lower = [(float(x), float(river_y(x) + 45)) for x in xs]
    return lower + [(-2300.0, 1150.0), (-4300.0, 1150.0)]


def sector_e_polygon() -> list[tuple[float, float]]:
    xs = np.linspace(-1100, 1100, 10)
    upper = [(float(x), float(river_y(x) - 45)) for x in xs]
    return upper + [(1100.0, -2700.0), (-1100.0, -2700.0)]


SECTORS = [
    {"id": "A", "names": {"kk": "A секторы — жағалау", "ru": "Сектор A — прибрежный", "en": "Sector A — riverside"},
     "polygon": sector_a_polygon()},
    {"id": "B", "names": {"kk": "B секторы — оңтүстік ойпаң", "ru": "Сектор B — южная низина",
                          "en": "Sector B — southern lowland"},
     "polygon": [(1850, -880), (3450, -900), (3500, -1950), (1800, -1950)]},
    {"id": "C", "names": {"kk": "C секторы — батыс жағалау", "ru": "Сектор C — западный берег",
                          "en": "Sector C — western riverside"},
     "polygon": sector_c_polygon()},
    {"id": "D", "names": {"kk": "D секторы — қала орталығы", "ru": "Сектор D — центр города",
                          "en": "Sector D — town centre"},
     "polygon": [(-1700, 760), (1700, 760), (1700, 2300), (-1700, 2300)]},
    {"id": "E", "names": {"kk": "E секторы — оңтүстік жаға", "ru": "Сектор E — южный берег",
                          "en": "Sector E — southern bank"},
     "polygon": sector_e_polygon()},
]

# where synthetic buildings are generated: (sector, spacing m, floors distribution)
BUILDING_ZONES = [
    {"sector": "D", "spacing": 42, "floors": [1, 1, 2, 2, 3, 5], "core": [(-650, 1000), (650, 2000)], "core_floors": [3, 4, 5, 5, 9]},
    {"sector": "A", "spacing": 40, "floors": [1, 1, 1, 2]},
    {"sector": "B", "spacing": 38, "floors": [1, 1, 1, 2]},
    {"sector": "C", "spacing": 44, "floors": [1, 1, 2]},
    {"sector": "E", "spacing": 55, "floors": [1, 1, 2]},
]

BASES = [
    {"id": "BASE-A", "names": {"kk": "Өрт-құтқару бөлімі (DEMO)", "ru": "Пожарно-спасательная часть (DEMO)",
                               "en": "Fire & rescue station (DEMO)"}, "xy": (0, 1700), "safe": True},
    {"id": "DEPOT", "names": {"kk": "Аудандық материалдық қойма (DEMO)", "ru": "Районный склад (DEMO)",
                              "en": "District depot (DEMO)"}, "xy": (-5000, 2620), "safe": True},
]

FACILITIES = [
    {"id": "F-HOSP", "type": "HOSPITAL", "xy": (-900, 1300), "criticality": 100, "served": 25000, "sector": "D",
     "names": {"kk": "Аудандық аурухана (DEMO)", "ru": "Районная больница (DEMO)", "en": "District hospital (DEMO)"}},
    {"id": "F-WATER", "type": "WATER_SUPPLY", "xy": (-700, 330), "criticality": 90, "served": 30000, "sector": "A",
     "names": {"kk": "Су алу сорғы станциясы (DEMO)", "ru": "Водозаборная насосная станция (DEMO)",
               "en": "Water intake pumping station (DEMO)"}},
    {"id": "F-SUBST", "type": "POWER", "xy": (1150, 260), "criticality": 85, "served": 18000, "sector": "A",
     "names": {"kk": "Жағалау электр қосалқы станциясы (DEMO)", "ru": "Прибрежная электроподстанция (DEMO)",
               "en": "Riverside electrical substation (DEMO)"}},
    {"id": "F-CARE", "type": "CARE_HOME", "xy": (2400, -1420), "criticality": 95, "served": 60, "sector": "B",
     "names": {"kk": "B секторындағы қарттар үйі (DEMO)", "ru": "Дом престарелых сектора B (DEMO)",
               "en": "Sector B care home (DEMO)"}},
    {"id": "F-SCHOOL3", "type": "SCHOOL", "xy": (2950, -1420), "criticality": 70, "served": 650, "sector": "B",
     "names": {"kk": "№3 мектеп — уақытша пана (DEMO)", "ru": "Школа №3 — временный пункт (DEMO)",
               "en": "School No. 3 — temporary shelter (DEMO)"}},
    {"id": "F-FIRE", "type": "FIRE_STATION", "xy": (40, 1720), "criticality": 90, "served": 40000, "sector": "D",
     "names": {"kk": "Өрт-құтқару бөлімі (DEMO)", "ru": "Пожарно-спасательная часть (DEMO)",
               "en": "Fire & rescue station (DEMO)"}},
    {"id": "F-AKIMAT", "type": "ADMINISTRATION", "xy": (320, 1500), "criticality": 60, "served": 40000, "sector": "D",
     "names": {"kk": "Аудан әкімдігі (DEMO)", "ru": "Акимат района (DEMO)", "en": "District akimat (DEMO)"}},
    {"id": "F-SCHOOL1", "type": "SHELTER", "xy": (-1200, 1850), "criticality": 65, "served": 900, "sector": "D",
     "names": {"kk": "№1 мектеп — эвакуация пункті (DEMO)", "ru": "Школа №1 — пункт временного размещения (DEMO)",
               "en": "School No. 1 — evacuation centre (DEMO)"}},
    {"id": "F-CLINIC", "type": "CLINIC", "xy": (-3350, 900), "criticality": 75, "served": 4000, "sector": "C",
     "names": {"kk": "C секторы емханасы (DEMO)", "ru": "Поликлиника сектора C (DEMO)",
               "en": "Sector C outpatient clinic (DEMO)"}},
    {"id": "F-HEAT", "type": "HEATING", "xy": (2600, 2300), "criticality": 70, "served": 20000, "sector": None,
     "names": {"kk": "Жылу орталығы (DEMO)", "ru": "Котельная (DEMO)", "en": "Heating plant (DEMO)"}},
]

# local terrain adjustments: raised platforms (levee crest, pumping station platform) and basins
TERRAIN = {
    "north_slope": 0.0052, "south_slope": 0.0023, "terrace_start": 1700.0, "terrace_slope": 0.010,
    "bankfull_ws_at_x0": 292.0, "ws_slope": 0.0008, "channel_half_width": 26.0, "channel_depth": 2.6,
    "noise_amp": 0.12, "noise_sigma": 5.0, "seed": 7,
    "bowls": [
        Bowl(2600, -1320, 700, 430, -0.38),   # Sector B basin
        Bowl(1050, -790, 300, 130, -0.45),    # R7 low section swale
        Bowl(-700, 330, 90, 70, 0.40),         # pumping-station platform
        Bowl(-300, 185, 160, 45, 1.55),        # Sector A levee crest
        Bowl(-3250, 560, 180, 45, 2.00),       # Sector C levee crest
        Bowl(1150, 260, 70, 60, 0.10),         # substation pad
        Bowl(-3350, 900, 120, 90, 0.4),        # clinic pad
    ],
}

TASK_SITES = [
    {"id": "S-LEVEE-A", "kind": "LEVEE", "xy": (-300, 185), "sector": "A", "work_limit": -0.30,
     "protects": {"sector_ids": ["A"], "facility_ids": ["F-WATER"]},
     "names": {"kk": "A секторы бөгетінің учаскесі", "ru": "Участок дамбы сектора A", "en": "Sector A levee section"}},
    {"id": "S-LEVEE-C", "kind": "LEVEE", "xy": (-3250, 560), "sector": "C", "work_limit": -0.30,
     "protects": {"sector_ids": ["C"], "facility_ids": ["F-CLINIC"]},
     "names": {"kk": "C секторы бөгетінің учаскесі", "ru": "Участок дамбы сектора C", "en": "Sector C levee section"}},
    {"id": "S-WATER", "kind": "FACILITY", "xy": (-700, 330), "sector": "A", "work_limit": 0.20,
     "protects": {"facility_ids": ["F-WATER"]},
     "names": {"kk": "Су алу станциясы", "ru": "Водозаборная станция", "en": "Water intake station"}},
    {"id": "S-SUBST", "kind": "FACILITY", "xy": (1150, 260), "sector": "A", "work_limit": 0.20,
     "protects": {"facility_ids": ["F-SUBST"]},
     "names": {"kk": "Электр қосалқы станциясы", "ru": "Электроподстанция", "en": "Electrical substation"}},
    {"id": "S-DRAIN-B", "kind": "DRAINAGE_POINT", "xy": (2600, -1330), "sector": "B", "work_limit": 0.25,
     "protects": {"sector_ids": ["B"], "facility_ids": ["F-CARE"]},
     "names": {"kk": "B секторының дренаж нүктесі", "ru": "Дренажная точка сектора B",
               "en": "Sector B drainage point"}},
    {"id": "S-CARE", "kind": "FACILITY", "xy": (2400, -1420), "sector": "B", "work_limit": 0.30,
     "protects": {"facility_ids": ["F-CARE"]},
     "names": {"kk": "Қарттар үйі (B)", "ru": "Дом престарелых (B)", "en": "Care home (B)"}},
    {"id": "S-SCHOOL3", "kind": "FACILITY", "xy": (2950, -1420), "sector": "B", "work_limit": 0.30,
     "protects": {"facility_ids": ["F-SCHOOL3"]},
     "names": {"kk": "№3 мектеп (B)", "ru": "Школа №3 (B)", "en": "School No. 3 (B)"}},
    {"id": "S-STAGE-B", "kind": "STAGING", "xy": (2950, -1520), "sector": "B", "work_limit": 0.40,
     "protects": {"sector_ids": ["B"]},
     "names": {"kk": "B секторының жинақтау алаңы", "ru": "Площадка сосредоточения сектора B",
               "en": "Sector B staging area"}},
    {"id": "S-R7-CTRL", "kind": "ROAD_CLOSURE", "xy": (0, 650), "sector": "D", "work_limit": 0.20,
     "protects": {"sector_ids": ["B"], "road_ids": ["R7"]},
     "names": {"kk": "R7 жолын жабу нүктесі", "ru": "Пункт перекрытия дороги R7", "en": "Road R7 closure point"}},
    {"id": "S-HOSP", "kind": "FACILITY", "xy": (-900, 1300), "sector": "D", "work_limit": 0.30,
     "protects": {"facility_ids": ["F-HOSP"]},
     "names": {"kk": "Аурухана", "ru": "Больница", "en": "Hospital"}},
    {"id": "S-DRAIN-C", "kind": "DRAINAGE_POINT", "xy": (-3550, 700), "sector": "C", "work_limit": 0.25,
     "protects": {"sector_ids": ["C"]},
     "names": {"kk": "C секторының дренаж нүктесі", "ru": "Дренажная точка сектора C",
               "en": "Sector C drainage point"}},
    {"id": "S-CLINIC", "kind": "FACILITY", "xy": (-3350, 900), "sector": "C", "work_limit": 0.30,
     "protects": {"facility_ids": ["F-CLINIC"]},
     "names": {"kk": "C секторы емханасы", "ru": "Поликлиника сектора C", "en": "Sector C clinic"}},
]

STATIONS = [
    {"id": "HP-ZHABAI-ATB", "xy": (-150, 110), "river": "Zhabai", "bankfull": 500, "watch": 560, "warning": 620,
     "critical": 700,
     "names": {"kk": "Жабай — Атбасар гидробекеті (DEMO)", "ru": "Жабай — гидропост Атбасар (DEMO)",
               "en": "Zhabai — Atbasar hydropost (DEMO)"}},
]

# Stage hydrographs (cm) of the precomputed scenario ensemble members. Offsets in hours relative to
# the scenario reference time (NOW). All members share the analysed stage up to the issuance time (T-4h).
HYDROLOGY = {
    "bankfull_cm": 500,
    "common": [(-6, 548), (-5, 553), (-4, 559)],
    "recession_base_cm": 560, "recession_tau_h": 9.0,
    "members": [
        {"id": "M1", "label": "Low", "s0": 590, "peak": 670, "tp": 13.0},
        {"id": "M2", "label": "Below median", "s0": 596, "peak": 700, "tp": 12.0},
        {"id": "M3", "label": "Median (issuance P50)", "s0": 601, "peak": 725, "tp": 11.5},
        {"id": "M4", "label": "Above median", "s0": 611, "peak": 755, "tp": 10.0},
        {"id": "M5", "label": "High", "s0": 620, "peak": 785, "tp": 9.5},
        {"id": "M6", "label": "Extreme", "s0": 628, "peak": 815, "tp": 9.0},
    ],
    "issued_member": "M3",
    "conditioned_member": "M4",
    # DEMO observations (hours, stage cm, source_type, verification, source label)
    "observations": [
        (-4.0, 559, "HYDROPOST", "VERIFIED", "Automatic hydropost (DEMO)"),
        (-3.0, 568, "HYDROPOST", "VERIFIED", "Automatic hydropost (DEMO)"),
        (-2.0, 579, "HYDROPOST", "VERIFIED", "Automatic hydropost (DEMO)"),
        (-1.0, 590, "HYDROPOST", "VERIFIED", "Automatic hydropost (DEMO)"),
        (-10 / 60, 598, "HYDROPOST", "UNVERIFIED", "Automatic hydropost (DEMO)"),
        (-10 / 60, 613, "FIELD", "VERIFIED", "Field team gauge reading, Crew C5 (DEMO)"),
    ],
}

RESOURCES = [
    # crews
    {"id": "C1", "type": "CREW", "subtype": "ENGINEERING", "base": "BASE-A", "capacity": 6, "unit": "persons"},
    {"id": "C2", "type": "CREW", "subtype": "ENGINEERING", "base": "DEPOT", "capacity": 6, "unit": "persons"},
    {"id": "C3", "type": "CREW", "subtype": "GENERAL", "base": "BASE-A", "capacity": 4, "unit": "persons"},
    {"id": "C4", "type": "CREW", "subtype": "GENERAL", "base": "BASE-A", "capacity": 4, "unit": "persons"},
    {"id": "C5", "type": "CREW", "subtype": "RESCUE", "base": "BASE-A", "capacity": 5, "unit": "persons"},
    {"id": "C6", "type": "CREW", "subtype": "RESCUE", "base": "DEPOT", "capacity": 5, "unit": "persons"},
    # vehicles
    {"id": "V1", "type": "VEHICLE", "subtype": "TRUCK", "base": "BASE-A", "capacity": 8, "unit": "t"},
    {"id": "V2", "type": "VEHICLE", "subtype": "TRUCK", "base": "BASE-A", "capacity": 8, "unit": "t"},
    {"id": "V3", "type": "VEHICLE", "subtype": "TRUCK", "base": "DEPOT", "capacity": 10, "unit": "t"},
    {"id": "V4", "type": "VEHICLE", "subtype": "HIGH_CLEARANCE", "base": "BASE-A", "capacity": 3, "unit": "t"},
    {"id": "V5", "type": "VEHICLE", "subtype": "HIGH_CLEARANCE", "base": "DEPOT", "capacity": 3, "unit": "t"},
    {"id": "V6", "type": "VEHICLE", "subtype": "PICKUP", "base": "BASE-A", "capacity": 1, "unit": "t"},
    # equipment
    {"id": "EQ1", "type": "EQUIPMENT", "subtype": "EXCAVATOR", "base": "DEPOT", "capacity": None, "unit": None},
    {"id": "EQ2", "type": "EQUIPMENT", "subtype": "SANDBAG_FILLER", "base": "BASE-A", "capacity": 600, "unit": "bags/h"},
    {"id": "EQ3", "type": "EQUIPMENT", "subtype": "SANDBAG_FILLER", "base": "DEPOT", "capacity": 600, "unit": "bags/h"},
] + [
    {"id": f"P{i:02d}", "type": "PUMP", "subtype": "MOBILE_PUMP", "base": "BASE-A" if i <= 10 else "DEPOT",
     "capacity": 200 if i % 3 else 300, "unit": "m3/h"}
    for i in range(1, 17)
]

# Human response plan "Plan A" — authored against scenario v1 (issuance median member).
# times are "HH:MM" local on the reference day.
PLANS = [
    {"id": "plan-a", "name": "Plan A", "description": "Human response plan prepared at 06:30 against forecast v1 (DEMO)",
     "tasks": [
         {"code": "T1", "template": "ACT-LEVEE", "site": "S-LEVEE-A", "resources": ["C1", "V1", "EQ2"], "depart": "10:10"},
         {"code": "T2", "template": "ACT-PUMP-L", "site": "S-WATER", "resources": ["C2", "V3", "P11", "P12", "P13", "P14"], "depart": "10:20"},
         {"code": "T3", "template": "ACT-PUMP-S", "site": "S-SUBST", "resources": ["C4", "V2", "P01", "P02"], "depart": "10:15"},
         {"code": "T4", "template": "ACT-SUPPLY", "site": "S-CARE", "resources": ["C6", "V5"], "depart": "11:00"},
         {"code": "T5", "template": "ACT-PREPOS", "site": "S-STAGE-B", "resources": ["C5", "V4"], "depart": "12:40"},
         {"code": "T6", "template": "ACT-ROADCLOSE", "site": "S-R7-CTRL", "resources": ["C4", "V6"], "depart": "12:20",
          "depends": ["T3"]},
         {"code": "T7", "template": "ACT-LEVEE", "site": "S-LEVEE-C", "resources": ["C2", "V3", "EQ3"], "depart": "11:50",
          "depends": ["T2"]},
         {"code": "T9", "template": "ACT-SUPPLY", "site": "S-HOSP", "resources": ["C3", "V6"], "depart": "11:10"},
         {"code": "T8", "template": "ACT-PUMP-L", "site": "S-DRAIN-B", "resources": ["C3", "V1", "P05", "P06", "P07", "P08"],
          "depart": "14:30", "depends": ["T9"]},
     ]},
]

# Additional candidate tasks the optimizer may schedule (the human plan's tasks are always candidates).
EXTRA_CANDIDATES = [
    {"code": "T10", "template": "ACT-PUMP-S", "site": "S-SCHOOL3"},
    {"code": "T11", "template": "ACT-PUMP-M", "site": "S-DRAIN-C"},
    {"code": "T12", "template": "ACT-SUPPLY", "site": "S-CLINIC"},
]

SPEC = {
    "id": "atbasar",
    "sort_order": 1,
    "names": {"kk": "Атбасар — Жабай", "ru": "Атбасар — Жабай", "en": "Atbasar — Zhabai", "original": "Атбасар"},
    "river_names": {"kk": "Жабай өзені", "ru": "река Жабай", "en": "Zhabai River", "original": "Жабай"},
    "archetype": "RIVERINE_FLOODPLAIN",
    "center": (68.3580, 51.8060),
    "epsg": 32642,
    "grid": {"x0": -8000.0, "y1": 6000.0, "res": 40.0, "nx": 400, "ny": 300},
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
        {"id": "BN-B1", "kind": "BRIDGE", "segments": ["R2a>B1S"], "bridge": "B1",
         "names": {"kk": "B1 орталық көпір", "ru": "Центральный мост B1", "en": "Central bridge B1"}},
        {"id": "BN-B2", "kind": "BRIDGE", "segments": ["B2N>B2S"], "bridge": "B2",
         "names": {"kk": "B2 шығыс көпір", "ru": "Восточный мост B2", "en": "Eastern bridge B2"}},
        {"id": "BN-R7", "kind": "LOW_ROAD", "segments": ["R7a>R7b", "R7b>R7c"],
         "names": {"kk": "R7 ойпаң учаскесі", "ru": "Пониженный участок R7", "en": "R7 low section"}},
    ],
    "ponding": None,
    "reference_time_local": "2026-04-12T10:00:00",
    "utc_offset_min": 300,
}
