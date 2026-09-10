from __future__ import annotations

"""Point-in-time memory for Report Delta.

One immutable snapshot is stored per symbol and verified report date. Borsify never
reconstructs earlier reports from today's data and never creates multiple historical
observations for the same report merely because the scanner runs again.
"""

import math
import sqlite3
from typing import Any

import numpy as np


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _clean_date(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 and text[:4].isdigit() else ""


def ensure_report_delta_memory_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS report_delta_snapshots (
            symbol TEXT NOT NULL,
            report_date TEXT NOT NULL,
            captured_date TEXT NOT NULL,
            eps_surprise REAL,
            revenue_yoy REAL,
            revenue_acceleration REAL,
            margin_change REAL,
            fcf_yoy REAL,
            earnings_yoy REAL,
            eps_estimate_change REAL,
            revision_balance REAL,
            evidence_count REAL,
            positive_count REAL,
            negative_count REAL,
            candidate INTEGER NOT NULL DEFAULT 0,
            underreaction INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(symbol, report_date)
        )
    """)


def snapshot_from_report_delta(
    symbol: str,
    metrics: dict[str, Any] | None,
    post_report: dict[str, Any] | None,
    report_delta: dict[str, Any] | None,
    captured_date: str,
) -> dict[str, Any] | None:
    m, p, r = metrics or {}, post_report or {}, report_delta or {}
    report_date = _clean_date(p.get("Post-report datum"))
    if not report_date:
        return None
    margin_yoy = _num(m.get("Marginal YoY förändring"))
    margin_qoq = _num(m.get("Marginal QoQ förändring"))
    margin_change = margin_yoy if np.isfinite(margin_yoy) else margin_qoq
    return {
        "symbol": str(symbol).strip().upper(),
        "report_date": report_date,
        "captured_date": _clean_date(captured_date) or str(captured_date),
        "eps_surprise": _num(m.get("Senaste EPS-överraskning")),
        "revenue_yoy": _num(m.get("Omsättning YoY senaste kvartal")),
        "revenue_acceleration": _num(m.get("Omsättning acceleration")),
        "margin_change": margin_change,
        "fcf_yoy": _num(m.get("FCF YoY senaste kvartal")),
        "earnings_yoy": _num(m.get("Vinst YoY senaste kvartal")),
        "eps_estimate_change": _num(m.get("EPS-estimat förändring")),
        "revision_balance": _num(m.get("EPS-revisionsbalans")),
        "evidence_count": _num(r.get("Report Delta evidens")),
        "positive_count": _num(r.get("Report Delta positiva")),
        "negative_count": _num(r.get("Report Delta negativa")),
        "candidate": int(bool(r.get("Report Delta kandidat"))),
        "underreaction": int(bool(r.get("Report Delta underreaktion"))),
        "status": str(r.get("Report Delta status") or ""),
    }


def previous_report_snapshot(conn: sqlite3.Connection, symbol: str, report_date: str) -> dict[str, Any] | None:
    ensure_report_delta_memory_table(conn)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM report_delta_snapshots WHERE symbol=? AND report_date<? ORDER BY report_date DESC LIMIT 1",
        (str(symbol).strip().upper(), str(report_date)),
    ).fetchone()
    return dict(row) if row else None


def save_report_snapshot(conn: sqlite3.Connection, snapshot: dict[str, Any] | None) -> None:
    if not snapshot:
        return
    ensure_report_delta_memory_table(conn)
    cols = [
        "symbol", "report_date", "captured_date", "eps_surprise", "revenue_yoy",
        "revenue_acceleration", "margin_change", "fcf_yoy", "earnings_yoy",
        "eps_estimate_change", "revision_balance", "evidence_count", "positive_count",
        "negative_count", "candidate", "underreaction", "status",
    ]
    conn.execute(
        f"INSERT OR IGNORE INTO report_delta_snapshots({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})",
        [snapshot.get(c) for c in cols],
    )


def _delta(cur: dict[str, Any], prev: dict[str, Any], field: str) -> float:
    a, b = _num(cur.get(field)), _num(prev.get(field))
    return a - b if np.isfinite(a) and np.isfinite(b) else np.nan


def compare_report_delta_memory(current: dict[str, Any] | None, previous: dict[str, Any] | None) -> dict[str, Any]:
    if not current:
        return {
            "Rapportminne status": "Rapportdatum saknas",
            "Rapportminne historik": False,
            "Rapportminne förbättring": False,
            "Rapportminne försämring": False,
            "Rapportminne förklaring": "Borsify har inget verifierat rapportdatum och skapar därför inget historiskt rapportsnapshot.",
        }
    if not previous:
        return {
            "Rapportminne status": "För lite rapporthistorik",
            "Rapportminne historik": False,
            "Rapportminne förbättring": False,
            "Rapportminne försämring": False,
            "Rapportminne rapportdatum": current.get("report_date", ""),
            "Rapportminne förklaring": "Detta är första rapporten som Borsify har fryst för bolaget. Ingen äldre rapport återskapas i efterhand.",
        }

    pos_delta = _delta(current, previous, "positive_count")
    neg_delta = _delta(current, previous, "negative_count")
    rev_acc_delta = _delta(current, previous, "revenue_acceleration")
    margin_delta = _delta(current, previous, "margin_change")
    fcf_delta = _delta(current, previous, "fcf_yoy")
    earnings_delta = _delta(current, previous, "earnings_yoy")
    est_delta = _delta(current, previous, "eps_estimate_change")

    positive_steps = sum([
        bool(np.isfinite(pos_delta) and pos_delta >= 2),
        bool(np.isfinite(neg_delta) and neg_delta <= -1),
        bool(np.isfinite(rev_acc_delta) and rev_acc_delta >= 0.03),
        bool(np.isfinite(margin_delta) and margin_delta >= 0.015),
        bool(np.isfinite(fcf_delta) and fcf_delta >= 0.15),
        bool(np.isfinite(earnings_delta) and earnings_delta >= 0.10),
        bool(np.isfinite(est_delta) and est_delta >= 0.02),
    ])
    negative_steps = sum([
        bool(np.isfinite(neg_delta) and neg_delta >= 2),
        bool(np.isfinite(pos_delta) and pos_delta <= -2),
        bool(np.isfinite(rev_acc_delta) and rev_acc_delta <= -0.05),
        bool(np.isfinite(margin_delta) and margin_delta <= -0.02),
        bool(np.isfinite(fcf_delta) and fcf_delta <= -0.25),
        bool(np.isfinite(earnings_delta) and earnings_delta <= -0.20),
        bool(np.isfinite(est_delta) and est_delta <= -0.02),
    ])

    improved = positive_steps >= 2 and positive_steps > negative_steps
    weakened = negative_steps >= 2 and negative_steps > positive_steps
    if improved:
        status = "Rapportförändringen förbättras"
        why = "Den senaste frysta rapporten visar en bredare förbättring än bolagets föregående rapport i Borsifys PIT-historik."
    elif weakened:
        status = "Rapportförändringen försämras"
        why = "Den senaste frysta rapporten är bredare svag än bolagets föregående rapport i Borsifys PIT-historik."
    else:
        status = "Ingen tydlig rapporttrend ännu"
        why = "Borsify har minst två frysta rapporter, men skillnaden är ännu inte tillräckligt bred för en tydlig trend."

    return {
        "Rapportminne status": status,
        "Rapportminne historik": True,
        "Rapportminne förbättring": bool(improved),
        "Rapportminne försämring": bool(weakened),
        "Rapportminne positiva förändring": pos_delta,
        "Rapportminne negativa förändring": neg_delta,
        "Rapportminne omsättningsacceleration förändring": rev_acc_delta,
        "Rapportminne marginal förändring": margin_delta,
        "Rapportminne FCF förändring": fcf_delta,
        "Rapportminne vinst förändring": earnings_delta,
        "Rapportminne estimat förändring": est_delta,
        "Rapportminne rapportdatum": current.get("report_date", ""),
        "Rapportminne jämförelserapport": previous.get("report_date", ""),
        "Rapportminne förklaring": why,
    }
