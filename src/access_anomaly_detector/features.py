from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timezone
from typing import Any, Dict, List

from .models import AccessEvent
from .storage import SQLiteStore


@dataclass(frozen=True)
class FeatureSignals:
    # numeric contributions (0..1) for scoring
    values: Dict[str, float]
    # human-readable signals
    signals: List[str]


def compute_signals(
    event: AccessEvent,
    store: SQLiteStore,
    sensitivity_map: Dict[str, float],
    baseline_cfg: Dict[str, Any],
) -> FeatureSignals:
    signals: List[str] = []
    values: Dict[str, float] = {}

    ts_utc = event.timestamp.astimezone(timezone.utc)
    hour = ts_utc.hour

    alpha = float(baseline_cfg.get("smoothing_alpha", 1.0))
    min_hist = int(baseline_cfg.get("min_history_events", 30))

    # --- Hour likelihood: -log P(hour | actor) with Laplace smoothing
    hour_cnt = store.get_actor_hour_count(event.actor_id, hour)
    actor_total = store.get_actor_total_events(event.actor_id)

    # P = (count + alpha) / (total + 24*alpha)
    p_hour = (hour_cnt + alpha) / (max(actor_total, 0) + 24.0 * alpha)
    nll_hour = -math.log(p_hour)

    # normalize by "worst-case" probability under smoothing:
    # p_min = alpha / (total + 24*alpha)  -> max surprise for an unseen hour
    p_min_hour = alpha / (max(actor_total, 0) + 24.0 * alpha)
    nll_hour_max = -math.log(p_min_hour) if p_min_hour > 0 else nll_hour

    hour_score = min(1.0, nll_hour / max(nll_hour_max, 1e-9))

    # If not enough history, downweight (avoid overreacting for new users)
    if actor_total < min_hist:
        hour_score *= 0.35

    values["unusual_hour"] = float(hour_score)

    if hour_score >= 0.6:
        signals.append(
            f"Unusual hour for actor (UTC hour={hour}, P={p_hour:.4f}, nll={nll_hour:.2f})"
        )

    # --- Resource type likelihood: -log P(resource_type | actor)
    # We use an approximate vocabulary size K from config for Laplace smoothing.
    K = int(baseline_cfg.get("rtype_vocab_size", 50))

    rtype_cnt = store.get_actor_resource_type_count(event.actor_id, event.resource_type)
    rtype_total = store.get_actor_resource_type_total(event.actor_id)

    p_rtype = (rtype_cnt + alpha) / (max(rtype_total, 0) + float(K) * alpha)
    nll_rtype = -math.log(p_rtype)

    p_min_rtype = alpha / (max(rtype_total, 0) + float(K) * alpha)
    nll_rtype_max = -math.log(p_min_rtype) if p_min_rtype > 0 else nll_rtype

    rtype_score = min(1.0, nll_rtype / max(nll_rtype_max, 1e-9))
    if rtype_total < min_hist:
        rtype_score *= 0.35

    values["unusual_resource_type"] = float(rtype_score)

    if rtype_score >= 0.6:
        signals.append(
            f"Unusual resource_type for actor (resource_type={event.resource_type}, P={p_rtype:.4f}, nll={nll_rtype:.2f})"
        )

    # --- New device fingerprint (still a strong discrete signal)
    if event.device_fingerprint:
        if not store.has_actor_device(event.actor_id, event.device_fingerprint):
            values["new_device"] = 1.0
            signals.append("New device_fingerprint for this actor")

    # --- Sensitivity (maps to numeric severity; contributes directly)
    if event.sensitivity:
        sev = float(sensitivity_map.get(event.sensitivity, 0.0))
        if sev > 0:
            values["sensitive_resource"] = sev
            if sev >= 0.7:
                signals.append(f"Sensitive resource (sensitivity={event.sensitivity})")

    # --- Rare resource in org (few distinct actors touched recently)
    lookback_days = int(baseline_cfg.get("hour_lookback_days", 30))
    rare_threshold = int(baseline_cfg.get("rare_resource_actor_threshold", 3))
    distinct_actors = store.count_distinct_actors_for_resource_lookback(
        event.resource_id, lookback_days, ts_utc
    )
    if distinct_actors > 0 and distinct_actors <= rare_threshold:
        values["rare_resource_for_org"] = 1.0
        signals.append(
            f"Rare resource access (distinct_actors_last_{lookback_days}d={distinct_actors})"
        )

    return FeatureSignals(values=values, signals=signals)


def update_baselines(event: AccessEvent, store: SQLiteStore) -> None:
    ts_utc = event.timestamp.astimezone(timezone.utc)
    hour = ts_utc.hour

    store.upsert_actor_hour(event.actor_id, hour, ts_utc)
    store.upsert_actor_resource_type(event.actor_id, event.resource_type, ts_utc)
    if event.device_fingerprint:
        store.upsert_actor_device(event.actor_id, event.device_fingerprint, ts_utc)
    store.upsert_resource_actor_recent(event.resource_id, event.actor_id, ts_utc)
