from __future__ import annotations
"""Estimate how long a verified recognition path may need to become visible.

Advisory only. The engine uses explicit point-in-time timing buckets and never
turns missing or vague timing into a date. It does not affect ranking.
"""

import math
import re
from typing import Any

import numpy as np
import pandas as pd


def _n(value: Any) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else np.nan
    except Exception:
        return np.nan


def _yes(value: Any) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "ja"}


def _timing_bucket(timing: str) -> tuple[str, str]:
    """Return a conservative bucket and its evidence explanation."""
    text = str(timing or "").strip().lower()
    if not text or text in {"—", "-", "okänd", "unknown"}:
        return "UNKNOWN", "ingen verifierbar timing finns"
    if any(token in text for token in ("inom en vecka", "inom en månad")):
        return "NEAR", f"explicit tidsangivelse: {timing}"
    if "inom cirka tre månader" in text or "nästa 1–2 rapporter" in text:
        return "MEDIUM", f"explicit men grovt tidsfönster: {timing}"
    if "6–18 månader" in text or "6-18 månader" in text or "nästa 1–3 rapporter" in text:
        return "LONG", f"explicit långsiktigt tidsfönster: {timing}"
    if text == "idag":
        return "RECENT", "verifierad händelse inträffade idag"
    match = re.fullmatch(r"(\d+) dagar sedan", text)
    if match and int(match.group(1)) <= 30:
        return "RECENT", f"verifierad händelse inträffade {match.group(1)} dagar sedan"
    return "UNKNOWN", f"tidsangivelsen '{timing}' kan inte översättas säkert till ett recognition-fönster"


def assess_recognition_window(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    path_status = str(row.get("Catalyst-to-Recognition status") or "")
    timing = str(row.get("Catalyst Timing") or "—")
    catalyst_verified = _yes(row.get("Catalyst Independent Support"))
    report_days = _n(row.get("Post-report dagar sedan"))
    kpi = _n(row.get("KPI Inflection nivå"))
    revisions = _n(row.get("Revision breadth nivå"))
    confidence = _n(row.get("Analysis Confidence Score"))
    upside = _n(row.get("Riktkurs potential"))

    reasons: list[str] = []
    warnings: list[str] = []
    bucket = "UNKNOWN"

    eligible = path_status in {
        "STRONG_RECOGNITION_PATH", "POSSIBLE_RECOGNITION_PATH", "LOW_CONFIDENCE_PATH"
    }
    if path_status == "RECOGNITION_IN_PROGRESS":
        warnings.append("prisreaktionen tyder på att recognition redan kan vara igång")
    elif not eligible:
        warnings.append("ingen tillräckligt verifierad recognition-path finns")
    else:
        timing_bucket, timing_reason = _timing_bucket(timing)
        # Explicit catalyst timing is usable only when the catalyst itself has
        # independent support. A scheduled report may still be useful when the
        # existing path engine verified improving KPI/revisions.
        if catalyst_verified and timing_bucket in {"NEAR", "MEDIUM", "LONG"}:
            bucket = timing_bucket
            reasons.append(timing_reason)
        elif timing_bucket in {"NEAR", "MEDIUM"} and (kpi >= 2 or revisions >= 2):
            bucket = timing_bucket
            reasons.append(timing_reason + " med redan observerad KPI-/estimatförbättring")
        elif timing_bucket == "RECENT" and np.isfinite(report_days) and 0 <= report_days <= 30 and (kpi >= 2 or revisions >= 2):
            bucket = "NEAR"
            reasons.append("färsk verifierad händelse och förbättring kan ge kort efterreaktionsfönster")
        else:
            warnings.append(timing_reason)

    if np.isfinite(confidence) and confidence < 45:
        if bucket != "UNKNOWN":
            warnings.append("lågt analysförtroende blockerar ett bestämt tidsfönster")
        bucket = "UNKNOWN"

    labels = {
        "NEAR": "⚡ Recognition sannolikt nära",
        "MEDIUM": "⏳ Medellångt recognition-fönster",
        "LONG": "🌱 Långt recognition-fönster",
        "UNKNOWN": "❔ Recognition-timing okänd",
    }
    levels = {"NEAR": 3, "MEDIUM": 2, "LONG": 1, "UNKNOWN": 0}

    # Target upside is an observed analyst input, not intrinsic value or proof.
    payoff_status = "UNKNOWN"
    payoff_label = "— Uppsida/väntetid kan inte bedömas"
    if bucket != "UNKNOWN" and np.isfinite(upside):
        hurdle = {"NEAR": .15, "MEDIUM": .20, "LONG": .30}[bucket]
        if upside >= hurdle:
            payoff_status = "ATTRACTIVE"
            payoff_label = "🟢 Attraktiv observerad uppsida relativt väntetiden"
        elif upside >= hurdle * .55:
            payoff_status = "MIXED"
            payoff_label = "🟡 Måttlig observerad uppsida relativt väntetiden"
        else:
            payoff_status = "WEAK"
            payoff_label = "🟠 Svag observerad uppsida relativt väntetiden"
        reasons.append(f"observerad riktkurspotential {upside:.0%}; tröskeln för detta grova fönster är {hurdle:.0%}")
        warnings.append("riktkurspotential är stöd från konsensus, inte bevis på faktisk uppsida")
    elif bucket != "UNKNOWN":
        warnings.append("verifierbar uppsidedata saknas; väntetidsjusterad asymmetri lämnas okänd")

    score = {"NEAR": 75.0, "MEDIUM": 55.0, "LONG": 35.0, "UNKNOWN": 0.0}[bucket]
    if payoff_status == "ATTRACTIVE":
        score += 10
    elif payoff_status == "WEAK":
        score -= 10
    score = float(np.clip(score, 0, 100))

    explanation = f"Recognition Window {score:.0f}/100 · {labels[bucket]}. "
    if reasons:
        explanation += "Stöd: " + "; ".join(reasons[:4]) + ". "
    if warnings:
        explanation += "Begränsningar: " + "; ".join(warnings[:4]) + ". "
    explanation += "Fönstret är en grov evidensklass, inte ett datum eller en prognos, och påverkar inte rankingen."

    return {
        "Recognition Window": labels[bucket],
        "Recognition Window status": bucket,
        "Recognition Window nivå": levels[bucket],
        "Recognition Window Score": score,
        "Recognition Window timing input": timing,
        "Recognition Window payoff": payoff_label,
        "Recognition Window payoff status": payoff_status,
        "Recognition Window observed upside": upside,
        "Recognition Window reasons": "; ".join(reasons),
        "Recognition Window warnings": "; ".join(warnings),
        "Recognition Window förklaring": explanation,
    }


def add_recognition_window(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    extra = pd.DataFrame([assess_recognition_window(row) for _, row in out.iterrows()], index=out.index)
    overlap = [column for column in extra.columns if column in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    return out.join(extra)
