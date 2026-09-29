"""Centralized configuration (environment-driven, see .env.example)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARGUS_", env_file=(REPO_ROOT / ".env", ".env"), extra="ignore"
    )

    app_name: str = "ARGUS FloodOps"
    environment: str = "development"
    # DEMO mode seeds clearly-labelled DEMO / SIMULATION fixtures when the database is empty.
    demo_mode: bool = True

    database_url: str = Field(default=f"sqlite:///{(REPO_ROOT / 'data' / 'argus.db').as_posix()}")
    data_dir: Path = REPO_ROOT / "data"

    jwt_secret: str = "change-me-in-production-argus-demo-secret"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 12 * 60

    cors_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Operational thresholds (configurable; documented in docs/METHODOLOGY.md)
    road_restricted_depth_m: float = 0.10
    road_closed_depth_m: float = 0.30
    road_closed_depth_high_clearance_m: float = 0.60
    restricted_speed_factor: float = 0.4
    window_closing_threshold_min: int = 45
    task_at_risk_slack_min: int = 20
    observation_conflict_window_min: int = 30
    observation_conflict_tolerance_cm: float = 5.0
    stale_after_min: int = 120
    apply_unverified_closures: bool = True

    optimizer_time_limit_s: float = 3.0
    optimizer_workers: int = 4
    optimizer_max_alternatives: int = 3

    @property
    def demo_dir(self) -> Path:
        return self.data_dir / "demo"

    @property
    def imports_dir(self) -> Path:
        return self.data_dir / "imports"

    @property
    def processed_dir(self) -> Path:
        return self.data_dir / "processed"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
