from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def parse_iso8601_utc(ts: str) -> datetime:
    # Expecting "2025-12-21T03:21:00Z" or with offset
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, datetime):
        return obj.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_jsonable(x) for x in obj]
    return obj


def json_dumps(obj: Any) -> str:
    return json.dumps(to_jsonable(obj), ensure_ascii=False, separators=(",", ":"))


def safe_get(d: Dict[str, Any], key: str, default: Optional[Any] = None) -> Any:
    v = d.get(key, default)
    return default if v is None else v
