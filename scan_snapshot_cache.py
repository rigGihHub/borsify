from __future__ import annotations

from datetime import datetime, timezone
from io import StringIO
import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from dividend_units import clean_legacy_dividend

import numpy as np
import pandas as pd


DEFAULT_MAX_AGE_MINUTES = 120


CORE_FUNDAMENTAL_FIELDS = ("P/E", "Forward P/E", "EV/EBITDA", "FCF-yield", "ROE", "Vinstmarginal", "Omsättningstillväxt", "Skuld/eget kapital")


def fundamental_coverage(frame: pd.DataFrame) -> dict[str, int]:
    """Observed finite core facts, independent of scores or purchase policy."""
    values = frame.reindex(columns=CORE_FUNDAMENTAL_FIELDS).apply(pd.to_numeric, errors="coerce")
    counts = np.isfinite(values).sum(axis=1)
    return {"rows": len(frame), "with_data": int((counts > 0).sum()),
            "complete": int((counts == len(CORE_FUNDAMENTAL_FIELDS)).sum()),
            "facts": int(counts.sum())}


def scan_reuse_seconds(frame: pd.DataFrame) -> int:
    """Failed fundamentals retry after five minutes, healthy scans after two hours."""
    return 7200 if fundamental_coverage(frame)["with_data"] else 300


def snapshot_source_health(frame: pd.DataFrame) -> dict[str, dict]:
    """Reconstruct observed acquisition health, including across sessions/restarts."""
    result = {}
    for index, row in frame.iterrows():
        status = row.get("Fundamental source status")
        if not isinstance(status, str) or not status:
            status = "UNKNOWN" if fundamental_coverage(pd.DataFrame([row]))["with_data"] else "NO_DATA"
        error = row.get("Fundamental source errors")
        result[str(row.get("Ticker", index))] = {
            "status": status, "attempts": 0,
            "circuit_open": row.get("Fundamental circuit open") is True,
            "errors": [error] if isinstance(error, str) and error else [],
        }
    return result


def symbol_set_key(symbols: list[str] | tuple[str, ...]) -> str:
    normalized = sorted({str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()})
    return hashlib.sha256("\n".join(normalized).encode("utf-8")).hexdigest()


def _safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _encode_frame(frame: pd.DataFrame) -> str:
    records = []
    for _, source in frame.iterrows():
        row = {}
        for key, value in source.items():
            if key == "_history" and isinstance(value, pd.DataFrame):
                row[key] = {
                    "kind": "dataframe-split",
                    "value": value.to_json(orient="split", date_format="iso"),
                }
            else:
                row[str(key)] = _safe(value)
        records.append(row)
    return json.dumps(records, ensure_ascii=False, separators=(",", ":"))


def _decode_frame(payload: str) -> pd.DataFrame:
    raw = json.loads(payload)
    rows = []
    for source in raw if isinstance(raw, list) else []:
        row = clean_legacy_dividend(source)
        history = row.get("_history")
        if isinstance(history, dict) and history.get("kind") == "dataframe-split":
            try:
                restored = pd.read_json(StringIO(str(history.get("value") or "")), orient="split")
                restored.index = pd.to_datetime(restored.index, errors="coerce")
                row["_history"] = restored
            except (ValueError, TypeError, json.JSONDecodeError):
                row["_history"] = pd.DataFrame()
        rows.append(row)
    return pd.DataFrame(rows)


def _ensure_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS scan_snapshot_cache (
            cache_key TEXT PRIMARY KEY,
            captured_at_utc TEXT NOT NULL,
            symbol_count INTEGER NOT NULL,
            row_count INTEGER NOT NULL,
            payload_json TEXT NOT NULL
        )
        """
    )


def put_scan_snapshot(db_path: str | Path, symbols: list[str], frame: pd.DataFrame) -> dict[str, Any]:
    if frame is None or frame.empty:
        return {"saved": False, "reason": "empty"}
    captured = datetime.now(timezone.utc).isoformat()
    key = symbol_set_key(symbols)
    payload = _encode_frame(frame)
    with sqlite3.connect(str(db_path)) as connection:
        _ensure_table(connection)
        previous = connection.execute("SELECT payload_json FROM scan_snapshot_cache WHERE cache_key=?", (key,)).fetchone()
        if previous:
            old = fundamental_coverage(_decode_frame(previous[0]))
            new = fundamental_coverage(frame)
            if new["rows"] < old["rows"] or new["with_data"] < old["with_data"] or new["facts"] < old["facts"]:
                return {"saved": False, "reason": "reduced_data_coverage", "previous": old, "current": new}
        connection.execute(
            """
            INSERT INTO scan_snapshot_cache(cache_key,captured_at_utc,symbol_count,row_count,payload_json)
            VALUES(?,?,?,?,?)
            ON CONFLICT(cache_key) DO UPDATE SET
              captured_at_utc=excluded.captured_at_utc,
              symbol_count=excluded.symbol_count,
              row_count=excluded.row_count,
              payload_json=excluded.payload_json
            """,
            (key, captured, len(set(symbols)), len(frame), payload),
        )
    return {"saved": True, "captured_at": captured, "rows": len(frame), "cache_key": key}


def get_scan_snapshot(
    db_path: str | Path,
    symbols: list[str],
    max_age_minutes: int = DEFAULT_MAX_AGE_MINUTES,
    now: datetime | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    key = symbol_set_key(symbols)
    try:
        with sqlite3.connect(str(db_path)) as connection:
            _ensure_table(connection)
            row = connection.execute(
                "SELECT captured_at_utc,symbol_count,row_count,payload_json FROM scan_snapshot_cache WHERE cache_key=?",
                (key,),
            ).fetchone()
    except sqlite3.Error as exc:
        return pd.DataFrame(), {"hit": False, "reason": type(exc).__name__}
    if not row:
        return pd.DataFrame(), {"hit": False, "reason": "missing"}
    try:
        captured = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
        if captured.tzinfo is None:
            captured = captured.replace(tzinfo=timezone.utc)
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        age_minutes = max(0.0, (current - captured).total_seconds() / 60.0)
        if age_minutes > max_age_minutes:
            return pd.DataFrame(), {"hit": False, "reason": "stale", "age_minutes": age_minutes, "captured_at": row[0]}
        frame = _decode_frame(str(row[3]))
        if frame.empty or len(frame) != int(row[2]):
            return pd.DataFrame(), {"hit": False, "reason": "invalid_payload"}
        if age_minutes * 60 >= scan_reuse_seconds(frame):
            return pd.DataFrame(), {"hit": False, "reason": "incomplete_retry_due", "age_minutes": age_minutes}
        return frame, {
            "hit": True,
            "captured_at": str(row[0]),
            "age_minutes": age_minutes,
            "symbol_count": int(row[1]),
            "row_count": int(row[2]),
        }
    except (ValueError, TypeError, json.JSONDecodeError):
        return pd.DataFrame(), {"hit": False, "reason": "invalid_payload"}


def clear_scan_snapshots(db_path: str | Path) -> int:
    try:
        with sqlite3.connect(str(db_path)) as connection:
            _ensure_table(connection)
            cursor = connection.execute("DELETE FROM scan_snapshot_cache")
            return max(0, int(cursor.rowcount or 0))
    except sqlite3.Error:
        return 0
