from __future__ import annotations

import math
from typing import Any

import pandas as pd


def _num(value: Any) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else math.nan
    except (TypeError, ValueError):
        return math.nan


def _score_label(value: Any) -> str:
    v = _num(value)
    if not math.isfinite(v):
        return "saknar tillräcklig data"
    if v >= 75:
        return "starkt"
    if v >= 60:
        return "bra"
    if v >= 45:
        return "blandat"
    return "svagt"


def intent_match_reason(row: pd.Series | dict[str, Any], intent: str) -> str:
    """Explain the selected discovery intent using only fields already present in the row."""
    if intent == "Bra långsiktig investering":
        return f"Långsiktsbilden är {_score_label(row.get('INVEST Score'))}, med {_score_label(row.get('Kvalitet'))} kvalitet och {_score_label(row.get('Risk'))} riskbetyg."
    if intent == "Utdelningsaktier":
        dy = _num(row.get("Direktavkastning"))
        dy_text = f"{dy:.1%}".replace(".", ",") if math.isfinite(dy) else "okänd"
        return f"Registrerad direktavkastning är {dy_text}; kvaliteten är {_score_label(row.get('Kvalitet'))} och riskbetyget {_score_label(row.get('Risk'))}."
    if intent == "Billiga kvalitetsbolag":
        return f"Värderingen ser {_score_label(row.get('Värdering'))} ut samtidigt som bolagskvaliteten är {_score_label(row.get('Kvalitet'))}."
    if intent == "Aktier som fallit mycket":
        return f"Borsifys vändningsbedömning är {_score_label(row.get('REVERSAL Score'))}; riskbetyget är samtidigt {_score_label(row.get('Risk'))}."
    if intent == "Kortsiktigt köpläge":
        return f"Det kortsiktiga kursläget är {_score_label(row.get('SWING Score'))}; detta är en timingbedömning, inte ett bevis på att aktien är billig."
    if intent == "Stabilare aktier":
        return f"Riskbetyget är {_score_label(row.get('Risk'))} och kvaliteten {_score_label(row.get('Kvalitet'))}, vilket väger tungt i detta val."
    return f"Den samlade Borsify-bedömningen är {_score_label(row.get('Borsify Score'))} jämfört med övriga aktier som klarat dina filter."


def horizon_match_reason(row: pd.Series | dict[str, Any], horizon: str) -> str:
    mapping = {
        "1–2 dagar": ("Daytrade Score", "1–2 dagar"),
        "1 vecka–3 månader": ("Mellan Score", "1 vecka–3 månader"),
        "1–5 år": ("Lång Score", "1–5 år"),
        "Mycket lång sikt": ("Livstid Score", "mycket lång sikt"),
    }
    if horizon == "Alla tidshorisonter":
        return "Du har inte valt en särskild tidshorisont, så ingen enskild tidsmodell prioriteras."
    score_col, label = mapping.get(horizon, (None, horizon))
    if not score_col:
        return f"Borsify prioriterar din valda tidshorisont: {label}."
    return f"Borsifys befintliga modell för {label} bedömer läget som {_score_label(row.get(score_col))}."


def requirement_statuses(row: pd.Series | dict[str, Any], horizon: str) -> list[str]:
    """Small, human-readable checks; deliberately not a new score or probability."""
    checks: list[tuple[str, Any, float]] = [("Data", row.get("Datatäckning"), 0.60)]
    if horizon == "1–2 dagar":
        checks += [("Kursläge", row.get("Daytrade Score"), 60), ("Risk", row.get("Risk"), 45)]
    elif horizon == "1 vecka–3 månader":
        checks += [("Kursläge", row.get("Mellan Score"), 60), ("Kvalitet", row.get("Kvalitet"), 45)]
    elif horizon == "1–5 år":
        checks += [("Långsiktigt", row.get("Lång Score"), 60), ("Kvalitet", row.get("Kvalitet"), 50)]
    elif horizon == "Mycket lång sikt":
        checks += [("Mycket lång sikt", row.get("Livstid Score"), 60), ("Kvalitet", row.get("Kvalitet"), 55)]
    else:
        checks += [("Borsify", row.get("Borsify Score"), 60), ("Risk", row.get("Risk"), 45)]

    out: list[str] = []
    for label, raw, threshold in checks:
        v = _num(raw)
        if not math.isfinite(v):
            out.append(f"⚪ {label}: saknas")
            continue
        # Datatäckning is stored 0..1 while other scores are 0..100.
        passed = v >= threshold
        out.append(f"{'✓' if passed else '△'} {label}: {'klarar' if passed else 'svagare'}")
    return out


def main_risk_text(row: pd.Series | dict[str, Any]) -> str:
    for key in ("Största risk", "Riskflaggor", "Devils Advocate", "Devil's Advocate", "Risktext"):
        value = str(row.get(key, "") or "").strip()
        if value and value.lower() not in {"nan", "—", "inga"}:
            return value
    risk = _num(row.get("Risk"))
    if math.isfinite(risk) and risk < 45:
        return "Riskbetyget är svagt. Kontrollera vad som driver risken innan du går vidare."
    return "Ingen enskild huvudrisk är tydligt verifierad i den här snabblistan. Öppna fördjupningen innan köp."


def data_status_text(row: pd.Series | dict[str, Any]) -> str:
    trust = str(row.get("Datastatus", row.get("Data status", "")) or "").strip()
    if trust and trust.lower() != "nan":
        return trust
    coverage = _num(row.get("Datatäckning"))
    if not math.isfinite(coverage):
        return "Datastatus oklar"
    if coverage >= .80:
        return "Bra datatäckning"
    if coverage >= .60:
        return "Godtagbar datatäckning"
    return "Begränsad datatäckning"


def near_miss_reason(row: pd.Series | dict[str, Any], intent: str, horizon: str) -> str:
    parts = [intent_match_reason(row, intent)]
    if horizon != "Alla tidshorisonter":
        parts.append(horizon_match_reason(row, horizon))
    parts.append("Den hamnade utanför den visade kortlistan eftersom andra kvarvarande aktier rankades högre för just dina val.")
    return " ".join(parts)
