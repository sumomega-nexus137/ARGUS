"""DEMO Approved Action Library and demo users.

In production the action library is authored and approved by emergency specialists through the
API / UI (``/api/actions``). ARGUS only selects and schedules from it. These DEMO templates exist
so the optimizer and stress tester have something to work with; their durations and effects are
illustrative values, not doctrine.
"""

from __future__ import annotations

DEMO_APPROVER = "DEMO — Regional ES department (illustrative)"


def _t(kk: str, ru: str, en: str) -> dict:
    return {"kk": kk, "ru": ru, "en": en}


def _pump(tid: str, pumps: int, names: dict) -> dict:
    return {
        "id": tid, "action_type": "PUMP_DEPLOYMENT", "names": names,
        "description": _t(
            f"{pumps} жылжымалы сорғыны орналастыру және іске қосу",
            f"Развёртывание и запуск {pumps} мобильных насосов",
            f"Deploy and commission {pumps} mobile pumps",
        ),
        "requirements": {"crew": {"types": ["ENGINEERING", "GENERAL"], "count": 1},
                         "vehicle": {"types": ["TRUCK"], "count": 1}, "pumps": pumps, "equipment": {}},
        "setup_min": 30, "execution_min": 30, "safety_buffer_min": 20, "equipment_release": "HORIZON",
        "site_kinds": ["DRAINAGE_POINT", "FACILITY"],
        "prerequisites": [_t("Қоректендіру көзі немесе генератор", "Источник питания или генератор", "Power source or generator")],
        "constraints": {"requires_egress": True, "damage_reduction_range": [0.25, 0.45], "holds": ["PUMP"]},
    }


ACTIONS: list[dict] = [
    _pump("ACT-PUMP-S", 2, _t("Сорғы орналастыру (2 сорғы)", "Развёртывание насосов (2 шт.)", "Pump deployment (2 pumps)")),
    _pump("ACT-PUMP-M", 3, _t("Сорғы орналастыру (3 сорғы)", "Развёртывание насосов (3 шт.)", "Pump deployment (3 pumps)")),
    _pump("ACT-PUMP-L", 4, _t("Сорғы орналастыру (4 сорғы)", "Развёртывание насосов (4 шт.)", "Pump deployment (4 pumps)")),
    {
        "id": "ACT-LEVEE", "action_type": "LEVEE_REINFORCEMENT",
        "names": _t("Бөгетті нығайту", "Укрепление дамбы", "Levee reinforcement"),
        "description": _t("Құм қаптарымен және геотекстильмен бөгетті биіктету",
                          "Наращивание дамбы мешками с песком и геотекстилем",
                          "Raise the levee crest with sandbags and geotextile"),
        "requirements": {"crew": {"types": ["ENGINEERING"], "count": 1}, "vehicle": {"types": ["TRUCK"], "count": 1},
                         "pumps": 0, "equipment": {"SANDBAG_FILLER": 1}},
        "setup_min": 20, "execution_min": 90, "safety_buffer_min": 30, "equipment_release": "TASK_END",
        "site_kinds": ["LEVEE"],
        "prerequisites": [_t("Құм мен қаптар қоры", "Запас песка и мешков", "Sand and bag stock")],
        "constraints": {"requires_egress": True, "damage_reduction_range": [0.4, 0.7]},
    },
    {
        "id": "ACT-PREPOS", "action_type": "RESOURCE_PREPOSITIONING",
        "names": _t("Ресурстарды алдын ала орналастыру", "Предварительное размещение ресурсов", "Resource pre-positioning"),
        "description": _t("Құтқару тобын оқшаулану басталғанға дейін секторға орналастыру",
                          "Размещение спасательной группы в секторе до его изоляции",
                          "Stage a rescue team inside the sector before it becomes isolated"),
        "requirements": {"crew": {"types": ["RESCUE"], "count": 1}, "vehicle": {"types": ["HIGH_CLEARANCE"], "count": 1},
                         "pumps": 0, "equipment": {}},
        "setup_min": 10, "execution_min": 15, "safety_buffer_min": 15, "equipment_release": "HORIZON",
        "site_kinds": ["STAGING", "FACILITY"],
        "prerequisites": [],
        "constraints": {"requires_egress": False, "damage_reduction_range": [0.0, 0.0], "holds": ["CREW", "VEHICLE"]},
    },
    {
        "id": "ACT-SUPPLY", "action_type": "SUPPLY_DELIVERY",
        "names": _t("Жабдықтау жеткізілімі", "Доставка снабжения", "Supply delivery"),
        "description": _t("Отын, су, дәрі-дәрмек жеткізу", "Доставка топлива, воды, медикаментов",
                          "Deliver fuel, water and medical supplies"),
        "requirements": {"crew": {"types": ["GENERAL", "RESCUE"], "count": 1},
                         "vehicle": {"types": ["TRUCK", "HIGH_CLEARANCE", "PICKUP"], "count": 1}, "pumps": 0, "equipment": {}},
        "setup_min": 15, "execution_min": 30, "safety_buffer_min": 15, "equipment_release": "TASK_END",
        "site_kinds": ["FACILITY"],
        "prerequisites": [],
        "constraints": {"requires_egress": True, "damage_reduction_range": [0.0, 0.0]},
    },
    {
        "id": "ACT-ROADCLOSE", "action_type": "ROAD_CLOSURE",
        "names": _t("Жолды жабу және қозғалысты реттеу", "Перекрытие дороги и регулирование движения",
                    "Road closure & traffic control"),
        "description": _t("Су басатын жол учаскесіне кіруді жабу", "Перекрытие въезда на подтопляемый участок",
                          "Close access to a road section expected to flood"),
        "requirements": {"crew": {"types": ["GENERAL"], "count": 1},
                         "vehicle": {"types": ["PICKUP", "TRUCK", "HIGH_CLEARANCE"], "count": 1}, "pumps": 0, "equipment": {}},
        "setup_min": 10, "execution_min": 20, "safety_buffer_min": 10, "equipment_release": "TASK_END",
        "site_kinds": ["ROAD_CLOSURE"],
        "prerequisites": [_t("Жол белгілері мен тосқауылдар", "Знаки и ограждения", "Signs and barriers")],
        "constraints": {"requires_egress": True, "damage_reduction_range": [0.0, 0.0]},
    },
    {
        "id": "ACT-CULVERT", "action_type": "CULVERT_CLEARING",
        "names": _t("Су өткізгіш құбырды тазарту", "Очистка водопропускной трубы", "Culvert clearing"),
        "description": _t("Мұз бен қоқысты экскаватормен тазарту", "Удаление льда и мусора экскаватором",
                          "Remove ice and debris with an excavator"),
        "requirements": {"crew": {"types": ["ENGINEERING"], "count": 1}, "vehicle": {"types": ["TRUCK"], "count": 1},
                         "pumps": 0, "equipment": {"EXCAVATOR": 1}},
        "setup_min": 20, "execution_min": 60, "safety_buffer_min": 20, "equipment_release": "TASK_END",
        "site_kinds": ["CULVERT"],
        "prerequisites": [],
        "constraints": {"requires_egress": True, "damage_reduction_range": [0.3, 0.6]},
    },
]

DEMO_PASSWORD = "argus2026"

USERS = [
    {"username": "viewer", "full_name": "Demo Viewer", "role": "VIEWER"},
    {"username": "operator", "full_name": "Demo Operator (field)", "role": "OPERATOR"},
    {"username": "planner", "full_name": "Demo Planner", "role": "PLANNER"},
    {"username": "commander", "full_name": "Demo Commander", "role": "COMMANDER"},
    {"username": "admin", "full_name": "Demo Administrator", "role": "ADMIN"},
]

MODEL_VERSIONS = [
    ("scenario-synthetic", "scenario_provider", "synthetic-stage-hand-0.3",
     "SIMULATION stage–HAND inundation surrogate for DEMO areas (not hydrodynamic)."),
    ("scenario-raster", "scenario_provider", "raster-manifest-1.0", "Consumes precomputed depth rasters from the modelling pipeline."),
    ("impact", "impact_engine", "impact-1.0", "Point-sampled building / facility / road exposure with DEMO valuation assumptions."),
    ("access", "access_engine", "access-td-1.0", "Time-dependent road graph, latest-departure reverse search, max–min access loss."),
    ("evaluator", "plan_evaluator", "plan-eval-1.0", "Deterministic plan simulation with causal failure chains."),
    ("optimizer", "optimizer", "cpsat-1.0", "OR-Tools CP-SAT scheduling with post-solve time-dependent verification."),
    ("validation", "validation", "validation-1.0", "Binary mask comparison: IoU, precision, recall, F1, CSI."),
]
