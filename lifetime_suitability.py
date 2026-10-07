"""Business suitability is mandatory even for observational lifetime alternatives."""
import math
import pandas as pd
from business_outlook import business_context


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def lifetime_blockers(row):
    reasons = []
    context = business_context(row)
    industry = str(row.get("Bransch", "")).lower()
    if context["Bransch klassificering"] in {"tankers", "lpg", "oil"} or any(x in industry for x in ("marine shipping", "oil & gas", "thermal coal", "coking coal")):
        reasons.append("starkt beroende av frakt- eller råvarucykler; hör inte hemma i kategorin långsiktigt ägande")
    elif not context["Bransch bedömd"]:
        reasons.append("verksamhetens långsiktiga branschrisk är inte tillräckligt bedömd")
    for field, label in [("Historik omsättning år", "omsättning"), ("Historik vinst år", "vinst"), ("Historik FCF år", "fritt kassaflöde")]:
        value = number(row.get(field))
        if not math.isfinite(value) or value < 3:
            reasons.append(f"minst tre separata års observationer av {label} krävs")
    for field, label in [("Positiv FCF-andel", "kassaflöde"), ("Positiv vinst-andel", "vinst")]:
        value = number(row.get(field))
        if not math.isfinite(value) or not .8 <= value <= 1:
            reasons.append(f"positivt {label} krävs under minst 80 % av observerade år")
    growth = number(row.get("Omsättning CAGR"))
    if not math.isfinite(growth) or growth < 0:
        reasons.append("flerårig omsättningsutveckling måste vara verifierad och inte krympande")
    for field, label in [("Senaste FCF", "senaste kassaflödet"), ("Senaste vinst", "senaste vinsten")]:
        if not math.isfinite(number(row.get(field))) or number(row.get(field)) <= 0:
            reasons.append(f"{label} måste vara verifierat positivt")
    if not math.isfinite(number(row.get("Deep Confidence"))) or number(row.get("Deep Confidence")) < 70:
        reasons.append("fördjupad flerårsanalys måste nå 70/100")
    # An industry label or a high ROE is not evidence of a durable moat.
    moat = row.get("Konkurrensfördel verifierad")
    source = row.get("Konkurrensfördel källa")
    explanation = row.get("Konkurrensfördel underlag")
    observed = pd.to_datetime(row.get("Konkurrensfördel datum"), errors="coerce", utc=True)
    now = pd.Timestamp.now(tz="UTC")
    if (str(moat).lower() != "true" or not isinstance(source, str) or not source.startswith("https://")
            or not isinstance(explanation, str) or len(explanation.strip()) < 30
            or pd.isna(observed) or not 0 <= (now - observed).days <= 365):
        reasons.append("daterat källunderlag som verifierar en uthållig konkurrensfördel saknas")
    return reasons


def filter_lifetime_suitable(frame):
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    return frame.loc[[not lifetime_blockers(row) for _, row in frame.iterrows()]].copy()
