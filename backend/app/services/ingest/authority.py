"""Data authority hierarchy (higher wins). Conflicts are never silently overwritten."""

from __future__ import annotations

SOURCE_TYPES = ("FIELD", "HYDROPOST", "FORECAST", "SATELLITE", "GLOBAL_MODEL", "SIMULATION")

_BASE = {
    "FIELD": 45,  # unverified field report
    "HYDROPOST": 50,
    "FORECAST": 40,
    "SATELLITE": 30,
    "GLOBAL_MODEL": 20,
    "SIMULATION": 10,
}


def authority_rank(source_type: str, verification: str) -> int:
    if verification == "REJECTED":
        return -1
    if source_type == "FIELD" and verification == "VERIFIED":
        return 60
    return _BASE.get(source_type, 0)


def authority_label(source_type: str, verification: str) -> str:
    if source_type == "FIELD" and verification == "VERIFIED":
        return "VERIFIED_FIELD"
    return source_type
