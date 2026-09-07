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


def build_expectation_change(case: dict[str, Any] | pd.Series) -> dict[str, Any]:
    """Describe whether market expectations appear to be changing.

    This is deliberately *not* another ranking score. It separates analyst-opinion
    evidence from reported operating evidence, requires breadth before calling a
    change strong, and exposes conflicts rather than averaging them away.
    """
    eps = _num(case.get("EPS-estimat förändring"))
    balance = _num(case.get("EPS-revisionsbalans"))
    est_weight = _num(case.get("Estimat tillförlitlighetsvikt"))
    analysts = _num(case.get("Analytiker antal"))
    surprise = _num(case.get("Senaste EPS-överraskning"))

    rev_acc = _num(case.get("Omsättning acceleration"))
    margin_yoy = _num(case.get("Marginal YoY förändring"))
    margin_qoq = _num(case.get("Marginal QoQ förändring"))
    earnings_yoy = _num(case.get("Vinst YoY senaste kvartal"))
    fcf_yoy = _num(case.get("FCF YoY senaste kvartal"))

    if not np.isfinite(est_weight):
        est_weight = 0.0
    est_weight = float(np.clip(est_weight, 0.0, 1.0))

    analyst_signals: list[int] = []
    analyst_bits: list[str] = []
    if np.isfinite(eps):
        direction = 1 if eps >= .02 else (-1 if eps <= -.02 else 0)
        analyst_signals.append(direction)
        if direction > 0:
            analyst_bits.append(f"vinstprognoserna har höjts cirka {eps:.1%}")
        elif direction < 0:
            analyst_bits.append(f"vinstprognoserna har sänkts cirka {abs(eps):.1%}")
    if np.isfinite(balance):
        direction = 1 if balance >= .35 else (-1 if balance <= -.35 else 0)
        analyst_signals.append(direction)
        if direction > 0:
            analyst_bits.append("fler analytiker höjer än sänker")
        elif direction < 0:
            analyst_bits.append("fler analytiker sänker än höjer")

    analyst_net = sum(analyst_signals)
    analyst_count = len(analyst_signals)
    analyst_usable = est_weight >= .4 and analyst_count > 0
    if not analyst_usable:
        analyst_label = "För lite verifierbar analytikerdata"
        analyst_direction = 0
    elif analyst_net >= 2:
        analyst_label = "Tydligt höjda förväntningar"
        analyst_direction = 1
    elif analyst_net >= 1:
        analyst_label = "Förväntningarna höjs"
        analyst_direction = 1
    elif analyst_net <= -2:
        analyst_label = "Tydligt sänkta förväntningar"
        analyst_direction = -1
    elif analyst_net <= -1:
        analyst_label = "Förväntningarna sänks"
        analyst_direction = -1
    else:
        analyst_label = "Analytikerförväntningarna är i stort sett oförändrade"
        analyst_direction = 0

    reported_signals: list[int] = []
    reported_bits: list[str] = []

    def add(value: float, pos: float, neg: float, pos_text: str, neg_text: str) -> None:
        if not np.isfinite(value):
            return
        direction = 1 if value >= pos else (-1 if value <= neg else 0)
        reported_signals.append(direction)
        if direction > 0:
            reported_bits.append(pos_text)
        elif direction < 0:
            reported_bits.append(neg_text)

    add(rev_acc, .03, -.05, "försäljningstillväxten accelererar", "försäljningstillväxten bromsar")
    margin_measure = margin_yoy if np.isfinite(margin_yoy) else margin_qoq
    add(margin_measure, .015, -.02, "marginalen förbättras", "marginalen försämras")
    add(earnings_yoy, .10, -.20, "vinsten förbättras", "vinsten försämras")
    add(fcf_yoy, .15, -.25, "kassaflödet förbättras", "kassaflödet försämras")
    if np.isfinite(surprise):
        add(surprise, .05, -.05, "senaste rapporten slog vinstförväntningarna", "senaste rapporten missade vinstförväntningarna")

    reported_pos = sum(x > 0 for x in reported_signals)
    reported_neg = sum(x < 0 for x in reported_signals)
    reported_count = len(reported_signals)
    reported_net = reported_pos - reported_neg
    if reported_count < 2:
        reported_label = "För lite färsk rapportdata"
        reported_direction = 0
    elif reported_net >= 2:
        reported_label = "Bolagets siffror förbättras brett"
        reported_direction = 1
    elif reported_net >= 1:
        reported_label = "Bolagets siffror förbättras"
        reported_direction = 1
    elif reported_net <= -2:
        reported_label = "Bolagets siffror försämras brett"
        reported_direction = -1
    elif reported_net <= -1:
        reported_label = "Bolagets siffror försämras"
        reported_direction = -1
    else:
        reported_label = "Bolagets färska siffror är blandade"
        reported_direction = 0

    if analyst_direction > 0 and reported_direction > 0:
        status = "Förväntningarna förbättras med stöd i siffrorna"
        direction = "positiv"
        strength = "stark"
        why = "Både analytikernas prognoser och bolagets färska siffror pekar uppåt."
    elif analyst_direction < 0 and reported_direction < 0:
        status = "Förväntningarna försämras med stöd i siffrorna"
        direction = "negativ"
        strength = "stark"
        why = "Både analytikernas prognoser och bolagets färska siffror pekar nedåt."
    elif analyst_direction > 0 and reported_direction < 0:
        status = "Höjda prognoser men svagare siffror"
        direction = "konflikt"
        strength = "varning"
        why = "Analytikerna har blivit mer positiva, men bolagets senaste siffror stödjer ännu inte förbättringen."
    elif analyst_direction < 0 and reported_direction > 0:
        status = "Siffrorna förbättras före prognoserna"
        direction = "positiv_tidigt"
        strength = "tidig"
        why = "Bolagets siffror förbättras, men analytikernas prognoser har ännu inte vänt upp."
    elif analyst_direction > 0:
        status = "Förväntningarna höjs – begränsat stöd i rapportdata"
        direction = "positiv"
        strength = "måttlig"
        why = "Analytikernas prognoser förbättras, men färsk rapportdata ger ännu inte ett brett stöd."
    elif analyst_direction < 0:
        status = "Förväntningarna sänks"
        direction = "negativ"
        strength = "måttlig"
        why = "Analytikernas prognoser har försämrats."
    elif reported_direction > 0:
        status = "Bolagets siffror förbättras – prognoser saknas eller är neutrala"
        direction = "positiv_tidigt"
        strength = "tidig"
        why = "Färska bolagssiffror förbättras, men analytikerdata är för tunn eller har ännu inte vänt upp."
    elif reported_direction < 0:
        status = "Bolagets siffror försämras"
        direction = "negativ"
        strength = "måttlig"
        why = "Färska bolagssiffror försämras även om analytikerdata inte ger en tydlig signal."
    else:
        status = "Ingen tydlig förändring i förväntningarna"
        direction = "neutral"
        strength = "svag"
        why = "Borsify kan inte verifiera en tydlig förändring i marknadens förväntningar."

    evidence_count = analyst_count + reported_count
    coverage = "Bra underlag" if analyst_usable and reported_count >= 3 else ("Användbart underlag" if evidence_count >= 3 else "Begränsat underlag")

    return {
        "Förväntningsförändring": status,
        "Förväntningsriktning": direction,
        "Förväntningsstyrka": strength,
        "Förväntningsunderlag": coverage,
        "Förväntningsanalytiker": analyst_label,
        "Förväntningsrapporterat": reported_label,
        "Förväntningsförklaring": why,
        "Förväntningsanalytiker stöd": "; ".join(analyst_bits[:2]) if analyst_bits else "inget tydligt verifierat",
        "Förväntningsrapporterat stöd": "; ".join(reported_bits[:3]) if reported_bits else "inget tydligt verifierat",
        "Förväntning analyst direction": analyst_direction,
        "Förväntning reported direction": reported_direction,
        "Förväntning evidence count": evidence_count,
        "Förväntning analytiker antal": int(analysts) if np.isfinite(analysts) else np.nan,
    }
