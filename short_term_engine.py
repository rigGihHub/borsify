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


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _linear(x: float, low: float, high: float) -> float:
    if not math.isfinite(x):
        return 50.0
    if high <= low:
        return 50.0
    return _clip((x - low) / (high - low) * 100.0)


def _trend_score(price: float, sma50: float, dist200: float) -> float:
    above50 = math.isfinite(price) and math.isfinite(sma50) and price >= sma50
    if not math.isfinite(dist200):
        return 45.0
    if dist200 >= 0.0 and dist200 <= 0.18:
        return 88.0 if above50 else 72.0
    if dist200 > 0.18:
        return 72.0 if above50 else 58.0
    if dist200 >= -0.05:
        return 55.0 if above50 else 42.0
    if dist200 >= -0.10:
        return 30.0
    return 10.0


def _momentum_score(m1: float, m3: float, m6: float) -> float:
    parts = []
    if math.isfinite(m1):
        # Positive is good, but extremely vertical one-month moves are not rewarded forever.
        parts.append(100 - abs(_clip((m1 - 0.08) / 0.20 * 100) - 50) if m1 > 0.18 else _linear(m1, -0.10, 0.14))
    if math.isfinite(m3):
        parts.append(_linear(m3, -0.15, 0.30))
    if math.isfinite(m6):
        parts.append(_linear(m6, -0.20, 0.50))
    return float(np.mean(parts)) if parts else 45.0


def _relative_strength_score(row: dict[str, Any] | pd.Series, benchmark: dict[str, Any] | None) -> tuple[float, str]:
    benchmark = benchmark or {}
    diffs = []
    labels = []
    for stock_key, bench_key, label in (("1 mån", "month", "1m"), ("3 mån", "3m", "3m"), ("6 mån", "6m", "6m")):
        s = _num(row.get(stock_key))
        b = _num(benchmark.get(bench_key))
        if math.isfinite(s) and math.isfinite(b):
            diff = s - b
            diffs.append(diff)
            labels.append(f"{label} {diff:+.1%}")
    if not diffs:
        return 50.0, "benchmarkdata saknas"
    # 0% excess ≈ neutral, +15% strong, -15% weak.
    score = float(np.mean([_linear(x, -0.15, 0.15) for x in diffs]))
    return score, ", ".join(labels)


def assess_short_term_case(
    row: dict[str, Any] | pd.Series,
    benchmark: dict[str, Any] | None = None,
    inflection: dict[str, Any] | None = None,
    catalyst: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """1–6 month screening model with hard anti-falling-knife gates.

    The model rewards confirmation (trend, relative strength, revisions, participation)
    rather than the size of a prior fall. A large drawdown is never a positive input.
    """
    inflection = inflection or {}
    catalyst = catalyst or {}

    price = _num(row.get("Pris"))
    sma50 = _num(row.get("SMA50"))
    dist200 = _num(row.get("Avstånd SMA200"))
    m1 = _num(row.get("1 mån"))
    m3 = _num(row.get("3 mån"))
    m6 = _num(row.get("6 mån"))
    daily = _num(row.get("Dagsförändring"))
    rsi = _num(row.get("RSI14"))
    vol = _num(row.get("Volymkvot"))
    risk = _num(row.get("Risk"))
    liquidity = _num(row.get("Omsättning MSEK/dag"))
    flags = str(row.get("Riskflaggor", ""))

    trend = _trend_score(price, sma50, dist200)
    momentum = _momentum_score(m1, m3, m6)
    relative, relative_text = _relative_strength_score(row, benchmark)
    participation = _linear(vol, 0.65, 1.65) if math.isfinite(vol) else 45.0

    inf_score = _num(inflection.get("Inflection Score") or row.get("Inflection Score"))
    inf_signal = str(inflection.get("Inflection Signal") or row.get("Inflection Signal") or "")
    revisions = 50.0 if not math.isfinite(inf_score) else _clip(inf_score)
    if inf_signal in {"Negativ förändring", "Tydlig försämring"}:
        revisions = min(revisions, 25.0)

    cat_signal = str(catalyst.get("Catalyst Signal") or row.get("Catalyst Signal") or "")
    cat_support = bool(catalyst.get("Catalyst Support", row.get("Catalyst Support", False)))
    if cat_signal == "Tydlig möjlig katalysator":
        catalyst_score = 85.0
    elif cat_signal == "Möjlig katalysator":
        catalyst_score = 70.0
    elif cat_signal == "Närliggande kontrollpunkt":
        catalyst_score = 55.0
    elif cat_signal == "Ny risk måste verifieras först":
        catalyst_score = 10.0
    else:
        catalyst_score = 45.0

    # Weights intentionally emphasize market confirmation for a 1–6m horizon.
    score = (
        0.27 * relative
        + 0.23 * trend
        + 0.17 * momentum
        + 0.10 * participation
        + 0.13 * revisions
        + 0.10 * catalyst_score
    )

    vetoes = []
    cautions = []

    severe_terms = ("negativ ROE", "negativ marginal", "hög skuldsättning", "fallande lång trend")
    if any(term in flags for term in severe_terms):
        cautions.append("fundamental/riskflagga finns")

    # Falling-knife protection: drawdown itself never helps.
    if math.isfinite(dist200) and dist200 < -0.10 and math.isfinite(m3) and m3 < -0.08:
        vetoes.append("kursen ligger tydligt under lång trend och tremånadersmomentum är negativt")
    if math.isfinite(m1) and m1 <= -0.20 and not (cat_support and inf_signal in {"Positiv inflektion", "Tidiga förbättringstecken"}):
        vetoes.append("mycket svagt 1-månadersmomentum saknar verifierad positiv motkraft")
    if inf_signal in {"Tydlig försämring"}:
        vetoes.append("färska vinst-/estimatsignaler försämras tydligt")
    if cat_signal == "Ny risk måste verifieras först":
        vetoes.append("ny extern riskhändelse måste verifieras först")
    if math.isfinite(relative) and relative < 25 and math.isfinite(dist200) and dist200 < 0:
        vetoes.append("aktien underpresterar marknaden samtidigt som lång trend är svag")
    if math.isfinite(liquidity) and liquidity < 2:
        cautions.append("mycket låg daglig omsättning kan göra signalen svår att handla")

    # A sharp daily fall is a risk/event clue, never a positive factor by itself.
    if math.isfinite(daily) and daily <= -0.08:
        cautions.append("stort dagsfall – orsaken måste förstås innan köp")
    if math.isfinite(rsi) and rsi < 28:
        cautions.append("kraftigt översåld; invänta bekräftelse hellre än att fånga fallande kniv")
    if math.isfinite(rsi) and rsi > 78:
        cautions.append("mycket hög RSI; kortsiktig rekylrisk")

    confirmation_count = sum([
        relative >= 60,
        trend >= 65,
        momentum >= 60,
        revisions >= 60,
        catalyst_score >= 70,
        participation >= 55,
    ])

    if vetoes:
        gate = "Ej kortsiktigt toppcase"
        score = min(score, 54.0)
    elif score >= 76 and confirmation_count >= 4 and (revisions >= 60 or catalyst_score >= 70):
        gate = "Kortsiktigt toppcase"
    elif score >= 66 and confirmation_count >= 3:
        gate = "Starkt kortsiktigt case"
    elif score >= 58:
        gate = "Bevaka kortsiktigt"
    else:
        gate = "Svag kortsiktig signal"

    data_parts = [
        math.isfinite(m1), math.isfinite(m3), math.isfinite(m6),
        math.isfinite(dist200), math.isfinite(vol), math.isfinite(inf_score),
        bool(cat_signal),
    ]
    confidence = int(_clip(30 + 8 * sum(data_parts) + (6 if benchmark else 0) - 8 * len(vetoes), 20, 92))

    positives = []
    if relative >= 65:
        positives.append(f"slår jämförelsemarknaden ({relative_text})")
    if trend >= 70:
        positives.append("positiv teknisk trend")
    if revisions >= 65:
        positives.append("förbättrade vinst-/estimatsignaler")
    if catalyst_score >= 70:
        positives.append(str(catalyst.get("Primary Catalyst") or row.get("Primary Catalyst") or "konkret katalysator"))
    if participation >= 65:
        positives.append("ovanligt stark handelsaktivitet")
    why_now = "; ".join(positives[:3]) if positives else "ingen stark kombination av bekräftande kortsiktiga signaler"

    counter = vetoes[0] if vetoes else (cautions[0] if cautions else "signalen kan snabbt försvagas om relativ styrka eller trend vänder")

    return {
        "Short Alpha Score": round(_clip(score), 1),
        "Short Alpha Gate": gate,
        "Short Alpha Confidence": confidence,
        "Short Trend": round(trend, 1),
        "Short Relative Strength": round(relative, 1),
        "Short Relative Text": relative_text,
        "Short Momentum": round(momentum, 1),
        "Short Participation": round(participation, 1),
        "Short Revisions": round(revisions, 1),
        "Short Catalyst": round(catalyst_score, 1),
        "Short Confirmation Count": int(confirmation_count),
        "Short Why Now": why_now,
        "Short Counterargument": counter,
        "Short Vetoes": "; ".join(vetoes) if vetoes else "—",
        "Short Cautions": "; ".join(cautions) if cautions else "—",
    }


def short_term_rank_key(row: dict[str, Any] | pd.Series) -> tuple:
    order = {
        "Kortsiktigt toppcase": 4,
        "Starkt kortsiktigt case": 3,
        "Bevaka kortsiktigt": 2,
        "Svag kortsiktig signal": 1,
        "Ej kortsiktigt toppcase": 0,
    }
    return (
        order.get(str(row.get("Short Alpha Gate", "")), 0),
        _num(row.get("Short Alpha Score")),
        _num(row.get("Short Alpha Confidence")),
    )
