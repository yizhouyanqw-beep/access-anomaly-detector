from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any
import yaml


@dataclass(frozen=True)
class Thresholds:
    high: float
    medium: float


@dataclass(frozen=True)
class Config:
    scoring_engine: str
    thresholds: Thresholds
    weights: Dict[str, float]
    sensitivity_labels: Dict[str, float]
    baseline: Dict[str, Any]


def load_config(path: str) -> Config:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    scoring = data.get("scoring", {})
    thresholds = scoring.get("thresholds", {})
    cfg = Config(
        scoring_engine=scoring.get("engine", "rule_based"),
        thresholds=Thresholds(
            high=float(thresholds.get("high", 0.8)),
            medium=float(thresholds.get("medium", 0.5)),
        ),
        weights={k: float(v) for k, v in (data.get("weights", {}) or {}).items()},
        sensitivity_labels={k: float(v) for k, v in (data.get("sensitivity_labels", {}) or {}).items()},
        baseline=data.get("baseline", {}) or {},
    )
    return cfg
