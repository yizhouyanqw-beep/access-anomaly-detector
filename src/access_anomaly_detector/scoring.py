from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Tuple, Any

from .models import AccessEvent, ScoredEvent
from .features import compute_signals, update_baselines
from .storage import SQLiteStore


def _bucket(score: float, high: float, medium: float) -> str:
    if score >= high:
        return "HIGH"
    if score >= medium:
        return "MEDIUM"
    return "LOW"


def _recommendations(bucket: str, signals: List[str]) -> List[str]:
    if bucket == "HIGH":
        rec = ["Require step-up MFA on next access", "Notify project/security owner", "Create incident ticket if pattern persists"]
        # add a bit of tailoring
        if any("New device" in s for s in signals):
            rec.insert(0, "Invalidate sessions and re-authenticate on new device")
        return rec
    if bucket == "MEDIUM":
        return ["Log and monitor", "Consider step-up MFA for next sensitive action"]
    return ["No action (baseline update only)"]


def rule_based_score(
    features: Dict[str, float],
    weights: Dict[str, float],
) -> float:
    # Weighted sum with clipping to [0, 1]
    s = 0.0
    for name, val in features.items():
        w = float(weights.get(name, 0.0))
        s += w * float(val)
    if s < 0:
        return 0.0
    if s > 1:
        return 1.0
    return s


def baseline_score(features: Dict[str, float], actor_total_events: int, baseline_cfg: Dict[str, Any]) -> float:
    """
    A minimal alternate scoring mode. Here we just:
      - emphasize unusual_hour more as history grows
      - combine with other signals lightly
    """
    min_hist = int(baseline_cfg.get("min_history_events", 30))
    history_factor = min(actor_total_events / max(min_hist, 1), 2.0)  # up to 2x

    unusual = float(features.get("unusual_hour", 0.0)) * min(history_factor / 2.0, 1.0)
    other = 0.0
    for k, v in features.items():
        if k != "unusual_hour":
            other += 0.15 * float(v)
    s = unusual * 0.7 + min(other, 0.6)
    return max(0.0, min(1.0, s))


def score_event(
    event: AccessEvent,
    store: SQLiteStore,
    cfg,
    update_store: bool = True,
) -> ScoredEvent:
    feat = compute_signals(event, store, cfg.sensitivity_labels, cfg.baseline)
    now = datetime.now(timezone.utc)

    if cfg.scoring_engine == "baseline":
        actor_total = store.get_actor_total_events(event.actor_id)
        score = baseline_score(feat.values, actor_total, cfg.baseline)
    else:
        score = rule_based_score(feat.values, cfg.weights)

    bucket = _bucket(score, cfg.thresholds.high, cfg.thresholds.medium)
    explanation = " | ".join(feat.signals) if feat.signals else "No unusual signals detected."

    scored = ScoredEvent(
        event=event,
        score=float(round(score, 4)),
        bucket=bucket,
        signals=feat.signals,
        explanation=explanation,
        recommended_actions=_recommendations(bucket, feat.signals),
        ts_scored=now,
    )

    if update_store:
        update_baselines(event, store)

    return scored
