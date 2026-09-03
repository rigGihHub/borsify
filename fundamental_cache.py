from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CACHE_MAX_AGE_HOURS = 24


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _safe_json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_json_value(v) for v in value]
    if isinstance(value, (str, bool)) or value is None:
        return value
    try:
        x=float(value)
        return x if math.isfinite(x) else None
    except Exception:
        return str(value)


def _connect(path: str | Path) -> sqlite3.Connection:
    conn=sqlite3.connect(str(path), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fundamental_cache (
            symbol TEXT PRIMARY KEY,
            payload_json TEXT NOT NULL,
            fetched_at_utc TEXT NOT NULL
        )
        """
    )
    return conn


def get_cached_fundamentals(
    db_path: str | Path,
    symbol: str,
    max_age_hours: float=CACHE_MAX_AGE_HOURS,
    now: datetime | None=None,
) -> dict[str,Any] | None:
    now=now or _utcnow()
    with _connect(db_path) as conn:
        row=conn.execute(
            "SELECT payload_json, fetched_at_utc FROM fundamental_cache WHERE symbol=?",
            (str(symbol).upper(),),
        ).fetchone()
    if not row:
        return None
    try:
        fetched=datetime.fromisoformat(str(row[1]))
        if fetched.tzinfo is None:
            fetched=fetched.replace(tzinfo=timezone.utc)
        if now - fetched > timedelta(hours=float(max_age_hours)):
            return None
        payload=json.loads(str(row[0]))
        return payload if isinstance(payload,dict) else None
    except Exception:
        return None


def put_cached_fundamentals(
    db_path: str | Path,
    symbol: str,
    payload: dict[str,Any],
    now: datetime | None=None,
) -> None:
    now=now or _utcnow()
    serializable=_safe_json_value(payload)
    raw=json.dumps(serializable, ensure_ascii=False, allow_nan=False)
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO fundamental_cache(symbol,payload_json,fetched_at_utc)
            VALUES(?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET
                payload_json=excluded.payload_json,
                fetched_at_utc=excluded.fetched_at_utc
            """,
            (str(symbol).upper(), raw, now.isoformat()),
        )


def purge_old_fundamentals(
    db_path: str | Path,
    max_age_hours: float=72,
    now: datetime | None=None,
) -> int:
    now=now or _utcnow()
    cutoff=(now-timedelta(hours=float(max_age_hours))).isoformat()
    with _connect(db_path) as conn:
        cur=conn.execute(
            "DELETE FROM fundamental_cache WHERE fetched_at_utc < ?",
            (cutoff,),
        )
        return int(cur.rowcount or 0)
