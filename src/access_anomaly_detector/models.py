from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class AccessEvent:
    timestamp: datetime
    actor_id: str
    resource_id: str
    resource_type: str
    action: str
    project_id: str

    # optional context
    location: Optional[str] = None
    ip: Optional[str] = None
    device_fingerprint: Optional[str] = None
    auth_method: Optional[str] = None
    sensitivity: Optional[str] = None

    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ScoredEvent:
    event: AccessEvent
    score: float
    bucket: str
    signals: List[str]
    explanation: str
    recommended_actions: List[str]
    ts_scored: datetime
