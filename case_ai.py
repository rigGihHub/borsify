from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd


SHORT_FIELDS = [
    "Ticker", "Namn", "Sektor", "Pris",
    "Short Alpha Score", "Short Alpha Gate", "Short Alpha Confidence",
    "Short Relative Strength", "Short Relative Text", "Short Trend",
    "Short Momentum", "Short Participation", "Short Revisions",
    "Short Catalyst", "Short Confirmation Count", "Short Why Now",
    "Short Counterargument", "Short Vetoes", "Short Cautions",
    "Inflection Signal", "Inflection Score", "Catalyst Signal",
    "Primary Catalyst", "Catalyst Timing", "Catalyst Evidence",
]

LONG_FIELDS = [
    "Ticker", "Namn", "Sektor", "Pris", "INVEST Score",
    "Case Gate", "Case Confidence", "Case Evidence Count", "Case Veto Count",
    "Case Supports", "Case Neutrals", "Case Vetoes",
    "Djupkontroll", "Value Trap Risk", "Deep Confidence",
    "Inflection Signal", "Inflection Score", "Varför nu",
    "Mispricing Signal", "Mispricing Confidence",
    "Required EPS CAGR base", "Growth Proxy", "FCF Growth Hurdle",
    "Scenario Verdict", "Scenario Asymmetry", "Scenario Confidence",
    "Bear upside", "Bear annualized return", "Bear EPS growth", "Bear exit P/E",
    "Base upside", "Base annualized return", "Base EPS growth", "Base exit P/E",
    "Bull upside", "Bull annualized return", "Bull EPS growth", "Bull exit P/E",
    "Catalyst Signal", "Catalyst Confidence", "Primary Catalyst",
    "Catalyst Timing", "Catalyst Effect", "Catalyst Evidence",
    "Catalyst Why Now", "Catalyst Warnings",
    "Varför marknaden kan ha fel", "Devil's Advocate",
    "P/E", "Forward P/E", "P/B", "EV/EBITDA", "FCF yield",
    "ROE", "Vinstmarginal", "Skuld/eget kapital",
    "Omsättning CAGR", "Vinst CAGR", "FCF CAGR",
]


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        x = float(value)
        return x if math.isfinite(x) else None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return value


def build_case_ai_context(case: dict[str, Any] | pd.Series, horizon: str) -> dict[str, Any]:
    """Return only the fields that Borsify actually has for this recommendation."""
    horizon = str(horizon).lower().strip()
    fields = SHORT_FIELDS if horizon == "short" else LONG_FIELDS
    raw = case.to_dict() if isinstance(case, pd.Series) else dict(case)
    data = {}
    for field in fields:
        if field not in raw:
            continue
        value = _clean(raw.get(field))
        if value is None or value == "" or value == "—":
            continue
        data[field] = value
    return {
        "horizon": "1–6 månader" if horizon == "short" else "2–5 år",
        "case_data": data,
        "important_limitations": [
            "Borsify-data kan vara fördröjd eller ofullständig.",
            "Confidence är evidenstäckning, inte sannolikheten att aktien stiger.",
            "Scenarioer är antagandebaserade och inte riktkurser eller sannolikheter.",
            "Extern rubrikdata är inte samma sak som verifierad ekonomisk effekt.",
            "Svaret får inte fylla luckor med påhittade fakta.",
        ],
    }


def build_case_ai_instructions() -> str:
    return """Du är Borsify AI, en kritisk analytiker inuti en aktieanalysapp.
Svara på svenska och utgå ENDAST från den bifogade Borsify-datan för just detta case.

Ditt jobb är att förklara varför modellen lyfter eller inte lyfter aktien, inte att försvara modellen.
Var skeptisk både mot marknaden och mot Borsifys egen analys.

Regler:
- Börja med ett direkt svar på användarens fråga.
- Hänvisa konkret till relevanta datapunkter från caset.
- Om användaren frågar varför aktien rekommenderas trots hög kurs, stark uppgång eller hög värdering:
  skilj tydligt mellan absolut aktiekurs, tidigare kursuppgång, relativ styrka och faktisk värdering.
- Lyft alltid det starkaste motargumentet när frågan gäller varför aktien är attraktiv.
- Säg vad som skulle få Borsify att ändra uppfattning.
- Säg uttryckligen när data inte räcker för att besvara något.
- Hitta aldrig på nyheter, estimat, riktkurser, historik eller bolagsfakta som inte finns i kontexten.
- Presentera inte Confidence som sannolikhet.
- Ge inte personligt anpassade köp-/säljråd. Formulera svaret som analys av caset.
- Håll standardsvaret kort: ungefär 120–220 ord, om inte användaren ber om mer.
"""


def build_case_ai_input(case: dict[str, Any] | pd.Series, horizon: str, question: str) -> str:
    context = build_case_ai_context(case, horizon)
    return (
        "ANVÄNDARENS FRÅGA:\n"
        + str(question).strip()
        + "\n\nBORSIFY-KONTEXT FÖR CASET:\n"
        + json.dumps(context, ensure_ascii=False, indent=2, sort_keys=True)
    )


def local_case_explanation(case: dict[str, Any] | pd.Series, horizon: str) -> str:
    """Safe non-AI fallback shown when no API key is configured."""
    raw = case.to_dict() if isinstance(case, pd.Series) else dict(case)
    name = str(raw.get("Namn") or raw.get("Ticker") or "Aktien")
    if horizon == "short":
        why = str(raw.get("Short Why Now") or "Ingen tydlig kortsiktig förklaring finns.")
        counter = str(raw.get("Short Counterargument") or "Motargument saknas i tillgänglig data.")
        gate = str(raw.get("Short Alpha Gate") or "—")
        return (
            f"{name} har bedömningen **{gate}**. Borsifys registrerade VARFÖR NU är: {why} "
            f"Det viktigaste registrerade motargumentet är: {counter} "
            "Detta är ett regelbaserat reservsvar; aktivera AI för öppna följdfrågor."
        )
    supports = raw.get("Case Supports") or []
    if isinstance(supports, list):
        support_text = "; ".join(map(str, supports)) or "inga tydliga stöd registrerade"
    else:
        support_text = str(supports)
    counter = str(raw.get("Devil's Advocate") or raw.get("Case Vetoes") or "Motargument saknas i tillgänglig data.")
    gate = str(raw.get("Case Gate") or "—")
    return (
        f"{name} har bedömningen **{gate}**. Registrerade stöd: {support_text}. "
        f"Starkaste motargument: {counter}. "
        "Detta är ett regelbaserat reservsvar; aktivera AI för öppna följdfrågor."
    )
