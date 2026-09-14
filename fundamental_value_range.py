from __future__ import annotations

import math
from typing import Any

import numpy as np


def _num(value: Any, default: float = np.nan) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError):
        return default


def _text(row: dict, *keys: str) -> str:
    return " ".join(str(row.get(key) or "") for key in keys).lower()


def _pct(value: float) -> str:
    return f"{value:+.0%}"


def _price(value: float) -> float:
    # The output is a deliberately coarse interval, not a target with false precision.
    if value >= 1000:
        return round(value / 10) * 10
    if value >= 100:
        return round(value)
    if value >= 10:
        return round(value, 1)
    return round(value, 2)


def _blocked_business_model(row: dict) -> str:
    descriptor = _text(row, "Sektor", "Bransch", "Industry", "Business profile")
    groups = (
        (("bank", "financial service", "insurance", "försäkring"), "bank/finans/försäkring"),
        (("real estate", "reit", "fastighet"), "fastighet/REIT"),
    )
    for terms, label in groups:
        if any(term in descriptor for term in terms):
            return label
    return ""


def build_fundamental_value_range(row: dict, scenario: dict | None) -> dict:
    """Quality-gated, advisory range around the existing transparent scenarios.

    This layer cannot affect ranking. It refuses business models needing a dedicated
    valuation model and never treats absent cash-flow or dilution data as favourable.
    """
    scenario = scenario or {}
    blocked = _blocked_business_model(row)
    if blocked:
        return {
            "Fundamental Value Range status": "UNSUPPORTED_MODEL",
            "Fundamental Value Range": "⚪ Kräver sektorspecifik värdering",
            "Fundamental Value Range confidence": 0,
            "Fundamental Value Range reason": (
                f"Generisk EPS/P-E-värdering används inte för {blocked}. "
                "Borsify behöver en separat sektormodell innan ett intervall kan visas."
            ),
            "Fundamental Value Range ranking effect": "NONE",
        }

    if scenario.get("status") != "OK":
        return {
            "Fundamental Value Range status": "INSUFFICIENT_DATA",
            "Fundamental Value Range": "❔ Värdeintervall kan inte beräknas",
            "Fundamental Value Range confidence": 0,
            "Fundamental Value Range reason": str(
                scenario.get("reason") or "Positiv EPS, pris och verifierbar tillväxthistorik saknas."
            ),
            "Fundamental Value Range ranking effect": "NONE",
        }

    scenario_confidence = int(_num(scenario.get("confidence"), 0))
    if scenario_confidence < 50:
        return {
            "Fundamental Value Range status": "LOW_CONFIDENCE",
            "Fundamental Value Range": "❔ För svagt underlag för värdeintervall",
            "Fundamental Value Range confidence": scenario_confidence,
            "Fundamental Value Range reason": "Scenarioevidensen är för tunn för ett användbart intervall.",
            "Fundamental Value Range ranking effect": "NONE",
        }

    fcf_yield = _num(row.get("FCF-yield") if row.get("FCF-yield") is not None else row.get("FCF yield"))
    positive_fcf_share = _num(row.get("Positivt FCF andel"))
    latest_fcf = _num(row.get("Senaste FCF"))
    fcf_observed = any(math.isfinite(value) for value in (fcf_yield, positive_fcf_share, latest_fcf))
    fcf_conflict = (
        (math.isfinite(fcf_yield) and fcf_yield <= 0)
        or (math.isfinite(positive_fcf_share) and positive_fcf_share < 0.5)
        or (math.isfinite(latest_fcf) and latest_fcf <= 0)
    )
    if not fcf_observed or fcf_conflict:
        reason = (
            "Kassaflödesdata saknas; Borsify accepterar inte vinstscenariot som värdebevis."
            if not fcf_observed
            else "Vinstscenariot stöds inte av tillräckligt stabilt positivt fritt kassaflöde."
        )
        return {
            "Fundamental Value Range status": "FCF_NOT_CONFIRMED",
            "Fundamental Value Range": "🟡 Vinstscenario utan kassaflödesbekräftelse",
            "Fundamental Value Range confidence": max(0, scenario_confidence - 20),
            "Fundamental Value Range reason": reason,
            "Fundamental Value Range ranking effect": "NONE",
        }

    bear = scenario.get("bear") or {}
    base = scenario.get("base") or {}
    bull = scenario.get("bull") or {}
    anchors = [_num(part.get("future_price")) for part in (bear, base, bull)]
    if not all(math.isfinite(value) and value > 0 for value in anchors):
        return {
            "Fundamental Value Range status": "INSUFFICIENT_DATA",
            "Fundamental Value Range": "❔ Värdeintervall kan inte beräknas",
            "Fundamental Value Range confidence": 0,
            "Fundamental Value Range reason": "Scenarioankarna är ofullständiga.",
            "Fundamental Value Range ranking effect": "NONE",
        }

    bear_price, base_price, bull_price = sorted(anchors)
    lower_mid = (bear_price + base_price) / 2
    upper_mid = (base_price + bull_price) / 2
    bear_band = (_price(bear_price * 0.90), _price(lower_mid))
    base_band = (_price(lower_mid), _price(upper_mid))
    bull_band = (_price(upper_mid), _price(bull_price * 1.10))

    warnings = ["Historisk utspädning saknas och har inte antagits vara noll."]
    confidence = scenario_confidence
    debt_to_equity = _num(row.get("Skuld/eget kapital"))
    if math.isfinite(debt_to_equity) and debt_to_equity > 200:
        warnings.append("Hög skuld/eget kapital gör intervallet mindre robust.")
        confidence -= 10
    analysis_confidence = _num(row.get("Analysis Confidence Score"))
    if math.isfinite(analysis_confidence) and analysis_confidence < 50:
        warnings.append("Låg Analysis Confidence blockerar stark tillit till intervallet.")
        confidence = min(confidence, 45)

    price = _num(scenario.get("current_price"))
    base_return_band = (base_band[0] / price - 1, base_band[1] / price - 1)
    horizon = int(_num(scenario.get("horizon_years"), 5))
    currency = str(row.get("Valuta") or "").strip()
    unit = f" {currency}" if currency else ""
    label = "🟢 Fundamental värderingsrange" if confidence >= 65 else "🟡 Osäker fundamental värderingsrange"
    return {
        "Fundamental Value Range status": "SUPPORTED",
        "Fundamental Value Range": label,
        "Fundamental Value Range confidence": max(0, min(90, confidence)),
        "Fundamental Value Range horizon years": horizon,
        "Fundamental Value Range bear low": bear_band[0],
        "Fundamental Value Range bear high": bear_band[1],
        "Fundamental Value Range base low": base_band[0],
        "Fundamental Value Range base high": base_band[1],
        "Fundamental Value Range bull low": bull_band[0],
        "Fundamental Value Range bull high": bull_band[1],
        "Fundamental Value Range base return low": base_return_band[0],
        "Fundamental Value Range base return high": base_return_band[1],
        "Fundamental Value Range summary": (
            f"Base {_price(base_band[0])}–{_price(base_band[1])}{unit} "
            f"({_pct(base_return_band[0])} till {_pct(base_return_band[1])}) över {horizon} år."
        ),
        "Fundamental Value Range assumptions": (
            "Intervallen omger Bear/Base/Bull-ankare från EPS-tillväxt och framtida P/E; "
            "de är policyantaganden, inte sannolikhetsviktade riktkurser."
        ),
        "Fundamental Value Range warnings": " | ".join(warnings),
        "Fundamental Value Range reason": "Positiv EPS och kassaflödesstöd finns, men intervallet är antagandekänsligt.",
        "Fundamental Value Range ranking effect": "NONE",
    }
