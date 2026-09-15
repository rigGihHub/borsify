from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROLES = ("incumbent", "evidence_gated")


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
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, int)):
        return value
    return str(value)


def build_first_choice_record(
    row: pd.Series | dict[str, Any], role: str, profile: str, market: str,
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    if role not in ROLES:
        raise ValueError(f"Unknown first-choice role: {role}")
    captured = captured_at or datetime.now(timezone.utc)
    if captured.tzinfo is None:
        captured = captured.replace(tzinfo=timezone.utc)
    ticker = str(row.get("Ticker") or "").strip().upper()
    captured_date = captured.date().isoformat()
    identity = "|".join([captured_date, str(profile), str(market), role, ticker])
    record_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    frozen_fields = [
        "Ticker", "Namn", "Pris", "Prisdatum", "Borsify Score", "Dagens relevans",
        "Value Trap verdict", "Ingångsläge nivå", "Bolagsbedömning nivå",
        "Analysis Confidence nivå", "Analysis Confidence Score", "Deal Conviction Score",
        "Recognition Window status", "Decision Brief tes", "Decision Brief risk",
        "Förstaval godkänd", "Förstaval blockerare",
    ]
    snapshot = {field: _safe(row.get(field)) for field in frozen_fields}
    return {
        "record_id": record_id,
        "captured_at": captured.isoformat(),
        "captured_date": captured_date,
        "profile": str(profile),
        "market": str(market),
        "role": role,
        "symbol": ticker,
        "price": _safe(row.get("Pris")),
        "score": _safe(row.get("Borsify Score")),
        "blockers": str(row.get("Förstaval blockerare") or ""),
        "snapshot_json": json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
    }


def _ensure_table(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS first_choice_audit (
            record_id TEXT PRIMARY KEY,
            captured_at TEXT NOT NULL,
            captured_date TEXT NOT NULL,
            profile TEXT NOT NULL,
            market TEXT NOT NULL,
            role TEXT NOT NULL,
            symbol TEXT NOT NULL,
            price REAL,
            score REAL,
            blockers TEXT NOT NULL DEFAULT '',
            snapshot_json TEXT NOT NULL
        )
        """
    )


def save_first_choice_records(db_path: str | Path, records: list[dict[str, Any]]) -> int:
    valid = [record for record in records if record.get("record_id") and record.get("symbol")]
    if not valid:
        return 0
    columns = ["record_id", "captured_at", "captured_date", "profile", "market", "role", "symbol", "price", "score", "blockers", "snapshot_json"]
    inserted = 0
    with sqlite3.connect(str(db_path)) as connection:
        _ensure_table(connection)
        for record in valid:
            before = connection.total_changes
            connection.execute(
                f"INSERT OR IGNORE INTO first_choice_audit({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                tuple(record.get(column) for column in columns),
            )
            inserted += int(connection.total_changes > before)
    return inserted


def get_first_choice_records(db_path: str | Path, limit: int = 500) -> pd.DataFrame:
    with sqlite3.connect(str(db_path)) as connection:
        _ensure_table(connection)
        return pd.read_sql_query(
            "SELECT * FROM first_choice_audit ORDER BY captured_at DESC LIMIT ?",
            connection, params=(max(1, int(limit)),),
        )
