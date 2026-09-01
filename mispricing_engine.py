from __future__ import annotations

from typing import Any
import math

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else np.nan
    except (TypeError, ValueError):
        return np.nan


def required_eps_cagr(
    forward_pe: float,
    exit_pe: float,
    annual_return_hurdle: float = 0.10,
    years: int = 5,
) -> float:
    """EPS CAGR required for a chosen annual return if P/E ends at ``exit_pe``.

    Price cancels algebraically: EPS_0 = P / forward_pe and
    target P = P * (1+r)^years. This is an expectation *hurdle*, not a forecast.
    """
    fp, ep, hurdle = _num(forward_pe), _num(exit_pe), _num(annual_return_hurdle)
    if years <= 0 or not (np.isfinite(fp) and np.isfinite(ep) and np.isfinite(hurdle)):
        return np.nan
    if fp <= 0 or ep <= 0 or hurdle <= -1:
        return np.nan
    required_multiple = (1.0 + hurdle) ** years * fp / ep
    if required_multiple <= 0:
        return np.nan
    return required_multiple ** (1.0 / years) - 1.0


def fcf_growth_hurdle(fcf_yield: float, annual_return_hurdle: float = 0.10) -> float:
    """Simple owner-earnings lens: approximate growth needed after current FCF yield.

    This deliberately stays a rough diagnostic and must not be presented as a DCF.
    """
    fy, hurdle = _num(fcf_yield), _num(annual_return_hurdle)
    if not (np.isfinite(fy) and np.isfinite(hurdle)) or fy <= 0:
        return np.nan
    return hurdle - fy


def _best_verified_growth(deep: dict[str, Any] | pd.Series, snapshot: dict[str, Any] | pd.Series) -> tuple[float, str]:
    """Choose a conservative observed growth proxy without averaging unrelated signals."""
    candidates = [
        ("FCF CAGR", _num(deep.get("FCF CAGR"))),
        ("Vinst CAGR", _num(deep.get("Vinst CAGR"))),
        ("Omsättning CAGR", _num(deep.get("Omsättning CAGR"))),
    ]
    # Prefer cash earnings, then accounting earnings, then revenue. Ignore extreme
    # values that are usually base-effect noise rather than a durable run-rate.
    for label, value in candidates:
        if np.isfinite(value) and -0.40 <= value <= 0.60:
            return value, label
    current = _num(snapshot.get("Vinsttillväxt"))
    if np.isfinite(current) and -0.40 <= current <= 0.60:
        return current, "senaste rapporterade vinsttillväxt"
    return np.nan, "—"


def build_mispricing_assessment(
    snapshot: dict[str, Any] | pd.Series,
    deep: dict[str, Any] | pd.Series,
    annual_return_hurdle: float = 0.10,
) -> dict[str, Any]:
    """Estimate whether current valuation looks demanding or undemanding.

    The engine does *not* claim to know the market's true expectations. Instead it
    calculates transparent expectation hurdles from available valuation data and
    compares them with verified operating trends. Missing inputs remain missing.
    """
    forward_pe = _num(snapshot.get("Forward P/E"))
    trailing_pe = _num(snapshot.get("P/E"))
    fcf_yield = _num(snapshot.get("FCF-yield"))
    trap = _num(deep.get("Value Trap Risk"))
    confidence = _num(deep.get("Deep Confidence"))
    inflection = _num(deep.get("Inflection Score"))

    growth, growth_source = _best_verified_growth(deep, snapshot)

    # Three explicit exit-multiple scenarios avoid pretending that one terminal
    # multiple is objectively correct. 20x is only the middle reference lens.
    pe_hurdles: dict[str, float] = {}
    if np.isfinite(forward_pe) and forward_pe > 0:
        for exit_pe in (15.0, 20.0, 25.0):
            pe_hurdles[f"Implied EPS CAGR @ exit P/E {int(exit_pe)}"] = required_eps_cagr(
                forward_pe, exit_pe, annual_return_hurdle, 5
            )
    base_required = pe_hurdles.get("Implied EPS CAGR @ exit P/E 20", np.nan)
    fcf_required = fcf_growth_hurdle(fcf_yield, annual_return_hurdle)

    evidence: list[str] = []
    cautions: list[str] = []
    lens_count = 0
    support_points = 0
    challenge_points = 0

    pe_gap = np.nan
    if np.isfinite(base_required) and np.isfinite(growth):
        lens_count += 1
        pe_gap = growth - base_required
        if pe_gap >= 0.06:
            support_points += 2
            evidence.append(
                f"verifierad {growth_source.lower()} ({growth:.1%}) ligger tydligt över den tillväxt som 10 % årlig avkastning skulle kräva vid exit P/E 20 ({base_required:.1%})"
            )
        elif pe_gap >= 0.02:
            support_points += 1
            evidence.append(
                f"verifierad {growth_source.lower()} ({growth:.1%}) ligger något över P/E-hurdlen ({base_required:.1%})"
            )
        elif pe_gap <= -0.06:
            challenge_points += 2
            cautions.append(
                f"nuvarande {growth_source.lower()} ({growth:.1%}) ligger tydligt under P/E-hurdlen ({base_required:.1%})"
            )
        elif pe_gap <= -0.02:
            challenge_points += 1
            cautions.append("värderingen kräver mer tillväxt än den verifierade flerårstrenden visar")

    fcf_gap = np.nan
    if np.isfinite(fcf_required) and np.isfinite(growth):
        lens_count += 1
        fcf_gap = growth - fcf_required
        if fcf_gap >= 0.06:
            support_points += 1
            evidence.append("FCF-yielden ger en relativt låg extra tillväxthurdle jämfört med verifierad tillväxt")
        elif fcf_gap <= -0.06:
            challenge_points += 1
            cautions.append("FCF-yield + verifierad tillväxt når inte den valda 10 %-hurdlen i den förenklade kassaflödeslinsen")

    # Valuation on its own never creates strong evidence. Fresh improvement can
    # strengthen an already supported mismatch, while deterioration can veto it.
    if np.isfinite(inflection):
        if inflection >= 68 and support_points > 0:
            support_points += 1
            evidence.append("färska förändringssignaler stödjer snarare än motsäger flerårstrenden")
        elif inflection <= 35:
            challenge_points += 2
            cautions.append("färska förändringssignaler försämras och kan göra historisk tillväxt irrelevant")

    if np.isfinite(trap) and trap >= 45:
        challenge_points += 2
        cautions.append("value-trap-risken är för hög för att tolka låg värdering som tydlig felprissättning")
    if np.isfinite(confidence) and confidence < 55:
        challenge_points += 1
        cautions.append("datatäckningen är för svag för en stark slutsats om felprissättning")

    if lens_count == 0:
        label = "Kan inte bedömas"
    elif challenge_points >= 3 or (challenge_points >= 2 and support_points == 0):
        label = "Marknaden kan vara mer rimlig än caset"
    elif support_points >= 3 and challenge_points == 0 and (not np.isfinite(trap) or trap < 35) and (not np.isfinite(confidence) or confidence >= 55):
        label = "Tydlig möjlig felprissättning"
    elif support_points >= 1 and challenge_points <= 1:
        label = "Möjlig felprissättning"
    else:
        label = "Ingen tydlig felprissättning"

    why_market_wrong = "Ingen tydlig skillnad mellan prisets krav och verifierad utveckling kan beläggas."
    if evidence:
        why_market_wrong = evidence[0].capitalize() + "."
    if label == "Marknaden kan vara mer rimlig än caset" and cautions:
        why_market_wrong = "Modellen hittar inget robust förväntningsgap: " + cautions[0] + "."

    return {
        **pe_hurdles,
        "FCF growth hurdle": fcf_required,
        "Verifierad tillväxtproxy": growth,
        "Tillväxtkälla": growth_source,
        "P/E expectation gap": pe_gap,
        "FCF expectation gap": fcf_gap,
        "Mispricing-lins antal": lens_count,
        "Mispricing stöd": support_points,
        "Mispricing motbevis": challenge_points,
        "Mispricing Signal": label,
        "Mispricing Evidence": "; ".join(evidence[:3]) if evidence else "ingen tydlig stödjande felprissättningssignal",
        "Mispricing Cautions": "; ".join(cautions[:3]) if cautions else "inga extra varningar från förväntningshurdlen",
        "Varför marknaden kan ha fel 2.0": why_market_wrong,
        "Avkastningshurdle": annual_return_hurdle,
    }


def apply_mispricing_gate(assessment: dict[str, Any]) -> dict[str, Any]:
    """Let poor expectation economics downgrade, never blindly upgrade, deep gates."""
    out = dict(assessment)
    signal = str(out.get("Mispricing Signal", "Kan inte bedömas"))
    gate = str(out.get("Djupkontroll", "Otillräcklig data"))

    if signal == "Marknaden kan vara mer rimlig än caset" and gate in {"Klarar djupkontroll", "Neutral djupkontroll"}:
        out["Djupkontroll"] = "Kräver extra kontroll"
        out["Mispricing Gate Note"] = "Värderingen kräver mer av framtiden än tillgänglig verifierad utveckling stödjer."
    elif signal == "Tydlig möjlig felprissättning" and gate == "Neutral djupkontroll":
        # Do not promote through the hard gate; keep the evidence visible for ranking.
        out["Mispricing Gate Note"] = "Förväntningsgapet ser attraktivt ut, men övriga djupkrav är ännu inte tillräckliga för uppgradering."
    return out


def mispricing_rank_value(row: dict[str, Any] | pd.Series) -> float:
    order = {
        "Tydlig möjlig felprissättning": 5.0,
        "Möjlig felprissättning": 4.0,
        "Ingen tydlig felprissättning": 3.0,
        "Kan inte bedömas": 2.0,
        "Marknaden kan vara mer rimlig än caset": 1.0,
    }
    return order.get(str(row.get("Mispricing Signal", "")), 2.0)
