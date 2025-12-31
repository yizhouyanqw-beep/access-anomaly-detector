from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Optional

from .utils import json_dumps
from .models import AccessEvent
from .utils import parse_iso8601_utc, safe_get


class ScoreHandler(BaseHTTPRequestHandler):
    # injected at server init
    store = None
    cfg = None
    scorer = None

    def _send(self, status: int, body: Dict[str, Any]) -> None:
        data = json_dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/score":
            self._send(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw)
        except Exception as e:
            self._send(400, {"error": f"invalid json: {e}"})
            return

        # minimal validation
        missing = [k for k in ["timestamp", "actor_id", "resource_id", "resource_type", "action", "project_id"] if k not in payload]
        if missing:
            self._send(400, {"error": f"missing required fields: {missing}"})
            return

        try:
            ev = AccessEvent(
                timestamp=parse_iso8601_utc(str(payload["timestamp"])),
                actor_id=str(payload["actor_id"]),
                resource_id=str(payload["resource_id"]),
                resource_type=str(payload["resource_type"]),
                action=str(payload["action"]),
                project_id=str(payload["project_id"]),
                location=safe_get(payload, "location"),
                ip=safe_get(payload, "ip"),
                device_fingerprint=safe_get(payload, "device_fingerprint"),
                auth_method=safe_get(payload, "auth_method"),
                sensitivity=safe_get(payload, "sensitivity"),
                raw=dict(payload),
            )
            scored = self.scorer(ev, self.store, self.cfg, update_store=True)
            self.store.commit()
        except Exception as e:
            self._send(500, {"error": f"scoring failed: {e}"})
            return

        self._send(
            200,
            {
                "score": scored.score,
                "bucket": scored.bucket,
                "signals": scored.signals,
                "explanation": scored.explanation,
                "recommended_actions": scored.recommended_actions,
            },
        )


def serve(host: str, port: int, store, cfg, scorer) -> None:
    ScoreHandler.store = store
    ScoreHandler.cfg = cfg
    ScoreHandler.scorer = staticmethod(scorer)

    httpd = HTTPServer((host, port), ScoreHandler)
    print(f"Serving on http://{host}:{port} (POST /score, GET /health)")
    httpd.serve_forever()
