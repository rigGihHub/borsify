from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        out = float(value)
        return out if np.isfinite(out) else np.nan
    except (TypeError, ValueError):
        return np.nan


def evaluate_case_breakers(
    current: dict[str, Any],
    history: pd.DataFrame | None,
    rules: dict[str, Any],
) -> dict[str, Any]:
    """Check user-defined thesis-breaker rules without turning them into buy/sell advice."""
    score = _num(current.get("score"))
    quality = _num(current.get("quality"))
    risk = _num(current.get("risk"))

    min_score = _num(rules.get("min_score"))
    min_quality = _num(rules.get("min_quality"))
    min_risk = _num(rules.get("min_risk"))
    max_score_drop = _num(rules.get("max_score_drop"))

    first_score = np.nan
    if history is not None and not history.empty and "score" in history.columns:
        vals = pd.to_numeric(history["score"], errors="coerce").dropna()
        if not vals.empty:
            first_score = float(vals.iloc[0])

    triggered: list[str] = []
    near: list[str] = []
    active_rules = 0

    def enabled(v: float) -> bool:
        return bool(np.isfinite(v) and v > 0)

    if enabled(min_score):
        active_rules += 1
        if np.isfinite(score) and score < min_score:
            triggered.append(f"Borsify Score är {score:.0f}, under din gräns {min_score:.0f}.")
        elif np.isfinite(score) and score < min_score + 5:
            near.append(f"Borsify Score är nära din nedre gräns ({score:.0f} mot {min_score:.0f}).")

    if enabled(min_quality):
        active_rules += 1
        if np.isfinite(quality) and quality < min_quality:
            triggered.append(f"Kvalitet är {quality:.0f}, under din gräns {min_quality:.0f}.")
        elif np.isfinite(quality) and quality < min_quality + 5:
            near.append(f"Kvalitet är nära din nedre gräns ({quality:.0f} mot {min_quality:.0f}).")

    if enabled(min_risk):
        active_rules += 1
        if np.isfinite(risk) and risk < min_risk:
            triggered.append(f"Riskdelen är {risk:.0f}, under din trygghetsgräns {min_risk:.0f}. Lägre värde betyder sämre riskbild i Borsify.")
        elif np.isfinite(risk) and risk < min_risk + 5:
            near.append(f"Riskdelen är nära din nedre gräns ({risk:.0f} mot {min_risk:.0f}).")

    if enabled(max_score_drop) and np.isfinite(first_score) and np.isfinite(score):
        active_rules += 1
        drop = first_score - score
        if drop >= max_score_drop:
            triggered.append(f"Scoren har fallit {drop:.1f} poäng sedan första sparade analysen, mer än din gräns {max_score_drop:.1f}.")
        elif drop >= max(0.0, max_score_drop - 3):
            near.append(f"Scoren har fallit {drop:.1f} poäng och närmar sig din maxgräns {max_score_drop:.1f}.")

    if triggered:
        status = "Case-breaker utlöst"
        tone = "negative"
        explanation = "Minst ett villkor du själv sagt skulle försvaga investeringsidén har inträffat. Det betyder inte automatiskt sälj – men caset bör granskas på nytt."
    elif near:
        status = "Case-breaker nära"
        tone = "warning"
        explanation = "Inget villkor är brutet ännu, men minst en mätpunkt ligger nära din gräns."
    elif active_rules:
        status = "Caset håller enligt dina regler"
        tone = "positive"
        explanation = "Ingen av dina angivna case-breakers är utlöst i den senaste Borsify-mätningen."
    else:
        status = "Inga case-breakers satta"
        tone = "neutral"
        explanation = "Sätt egna gränser för vad som skulle få dig att ompröva investeringsidén."

    return {
        "status": status,
        "tone": tone,
        "explanation": explanation,
        "triggered": triggered,
        "near": near,
        "active_rules": active_rules,
        "first_score": first_score,
    }
