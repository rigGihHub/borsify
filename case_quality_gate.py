from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def build_case_quality_gate(case: dict[str, Any] | pd.Series) -> dict[str, Any]:
    """Evidence gate for long-term top cases.

    This deliberately does not create another weighted mega-score. Five largely
    independent pillars are checked: durable fundamentals, fresh change evidence,
    mispricing evidence, scenario asymmetry and a concrete re-rating catalyst. Data confidence is a prerequisite,
    while explicit risk signals can veto promotion.
    """
    deep_gate = str(case.get("Djupkontroll", "Otillräcklig data"))
    trap = _num(case.get("Value Trap Risk"))
    deep_conf = _num(case.get("Deep Confidence"))
    infl_conf = _num(case.get("Inflection Confidence"))
    infl_signal = str(case.get("Inflection Signal", "Otillräcklig förändringsdata"))
    mispricing = str(case.get("Mispricing Signal", "Kan inte bedömas"))
    scenario_status = str(case.get("Scenario Status", "Otillräcklig data"))
    scenario_verdict = str(case.get("Scenario Verdict", ""))
    asym = _num(case.get("Scenario Asymmetry"))
    scenario_conf = _num(case.get("Scenario Confidence"))
    catalyst_signal = str(case.get("Catalyst Signal", "Ingen tydlig katalysator verifierad"))
    catalyst_support = bool(case.get("Catalyst Support", False))
    catalyst_conf = _num(case.get("Catalyst Confidence"))

    supports: list[str] = []
    neutral: list[str] = []
    vetoes: list[str] = []

    # 1) Durable operating evidence.
    if deep_gate == "Klarar djupkontroll":
        supports.append("flerårsdata klarar den fundamentala djupkontrollen")
    elif deep_gate == "Neutral djupkontroll":
        neutral.append("flerårsdata är okej men inte tillräckligt stark för ett tydligt stöd")
    elif deep_gate == "Kräver extra kontroll":
        vetoes.append("fundamentala djupkontrollen kräver extra kontroll")
    elif deep_gate in {"Hög value-trap-risk", "Avstå tills vidare"}:
        vetoes.append("value-trap-/fundamentalrisken är för hög")
    else:
        vetoes.append("flerårsdata är otillräcklig")

    # 2) Fresh revisions / operating inflection. Neutral is allowed but not support.
    if infl_signal in {"Positiv inflektion", "Tidiga förbättringstecken"}:
        supports.append("färska estimat/kvartalstrender förbättras")
    elif infl_signal in {"Negativ förändring", "Tydlig försämring"}:
        vetoes.append("färska förändringssignaler försämras")
    else:
        neutral.append("ingen tydlig positiv färsk inflektion är verifierad")

    # 3) Mispricing: this must be more than 'cheap'.
    if mispricing in {"Tydlig möjlig felprissättning", "Möjlig felprissättning"}:
        supports.append("priset verkar kräva mindre än verifierad utveckling kan stödja")
    elif mispricing == "Marknaden kan vara mer rimlig än caset":
        vetoes.append("värderingen kräver mer av framtiden än verifierad utveckling stödjer")
    else:
        neutral.append("ingen tydlig felprissättning kan beläggas")

    # 4) Scenario risk/reward. A scenario never rescues a weak fundamental case.
    if scenario_status == "OK":
        if scenario_verdict == "Attraktiv asymmetri" and np.isfinite(asym) and asym >= 2.0:
            supports.append("Bear/Base/Bull visar attraktiv asymmetri")
        elif scenario_verdict == "Möjligen attraktiv asymmetri" and np.isfinite(asym) and asym >= 1.2:
            supports.append("scenarioanalysen visar möjlig attraktiv asymmetri")
        elif scenario_verdict == "Svag risk/reward":
            vetoes.append("scenarioanalysen visar svag risk/reward")
        else:
            neutral.append("scenarioanalysen ger ingen tydlig asymmetrisk fördel")
    else:
        neutral.append("scenarioasymmetri kan inte verifieras")

    # 5) Catalyst / Why Now. A catalyst is support only when there is positive,
    # independently observable evidence. A scheduled report is a control point, not
    # automatically a positive catalyst. Headline risk can veto promotion.
    if catalyst_signal == "Ny risk måste verifieras först":
        vetoes.append("ny extern riskhändelse måste verifieras innan caset kan lyftas")
    elif catalyst_support and catalyst_signal in {"Tydlig möjlig katalysator", "Möjlig katalysator"}:
        supports.append("en konkret möjlig omvärderingskatalysator kan beläggas")
    elif catalyst_signal == "Närliggande kontrollpunkt":
        neutral.append("nästa rapport är en kontrollpunkt men inte en positiv katalysator i sig")
    else:
        neutral.append("ingen konkret positiv katalysator är verifierad")

    if np.isfinite(trap) and trap >= 70:
        if "value-trap-/fundamentalrisken är för hög" not in vetoes:
            vetoes.append("Value Trap Risk är mycket hög")

    # Confidence is evidence coverage, never a probability of success.
    confidence_parts = [x for x in (deep_conf, infl_conf, scenario_conf, catalyst_conf) if np.isfinite(x) and x > 0]
    coverage_conf = float(np.mean(confidence_parts)) if confidence_parts else 0.0
    # Inflection coverage is often absent for non-US names. Do not zero a case merely
    # because analysts do not cover it; deep data remains the anchor.
    if np.isfinite(deep_conf):
        coverage_conf = 0.60 * deep_conf + 0.40 * coverage_conf
    coverage_conf = float(np.clip(coverage_conf, 0, 100))

    low_coverage = coverage_conf < 45
    if low_coverage:
        vetoes.append("för lite verifierbar data för ett toppcase")

    support_count = len(supports)
    veto_count = len(vetoes)
    hard_veto = deep_gate in {"Hög value-trap-risk", "Avstå tills vidare", "Otillräcklig data"} or (np.isfinite(trap) and trap >= 70) or low_coverage

    if hard_veto or veto_count >= 2 or (veto_count >= 1 and support_count <= 1):
        gate = "Ej toppcase"
    elif veto_count == 1:
        gate = "Bevaka – motbevis finns"
    elif support_count >= 5 and coverage_conf >= 65 and catalyst_support:
        gate = "Toppcase"
    elif support_count >= 4 and coverage_conf >= 58:
        gate = "Starkt case"
    elif support_count >= 3 and coverage_conf >= 52:
        gate = "Värd djupanalys"
    elif support_count >= 2 and coverage_conf >= 48:
        gate = "Bevaka"
    else:
        gate = "Bevaka"

    # A separate confidence label makes the meaning harder to confuse with odds.
    if coverage_conf >= 75:
        conf_label = "Hög evidenstäckning"
    elif coverage_conf >= 55:
        conf_label = "Medelgod evidenstäckning"
    else:
        conf_label = "Låg evidenstäckning"

    return {
        "Case Gate": gate,
        "Case Evidence Count": support_count,
        "Case Veto Count": veto_count,
        "Case Confidence": round(coverage_conf, 1),
        "Case Confidence Label": conf_label,
        "Case Supports": "; ".join(supports) if supports else "inga oberoende stöd verifierade",
        "Case Neutrals": "; ".join(neutral) if neutral else "—",
        "Case Vetoes": "; ".join(vetoes) if vetoes else "inga hårda motbevis i gate-modellen",
    }


def case_gate_rank_key(row: dict[str, Any] | pd.Series) -> tuple[float, float, float, float, float]:
    order = {
        "Toppcase": 6.0,
        "Starkt case": 5.0,
        "Värd djupanalys": 4.0,
        "Bevaka": 3.0,
        "Bevaka – motbevis finns": 2.0,
        "Ej toppcase": 1.0,
    }
    gate = order.get(str(row.get("Case Gate", "")), 0.0)
    evidence = _num(row.get("Case Evidence Count"))
    confidence = _num(row.get("Case Confidence"))
    asym = _num(row.get("Scenario Asymmetry"))
    invest = _num(row.get("INVEST Score"))
    return (
        gate,
        evidence if np.isfinite(evidence) else 0.0,
        confidence if np.isfinite(confidence) else 0.0,
        asym if np.isfinite(asym) else 0.0,
        invest if np.isfinite(invest) else 0.0,
    )
