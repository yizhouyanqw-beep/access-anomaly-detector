from __future__ import annotations

import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple


SCHEMA = """
CREATE TABLE IF NOT EXISTS actor_hour_hist (
  actor_id TEXT NOT NULL,
  hour_utc INTEGER NOT NULL,
  cnt INTEGER NOT NULL,
  last_seen_ts TEXT NOT NULL,
  PRIMARY KEY(actor_id, hour_utc)
);

CREATE TABLE IF NOT EXISTS actor_device (
  actor_id TEXT NOT NULL,
  device_fingerprint TEXT NOT NULL,
  cnt INTEGER NOT NULL,
  last_seen_ts TEXT NOT NULL,
  PRIMARY KEY(actor_id, device_fingerprint)
);

CREATE TABLE IF NOT EXISTS actor_resource_type (
  actor_id TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  cnt INTEGER NOT NULL,
  last_seen_ts TEXT NOT NULL,
  PRIMARY KEY(actor_id, resource_type)
);

CREATE TABLE IF NOT EXISTS resource_actor_recent (
  resource_id TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  last_seen_ts TEXT NOT NULL,
  PRIMARY KEY(resource_id, actor_id)
);
"""


def _ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class SQLiteStore:
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        for stmt in SCHEMA.strip().split(";"):
            s = stmt.strip()
            if s:
                self.conn.execute(s + ";")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---------- Reads ----------
    def get_actor_hour_count(self, actor_id: str, hour_utc: int) -> int:
        cur = self.conn.execute(
            "SELECT cnt FROM actor_hour_hist WHERE actor_id=? AND hour_utc=?",
            (actor_id, hour_utc),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def get_actor_total_events(self, actor_id: str) -> int:
        cur = self.conn.execute(
            "SELECT COALESCE(SUM(cnt),0) FROM actor_hour_hist WHERE actor_id=?",
            (actor_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def has_actor_device(self, actor_id: str, device_fingerprint: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM actor_device WHERE actor_id=? AND device_fingerprint=?",
            (actor_id, device_fingerprint),
        )
        return cur.fetchone() is not None

    def has_actor_resource_type(self, actor_id: str, resource_type: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM actor_resource_type WHERE actor_id=? AND resource_type=?",
            (actor_id, resource_type),
        )
        return cur.fetchone() is not None

    def count_distinct_actors_for_resource_lookback(
        self, resource_id: str, lookback_days: int, now_utc: datetime
    ) -> int:
        cutoff = now_utc.astimezone(timezone.utc) - timedelta(days=int(lookback_days))
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM resource_actor_recent WHERE resource_id=? AND last_seen_ts>=?",
            (resource_id, _ts(cutoff)),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0

    # ---------- Writes / Updates ----------
    def upsert_actor_hour(self, actor_id: str, hour_utc: int, seen_ts: datetime) -> None:
        self.conn.execute(
            """
            INSERT INTO actor_hour_hist(actor_id, hour_utc, cnt, last_seen_ts)
            VALUES(?,?,1,?)
            ON CONFLICT(actor_id, hour_utc) DO UPDATE SET
              cnt = cnt + 1,
              last_seen_ts = excluded.last_seen_ts
            """,
            (actor_id, hour_utc, _ts(seen_ts)),
        )

    def upsert_actor_device(self, actor_id: str, device_fingerprint: str, seen_ts: datetime) -> None:
        self.conn.execute(
            """
            INSERT INTO actor_device(actor_id, device_fingerprint, cnt, last_seen_ts)
            VALUES(?,?,1,?)
            ON CONFLICT(actor_id, device_fingerprint) DO UPDATE SET
              cnt = cnt + 1,
              last_seen_ts = excluded.last_seen_ts
            """,
            (actor_id, device_fingerprint, _ts(seen_ts)),
        )

    def upsert_actor_resource_type(self, actor_id: str, resource_type: str, seen_ts: datetime) -> None:
        self.conn.execute(
            """
            INSERT INTO actor_resource_type(actor_id, resource_type, cnt, last_seen_ts)
            VALUES(?,?,1,?)
            ON CONFLICT(actor_id, resource_type) DO UPDATE SET
              cnt = cnt + 1,
              last_seen_ts = excluded.last_seen_ts
            """,
            (actor_id, resource_type, _ts(seen_ts)),
        )

    def upsert_resource_actor_recent(self, resource_id: str, actor_id: str, seen_ts: datetime) -> None:
        self.conn.execute(
            """
            INSERT INTO resource_actor_recent(resource_id, actor_id, last_seen_ts)
            VALUES(?,?,?)
            ON CONFLICT(resource_id, actor_id) DO UPDATE SET
              last_seen_ts = excluded.last_seen_ts
            """,
            (resource_id, actor_id, _ts(seen_ts)),
        )

    def get_actor_resource_type_count(self, actor_id: str, resource_type: str) -> int:
        cur = self.conn.execute(
            "SELECT cnt FROM actor_resource_type WHERE actor_id=? AND resource_type=?",
            (actor_id, resource_type),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def get_actor_resource_type_total(self, actor_id: str) -> int:
        cur = self.conn.execute(
            "SELECT COALESCE(SUM(cnt),0) FROM actor_resource_type WHERE actor_id=?",
            (actor_id,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0


    def commit(self) -> None:
        self.conn.commit()
