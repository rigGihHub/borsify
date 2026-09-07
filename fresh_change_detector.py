from __future__ import annotations

import math
from typing import Any
import numpy as np


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _transition(current: float, previous: float, positive: float, negative: float) -> str:
    if not (np.isfinite(current) and np.isfinite(previous)):
        return "saknas"
    if current >= positive and previous < positive:
        return "ny positiv"
    if current <= negative and previous > negative:
        return "ny negativ"
    if current >= positive and previous >= positive:
        return "fortsatt positiv"
    if current <= negative and previous <= negative:
        return "fortsatt negativ"
    return "neutral"


def build_fresh_change(case: dict[str, Any]) -> dict[str, Any]:
    """Detect *new* fundamental direction changes, not merely good levels.

    Only point-in-time fields supplied in ``case`` are used. Missing prior-quarter
    evidence stays missing. This is an explanatory why-now layer, never a score.
    """
    checks = [
        ("Omsättning", _num(case.get("Omsättning YoY senaste kvartal")), _num(case.get("Omsättning YoY föregående kvartal")), .03, -.03),
        ("Marginal", _num(case.get("Marginal YoY förändring")), _num(case.get("Marginal YoY föregående kvartal")), .015, -.02),
        ("Kassaflöde", _num(case.get("FCF YoY senaste kvartal")), _num(case.get("FCF YoY föregående kvartal")), .15, -.25),
        ("Vinst", _num(case.get("Vinst YoY senaste kvartal")), _num(case.get("Vinst YoY föregående kvartal")), .10, -.20),
    ]
    new_pos, new_neg, continuing, available = [], [], [], 0
    details = []
    for label, cur, prev, pos, neg in checks:
        state = _transition(cur, prev, pos, neg)
        if state != "saknas":
            available += 1
        details.append(f"{label}: {state}")
        if state == "ny positiv": new_pos.append(label.lower())
        elif state == "ny negativ": new_neg.append(label.lower())
        elif state in {"fortsatt positiv", "fortsatt negativ"}: continuing.append(label.lower())

    eps = _num(case.get("EPS-estimat förändring"))
    balance = _num(case.get("EPS-revisionsbalans"))
    weight = _num(case.get("Estimat tillförlitlighetsvikt"))
    analyst_fresh = False
    analyst_negative = False
    if np.isfinite(weight) and weight >= .4:
        if (np.isfinite(eps) and eps >= .02) or (np.isfinite(balance) and balance >= .35):
            analyst_fresh = True
        if (np.isfinite(eps) and eps <= -.02) or (np.isfinite(balance) and balance <= -.35):
            analyst_negative = True

    if new_neg or analyst_negative:
        status = "Ny försämring upptäckt"
    elif len(new_pos) >= 2 or (new_pos and analyst_fresh):
        status = "Flera färska förbättringar"
    elif new_pos:
        status = "En färsk förbättring"
    elif analyst_fresh:
        status = "Färsk estimatförbättring"
    elif available < 2:
        status = "För lite jämförbar historik"
    else:
        status = "Ingen ny tydlig förändring"

    bits = []
    if new_pos: bits.append("ny förbättring i " + ", ".join(new_pos))
    if analyst_fresh: bits.append("analytikernas estimat/revideringar har vänt upp")
    if new_neg: bits.append("ny försämring i " + ", ".join(new_neg))
    if analyst_negative: bits.append("analytikernas estimat/revideringar har vänt ned")
    if not bits: bits.append("ingen tydlig ny fundamental förändring kan verifieras")

    return {
        "Fresh Change Status": status,
        "Fresh Change Summary": "; ".join(bits[:3]),
        "Fresh Change Positive Count": len(new_pos) + int(analyst_fresh),
        "Fresh Change Negative Count": len(new_neg) + int(analyst_negative),
        "Fresh Change Comparable Metrics": available,
        "Fresh Change New Positives": ", ".join(new_pos) if new_pos else "—",
        "Fresh Change New Negatives": ", ".join(new_neg) if new_neg else "—",
        "Fresh Change Detail": "; ".join(details),
    }
