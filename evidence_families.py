from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


FAMILY_ORDER = [
    "Pris/värdering",
    "Bolagskvalitet",
    "Förändrade förväntningar",
    "Kursbekräftelse",
    "Händelse/katalysator",
    "Risk/motbevis",
]


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _family(name: str, state: str, short: str, detail: str, counts_as_support: bool = True) -> dict[str, Any]:
    return {
        "name": name,
        "state": state,
        "short": short,
        "detail": detail,
        "counts_as_support": bool(counts_as_support and state == "STÖD"),
    }


def build_evidence_families(case: dict[str, Any] | pd.Series) -> dict[str, Any]:
    """Group correlated inputs into a small set of independent evidence families.

    The purpose is not to make another score. Multiple related metrics inside one
    family can strengthen the explanation, but they still count as only one
    independent support. Risk is a guardrail family and never adds positive
    support merely because no problem was found.
    """
    families: list[dict[str, Any]] = []

    # 1. Price / valuation: use the mispricing conclusion as the family-level view.
    mispricing = str(case.get("Mispricing Signal", "Kan inte bedömas") or "Kan inte bedömas")
    if mispricing in {"Tydlig möjlig felprissättning", "Möjlig felprissättning"}:
        families.append(_family("Pris/värdering", "STÖD", "Priset kan vara för lågt", mispricing))
    elif mispricing == "Marknaden kan vara mer rimlig än caset":
        families.append(_family("Pris/värdering", "VARNING", "Priset kräver mycket", mispricing))
    elif mispricing in {"Kan inte bedömas", "Otillräcklig data", ""}:
        families.append(_family("Pris/värdering", "SAKNAS", "För lite underlag", mispricing or "För lite underlag"))
    else:
        families.append(_family("Pris/värdering", "NEUTRAL", "Ingen tydlig felprissättning", mispricing))

    # 2. Business quality: several accounting/operating checks are one family,
    # rather than several independent votes for the same underlying quality idea.
    deep = str(case.get("Djupkontroll", "Otillräcklig data") or "Otillräcklig data")
    eq = str(case.get("Vinstkvalitet status", "") or "")
    cap = str(case.get("Kapitaldisciplin status", "") or "")
    quality_warnings = []
    if deep in {"Hög value-trap-risk", "Avstå tills vidare", "Kräver extra kontroll"}:
        quality_warnings.append(deep)
    if eq in {"SVAG VINSTKVALITET", "KRÄVER KONTROLL"}:
        quality_warnings.append(eq)
    if cap in {"KAPITALBINDNING ÖKAR", "KRÄVER KONTROLL"}:
        quality_warnings.append(cap)
    if quality_warnings:
        families.append(_family("Bolagskvalitet", "VARNING", "Kvaliteten behöver kontrolleras", "; ".join(quality_warnings)))
    elif deep == "Klarar djupkontroll":
        detail_bits = [deep]
        if eq:
            detail_bits.append(eq)
        if cap:
            detail_bits.append(cap)
        families.append(_family("Bolagskvalitet", "STÖD", "Bolaget ser robust ut", " · ".join(detail_bits)))
    elif deep in {"Neutral djupkontroll"}:
        families.append(_family("Bolagskvalitet", "NEUTRAL", "Kvaliteten är okej men inte tydlig", deep))
    else:
        families.append(_family("Bolagskvalitet", "SAKNAS", "För lite flerårsdata", deep))

    # 3. Expectations: analyst revisions and reported inflection are deliberately
    # collapsed into one family because they often describe the same change.
    direction = str(case.get("Förväntningsriktning", "neutral") or "neutral")
    expectation = str(case.get("Förväntningsförändring", "") or "")
    inflection = str(case.get("Inflection Signal", "") or "")
    if direction in {"positiv", "positiv_tidigt"} or inflection in {"Positiv inflektion", "Tidiga förbättringstecken"}:
        families.append(_family("Förändrade förväntningar", "STÖD", "Förväntningarna förbättras", expectation or inflection))
    elif direction == "negativ" or inflection in {"Negativ förändring", "Tydlig försämring"}:
        families.append(_family("Förändrade förväntningar", "VARNING", "Förväntningarna försämras", expectation or inflection))
    elif direction == "konflikt":
        families.append(_family("Förändrade förväntningar", "NEUTRAL", "Signalerna pekar åt olika håll", expectation or "Konflikt mellan prognoser och rapportdata"))
    elif expectation or inflection:
        families.append(_family("Förändrade förväntningar", "NEUTRAL", "Ingen tydlig förändring", expectation or inflection))
    else:
        families.append(_family("Förändrade förväntningar", "SAKNAS", "För lite färsk data", "För lite underlag"))

    # 4. Price confirmation. The benchmark-relative score is one family; market,
    # sector and peer comparisons do not each get their own vote.
    rel = _num(case.get("Relativ styrka"))
    m1 = _num(case.get("1 mån")); m3 = _num(case.get("3 mån"))
    rel_inputs = [
        _num(case.get("Relativ marknad 3 mån")),
        _num(case.get("Relativ sektor 3 mån")),
        _num(case.get("Relativ peer 3 mån")),
    ]
    has_relative_basis = any(np.isfinite(x) for x in rel_inputs)
    if np.isfinite(rel) and has_relative_basis and rel >= 58:
        families.append(_family("Kursbekräftelse", "STÖD", "Kursen bekräftar caset", str(case.get("Relativ styrka förklaring", "Relativ styrka är positiv"))))
    elif np.isfinite(rel) and has_relative_basis and rel < 42:
        families.append(_family("Kursbekräftelse", "VARNING", "Kursen bekräftar inte caset", str(case.get("Relativ styrka förklaring", "Relativ styrka är svag"))))
    elif has_relative_basis or np.isfinite(m1) or np.isfinite(m3):
        families.append(_family("Kursbekräftelse", "NEUTRAL", "Kursen ger ingen tydlig bekräftelse", str(case.get("Relativ styrka förklaring", "Ingen tydlig relativ styrka"))))
    else:
        families.append(_family("Kursbekräftelse", "SAKNAS", "För lite kursunderlag", "För lite jämförelsedata"))

    # 5. Event / catalyst: PEAD and catalyst evidence are one family. A report and
    # a catalyst that describe the same event must not count twice.
    catalyst_signal = str(case.get("Catalyst Signal", "") or "")
    catalyst_support = bool(case.get("Catalyst Independent Support", case.get("Catalyst Support", False)))
    post_support = bool(case.get("Post-report stöd", False))
    post_warning = bool(case.get("Post-report varning", False))
    post_status = str(case.get("Post-report status", "") or "")
    if catalyst_signal == "Ny risk måste verifieras först" or post_warning:
        detail = catalyst_signal if catalyst_signal == "Ny risk måste verifieras först" else post_status
        families.append(_family("Händelse/katalysator", "VARNING", "Händelsen ger ett motargument", detail))
    elif catalyst_support or post_support:
        detail = str(case.get("Primary Catalyst", "") or post_status or catalyst_signal)
        families.append(_family("Händelse/katalysator", "STÖD", "En konkret händelse stödjer caset", detail))
    elif catalyst_signal or post_status:
        families.append(_family("Händelse/katalysator", "NEUTRAL", "Ingen tydlig positiv katalysator", catalyst_signal or post_status))
    else:
        families.append(_family("Händelse/katalysator", "SAKNAS", "Ingen verifierad händelse", "För lite underlag"))

    # 6. Risk / counterevidence. Clean risk is not positive alpha evidence, so this
    # family never increments the support count. It is a separate guardrail.
    trap = _num(case.get("Value Trap Risk"))
    scenario_verdict = str(case.get("Scenario Verdict", "") or "")
    fundamental_status = str(case.get("Fundamental Data status", "") or "")
    redundancy_status = str(case.get("Redundans status", "") or "")
    risk_flags = []
    if np.isfinite(trap) and trap >= 70:
        risk_flags.append("hög risk för värdefälla")
    if scenario_verdict == "Svag risk/reward":
        risk_flags.append("svag risk/reward")
    if fundamental_status == "STOPP":
        risk_flags.append("fundamental data håller inte")
    if redundancy_status == "STOPP – MOTSÄGELSE":
        risk_flags.append("datakällor motsäger varandra")
    idio_status = str(case.get("Idiosynkratisk volatilitet status", "") or "")
    if idio_status == "MYCKET HÖG BOLAGSSPECIFIK RISK":
        risk_flags.append("mycket stora bolagsspecifika svängningar")
    elif idio_status == "HÖG BOLAGSSPECIFIK RISK":
        risk_flags.append("stora bolagsspecifika svängningar")
    if risk_flags:
        families.append(_family("Risk/motbevis", "VARNING", "Tydligt motbevis finns", "; ".join(risk_flags), counts_as_support=False))
    elif scenario_verdict in {"Attraktiv asymmetri", "Möjligen attraktiv asymmetri"} or (np.isfinite(trap) and trap < 50):
        families.append(_family("Risk/motbevis", "NEUTRAL", "Ingen stor riskflagga i modellen", scenario_verdict or "Value-trap-risken är inte hög", counts_as_support=False))
    else:
        families.append(_family("Risk/motbevis", "SAKNAS", "Riskbilden är inte fullt verifierad", scenario_verdict or "För lite underlag", counts_as_support=False))

    support_count = sum(1 for f in families if f["counts_as_support"])
    warning_count = sum(1 for f in families if f["state"] == "VARNING")
    covered_count = sum(1 for f in families if f["state"] != "SAKNAS")
    support_names = [f["name"] for f in families if f["counts_as_support"]]
    warning_names = [f["name"] for f in families if f["state"] == "VARNING"]

    # This is a diversity label, not a probability and not a weighted score.
    if support_count >= 4 and warning_count == 0:
        label = "Brett stöd"
    elif support_count >= 3 and warning_count <= 1:
        label = "Flera olika stöd"
    elif support_count >= 2:
        label = "Viss bredd"
    else:
        label = "Smalt stöd"

    out: dict[str, Any] = {
        "Evidence Families schema": 1,
        "Evidence Family Support Count": support_count,
        "Evidence Family Warning Count": warning_count,
        "Evidence Family Covered Count": covered_count,
        "Evidence Family Label": label,
        "Evidence Family Supports": "; ".join(support_names) if support_names else "inga positiva familjer",
        "Evidence Family Warnings": "; ".join(warning_names) if warning_names else "inga familjevarningar",
    }
    for f in families:
        prefix = f"Evidence Family {f['name']}"
        out[prefix] = f["state"]
        out[prefix + " text"] = f["short"]
        out[prefix + " detalj"] = f["detail"]
    return out


def evidence_family_rows(case: dict[str, Any] | pd.Series) -> list[dict[str, str]]:
    """Small UI helper with stable order and beginner-friendly labels."""
    rows = []
    symbols = {"STÖD": "✓", "NEUTRAL": "•", "VARNING": "!", "SAKNAS": "?"}
    for name in FAMILY_ORDER:
        state = str(case.get(f"Evidence Family {name}", "SAKNAS") or "SAKNAS")
        rows.append({
            "Familj": name,
            "Läge": f"{symbols.get(state, '?')} {state.title()}",
            "Kort förklaring": str(case.get(f"Evidence Family {name} text", "För lite underlag") or "För lite underlag"),
        })
    return rows
