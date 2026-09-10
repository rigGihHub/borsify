from __future__ import annotations

"""Point-in-time memory for Consensus Change.

Stores only observations actually seen by Borsify. It never reconstructs or
backfills analyst history. Comparison requires an older stored snapshot.
"""

import math
import sqlite3
from datetime import date
from typing import Any

import numpy as np

FIELDS = (
    "Konsensus analytiker antal", "Konsensus bullish andel", "Konsensus bearish andel",
    "Riktkurs medel", "Riktkurs median", "Riktkurs hög", "Riktkurs låg", "Riktkurs dispersion",
    "Konsensus uppgraderingar 45d", "Konsensus nedgraderingar 45d", "Konsensus initierad bevakning 45d",
)


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def ensure_consensus_memory_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS consensus_change_snapshots (
            symbol TEXT NOT NULL,
            captured_date TEXT NOT NULL,
            analyst_count REAL, bull_share REAL, bear_share REAL,
            target_mean REAL, target_median REAL, target_high REAL, target_low REAL, target_dispersion REAL,
            upgrades_45d REAL, downgrades_45d REAL, initiations_45d REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(symbol, captured_date)
        )
    """)


def snapshot_from_result(symbol: str, result: dict[str, Any], captured_date: str | None = None) -> dict[str, Any]:
    return {
        "symbol": str(symbol).strip().upper(),
        "captured_date": str(captured_date or date.today().isoformat()),
        "analyst_count": _num(result.get("Konsensus analytiker antal")),
        "bull_share": _num(result.get("Konsensus bullish andel")),
        "bear_share": _num(result.get("Konsensus bearish andel")),
        "target_mean": _num(result.get("Riktkurs medel")),
        "target_median": _num(result.get("Riktkurs median")),
        "target_high": _num(result.get("Riktkurs hög")),
        "target_low": _num(result.get("Riktkurs låg")),
        "target_dispersion": _num(result.get("Riktkurs dispersion")),
        "upgrades_45d": _num(result.get("Konsensus uppgraderingar 45d")),
        "downgrades_45d": _num(result.get("Konsensus nedgraderingar 45d")),
        "initiations_45d": _num(result.get("Konsensus initierad bevakning 45d")),
    }


def previous_snapshot(conn: sqlite3.Connection, symbol: str, before_date: str) -> dict[str, Any] | None:
    ensure_consensus_memory_table(conn)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM consensus_change_snapshots WHERE symbol=? AND captured_date<? ORDER BY captured_date DESC LIMIT 1",
        (str(symbol).strip().upper(), str(before_date)),
    ).fetchone()
    return dict(row) if row else None


def save_snapshot(conn: sqlite3.Connection, snapshot: dict[str, Any]) -> None:
    ensure_consensus_memory_table(conn)
    cols = ["symbol", "captured_date", "analyst_count", "bull_share", "bear_share", "target_mean", "target_median", "target_high", "target_low", "target_dispersion", "upgrades_45d", "downgrades_45d", "initiations_45d"]
    conn.execute(
        f"INSERT OR IGNORE INTO consensus_change_snapshots({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})",
        [snapshot.get(c) for c in cols],
    )


def compare_consensus_memory(current: dict[str, Any], previous: dict[str, Any] | None) -> dict[str, Any]:
    if not previous:
        return {
            "Konsensusminne status": "För lite historik",
            "Konsensusminne historik": False,
            "Konsensusminne positiv": False,
            "Konsensusminne negativ": False,
            "Konsensusminne förklaring": "Borsify har ännu inget äldre PIT-snapshot att jämföra med. Ingen historik återskapas i efterhand.",
        }

    bull_delta = _num(current.get("bull_share")) - _num(previous.get("bull_share"))
    median_now, median_prev = _num(current.get("target_median")), _num(previous.get("target_median"))
    median_delta = median_now / median_prev - 1 if np.isfinite(median_now) and np.isfinite(median_prev) and median_prev > 0 else np.nan
    disp_now, disp_prev = _num(current.get("target_dispersion")), _num(previous.get("target_dispersion"))
    disp_delta = disp_now - disp_prev if np.isfinite(disp_now) and np.isfinite(disp_prev) else np.nan
    count_delta = _num(current.get("analyst_count")) - _num(previous.get("analyst_count"))

    improving_breadth = np.isfinite(bull_delta) and bull_delta >= 0.05
    rising_targets = np.isfinite(median_delta) and median_delta >= 0.03
    converging_higher = rising_targets and np.isfinite(disp_delta) and disp_delta <= -0.05
    broadening = improving_breadth and np.isfinite(count_delta) and count_delta >= 1
    weakening = (np.isfinite(bull_delta) and bull_delta <= -0.05) or (np.isfinite(median_delta) and median_delta <= -0.05)

    if weakening:
        status = "Konsensus försämras"
        why = "Jämfört med Borsifys föregående frysta snapshot har analytikernas syn försvagats."
    elif converging_higher:
        status = "Riktkurserna samlas kring högre nivå"
        why = "Riktkursmedianen har stigit samtidigt som spridningen mellan riktkurserna har minskat."
    elif broadening:
        status = "Positiv syn breddas"
        why = "Köpandelen har ökat och fler analytiker ingår nu i den frysta konsensusbilden."
    elif improving_breadth and rising_targets:
        status = "Konsensus förbättras snabbt"
        why = "Både köpandelen och riktkursmedianen har förbättrats sedan föregående PIT-snapshot."
    elif improving_breadth:
        status = "Fler analytiker blir positiva"
        why = "Köpandelen har ökat tydligt sedan föregående frysta snapshot."
    elif rising_targets:
        status = "Riktkurserna höjs"
        why = "Riktkursmedianen har stigit tydligt sedan föregående frysta snapshot."
    else:
        status = "Ingen tydlig förändring ännu"
        why = "Det finns PIT-historik, men förändringen är ännu inte tillräckligt tydlig."

    return {
        "Konsensusminne status": status,
        "Konsensusminne historik": True,
        "Konsensusminne positiv": bool(not weakening and (improving_breadth or rising_targets)),
        "Konsensusminne negativ": bool(weakening),
        "Konsensusminne köpandel förändring": bull_delta,
        "Konsensusminne riktkursmedian förändring": median_delta,
        "Konsensusminne dispersion förändring": disp_delta,
        "Konsensusminne analytiker förändring": count_delta,
        "Konsensusminne jämförelsedatum": previous.get("captured_date", ""),
        "Konsensusminne förklaring": why,
    }
