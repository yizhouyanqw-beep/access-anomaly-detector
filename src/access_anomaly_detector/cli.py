from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterator, Dict, Any
from datetime import datetime, timezone

from .config import load_config
from .models import AccessEvent
from .storage import SQLiteStore
from .scoring import score_event
from .utils import parse_iso8601_utc, json_dumps, safe_get
from .http_server import serve


def _iter_jsonl(path: str) -> Iterator[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _event_from_dict(d: Dict[str, Any]) -> AccessEvent:
    missing = [k for k in ["timestamp", "actor_id", "resource_id", "resource_type", "action", "project_id"] if k not in d]
    if missing:
        raise ValueError(f"missing required fields: {missing}")
    return AccessEvent(
        timestamp=parse_iso8601_utc(str(d["timestamp"])),
        actor_id=str(d["actor_id"]),
        resource_id=str(d["resource_id"]),
        resource_type=str(d["resource_type"]),
        action=str(d["action"]),
        project_id=str(d["project_id"]),
        location=safe_get(d, "location"),
        ip=safe_get(d, "ip"),
        device_fingerprint=safe_get(d, "device_fingerprint"),
        auth_method=safe_get(d, "auth_method"),
        sensitivity=safe_get(d, "sensitivity"),
        raw=dict(d),
    )


def cmd_score(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    db_path = args.db or str(Path(args.output).with_suffix(".sqlite"))
    store = SQLiteStore(db_path)

    out_path = args.output
    written = 0
    high_cnt = 0
    med_cnt = 0

    with open(out_path, "w", encoding="utf-8") as out:
        for obj in _iter_jsonl(args.input):
            ev = _event_from_dict(obj)
            scored = score_event(ev, store, cfg, update_store=True)

            if scored.bucket == "HIGH":
                high_cnt += 1
            elif scored.bucket == "MEDIUM":
                med_cnt += 1

            out.write(
                json_dumps(
                    {
                        "event": scored.event.raw if scored.event.raw else {
                            "timestamp": scored.event.timestamp,
                            "actor_id": scored.event.actor_id,
                            "resource_id": scored.event.resource_id,
                            "resource_type": scored.event.resource_type,
                            "action": scored.event.action,
                            "project_id": scored.event.project_id,
                            "location": scored.event.location,
                            "ip": scored.event.ip,
                            "device_fingerprint": scored.event.device_fingerprint,
                            "auth_method": scored.event.auth_method,
                            "sensitivity": scored.event.sensitivity,
                        },
                        "score": scored.score,
                        "bucket": scored.bucket,
                        "signals": scored.signals,
                        "explanation": scored.explanation,
                        "recommended_actions": scored.recommended_actions,
                        "ts_scored": scored.ts_scored,
                    }
                )
                + "\n"
            )
            written += 1

            if args.commit_every and written % args.commit_every == 0:
                store.commit()

    store.commit()
    store.close()

    print(f"Wrote {written} scored events to {out_path}")
    print(f"Buckets: HIGH={high_cnt}, MEDIUM={med_cnt}, LOW={written - high_cnt - med_cnt}")
    print(f"SQLite baselines at: {db_path}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    store = SQLiteStore(args.db)
    try:
        serve(args.host, args.port, store, cfg, score_event)
    finally:
        store.commit()
        store.close()
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="access-anomaly-detector")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_score = sub.add_parser("score", help="Batch score a JSONL file.")
    p_score.add_argument("--input", required=True, help="Input JSONL audit log.")
    p_score.add_argument("--output", required=True, help="Output JSONL scored events.")
    p_score.add_argument("--config", required=True, help="Path to config.yaml")
    p_score.add_argument("--db", default=None, help="SQLite path for baseline stats (default: derived from output).")
    p_score.add_argument("--commit-every", type=int, default=500, help="Commit every N events (default 500).")
    p_score.set_defaults(func=cmd_score)

    p_srv = sub.add_parser("serve", help="Run HTTP server (POST /score).")
    p_srv.add_argument("--config", required=True, help="Path to config.yaml")
    p_srv.add_argument("--db", required=True, help="SQLite path for baseline stats.")
    p_srv.add_argument("--host", default="127.0.0.1", help="Bind host (default 127.0.0.1).")
    p_srv.add_argument("--port", type=int, default=8080, help="Bind port (default 8080).")
    p_srv.set_defaults(func=cmd_serve)

    args = p.parse_args()
    raise SystemExit(args.func(args))
