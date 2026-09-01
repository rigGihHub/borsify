from __future__ import annotations

import math
from typing import Any

import numpy as np


def _num(value: Any, default: float = np.nan) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except Exception:
        return default


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _cagr(series) -> float:
    try:
        vals = [float(x) for x in series if x is not None and math.isfinite(float(x)) and float(x) > 0]
    except Exception:
        return np.nan
    if len(vals) < 2:
        return np.nan
    years = len(vals) - 1
    return (vals[-1] / vals[0]) ** (1 / years) - 1 if years > 0 else np.nan


def build_scenarios(row: dict, deep: dict | None = None, inflection: dict | None = None,
                    mispricing: dict | None = None, horizon_years: int = 5) -> dict:
    """Transparent Bear/Base/Bull scenarios for long-term cases.

    This is deliberately not a price target model pretending to know the future.
    Assumptions are derived from current EPS, observed growth and current/forward P/E,
    then bounded to avoid extreme extrapolation.
    """
    deep = deep or {}
    inflection = inflection or {}
    mispricing = mispricing or {}

    price = _num(row.get("Pris") or row.get("price"))
    eps = _num(row.get("EPS") or row.get("Trailing EPS") or row.get("trailingEps"))
    fwd_eps = _num(row.get("Forward EPS") or row.get("forwardEps"))
    pe = _num(row.get("P/E") or row.get("PE"))
    fwd_pe = _num(row.get("Forward P/E") or row.get("forwardPE"))

    if not math.isfinite(eps) and math.isfinite(price) and math.isfinite(pe) and pe > 0:
        eps = price / pe
    if not math.isfinite(eps) or eps <= 0 or not math.isfinite(price) or price <= 0:
        return {
            "status": "Otillräcklig data",
            "reason": "Positiv EPS och aktuellt pris krävs för transparenta scenarios.",
            "confidence": 0,
        }

    current_pe = fwd_pe if math.isfinite(fwd_pe) and fwd_pe > 0 else (pe if math.isfinite(pe) and pe > 0 else price / eps)
    current_pe = _clip(current_pe, 6.0, 60.0)

    growth_candidates = []
    for key in ("Revenue CAGR", "EPS CAGR", "FCF CAGR", "Vinst CAGR", "Omsättning CAGR"):
        v = _num(deep.get(key))
        if math.isfinite(v):
            if abs(v) > 1.5:  # tolerate percentages
                v /= 100.0
            growth_candidates.append(v)
    verified_growth = _num(mispricing.get("verified_growth"))
    if math.isfinite(verified_growth):
        if abs(verified_growth) > 1.5:
            verified_growth /= 100.0
        growth_candidates.append(verified_growth)

    base_growth = float(np.median(growth_candidates)) if growth_candidates else np.nan
    if math.isfinite(fwd_eps) and fwd_eps > 0:
        forward_growth = fwd_eps / eps - 1
        base_growth = forward_growth if not math.isfinite(base_growth) else 0.65 * base_growth + 0.35 * forward_growth

    infl = _num(inflection.get("score") or inflection.get("Inflection Score"))
    if math.isfinite(infl):
        base_growth += _clip((infl - 50.0) / 1000.0, -0.04, 0.04)

    if not math.isfinite(base_growth):
        return {
            "status": "Otillräcklig data",
            "reason": "Borsify saknar tillräcklig verifierbar tillväxthistorik för scenarios.",
            "confidence": 20,
        }

    base_growth = _clip(base_growth, -0.05, 0.22)
    spread = 0.06 + min(0.05, abs(base_growth) * 0.25)
    bear_growth = _clip(base_growth - spread, -0.15, 0.12)
    bull_growth = _clip(base_growth + spread, 0.02, 0.30)

    # Mean-reversion rather than assuming today's multiple persists forever.
    base_pe = _clip(0.55 * current_pe + 0.45 * 20.0, 10.0, 32.0)
    bear_pe = _clip(base_pe * 0.72, 7.0, 22.0)
    bull_pe = _clip(base_pe * 1.22, 14.0, 38.0)

    trap = _num(deep.get("Value Trap Risk") or deep.get("value_trap_risk"))
    if math.isfinite(trap):
        if trap >= 70:
            bear_growth -= 0.03
            bear_pe *= 0.88
            base_growth -= 0.015
        elif trap >= 50:
            bear_growth -= 0.015

    def one(name: str, growth: float, exit_pe: float) -> dict:
        future_eps = eps * ((1 + growth) ** horizon_years)
        future_price = future_eps * exit_pe
        total = future_price / price - 1
        cagr = (future_price / price) ** (1 / horizon_years) - 1 if future_price > 0 else -1
        return {
            "name": name,
            "eps_growth": growth,
            "exit_pe": exit_pe,
            "future_eps": future_eps,
            "future_price": future_price,
            "upside": total,
            "annualized_return": cagr,
        }

    bear = one("Bear", bear_growth, bear_pe)
    base = one("Base", base_growth, base_pe)
    bull = one("Bull", bull_growth, bull_pe)

    upside = max(0.0, base["upside"])
    downside = max(0.0, -bear["upside"])
    asymmetry = upside / downside if downside > 0.02 else (5.0 if upside > 0 else 0.0)
    asymmetry = _clip(asymmetry, 0.0, 5.0)

    if bear["upside"] > 0.10:
        risk_label = "Ovanligt robust scenario – kontrollera antagandena"
    elif bear["upside"] > -0.15:
        risk_label = "Begränsad modellerad nedsida"
    elif bear["upside"] > -0.35:
        risk_label = "Tydlig nedsida om caset sviker"
    else:
        risk_label = "Stor nedsida i bear-scenariot"

    if asymmetry >= 2.0 and base["annualized_return"] >= 0.10:
        verdict = "Attraktiv asymmetri"
    elif asymmetry >= 1.2 and base["annualized_return"] >= 0.08:
        verdict = "Möjligen attraktiv asymmetri"
    elif base["annualized_return"] < 0.06:
        verdict = "Svag risk/reward"
    else:
        verdict = "Blandad risk/reward"

    data_points = 2 + len(growth_candidates) + int(math.isfinite(fwd_eps)) + int(math.isfinite(fwd_pe))
    confidence = int(_clip(28 + 9 * data_points - (15 if math.isfinite(trap) and trap >= 70 else 0), 20, 90))

    return {
        "status": "OK",
        "horizon_years": horizon_years,
        "current_price": price,
        "current_eps": eps,
        "current_pe": current_pe,
        "bear": bear,
        "base": base,
        "bull": bull,
        "asymmetry": asymmetry,
        "verdict": verdict,
        "risk_label": risk_label,
        "confidence": confidence,
        "note": "Scenarioanalys, inte prognos. Kursnivåerna beror direkt på synliga antaganden om EPS-tillväxt och framtida P/E.",
    }


def scenario_summary(result: dict) -> str:
    if result.get("status") != "OK":
        return result.get("reason", "Otillräcklig data.")
    b, m, u = result["bear"], result["base"], result["bull"]
    return (
        f'{result["verdict"]}. Bear {b["upside"]:+.0%}, Base {m["upside"]:+.0%}, '
        f'Bull {u["upside"]:+.0%} över {result["horizon_years"]} år. '
        f'Asymmetri {result["asymmetry"]:.1f}x.'
    )
