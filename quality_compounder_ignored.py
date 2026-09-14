from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _yes(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or "").strip().lower() in {"1", "true", "ja", "yes"}


def assess_quality_compounder_ignored(row: pd.Series | dict[str, Any], horizon: str) -> dict[str, Any]:
    """Find durable compounders that the market is temporarily ignoring.

    This is a long-horizon ranking context layer, not a buy gate. It requires durable
    quality plus muted attention/price action, and rejects cases where weak momentum
    coincides with clear fundamental deterioration. Missing data is neutral.
    """
    r = row
    quality = _num(r.get("Kvalitet"))
    risk = _num(r.get("Risk"))
    roe = _num(r.get("ROE"))
    margin = _num(r.get("Vinstmarginal"))
    fcf_yield = _num(r.get("FCF yield"))
    debt = _num(r.get("Skuld/eget kapital"))
    valuation = _num(r.get("Värdering"))
    invest = _num(r.get("INVEST Score"))

    m1 = _num(r.get("1 mån"))
    m3 = _num(r.get("3 mån"))
    m6 = _num(r.get("6 mån"))
    dist = _num(r.get("Avstånd SMA200"))
    momentum = _num(r.get("12–1 momentum"))

    neg_families = [x.strip() for x in str(r.get("Förändringsbekräftelse negativa familjer") or "").split(",") if x.strip()]
    report_neg = _num(r.get("Report Delta negativa"))
    report_pos = _num(r.get("Report Delta positiva"))
    hidden_level = _num(r.get("Hidden inflection nivå"))
    accel_level = _num(r.get("Mispriced acceleration nivå"))
    falling_knife = _yes(r.get("Fallande kniv varning"))
    crowded = _yes(r.get("Crowded varning")) or _yes(r.get("Crowded stark varning"))

    supports: list[str] = []
    warnings: list[str] = []

    # Durable business quality.
    if np.isfinite(quality) and quality >= 75:
        supports.append("hög strukturell bolagskvalitet")
    if np.isfinite(risk) and risk >= 65:
        supports.append("robust riskprofil")
    if np.isfinite(roe) and roe >= .15:
        supports.append(f"stark avkastning på eget kapital ({roe:.0%})")
    if np.isfinite(margin) and margin >= .10:
        supports.append(f"god vinstmarginal ({margin:.0%})")
    if np.isfinite(fcf_yield) and fcf_yield > 0:
        supports.append("positiv fri-kassaflödesyield")
    if np.isfinite(debt) and debt <= 1.0:
        supports.append("balanserad skuldsättning")
    if np.isfinite(invest) and invest >= 70:
        supports.append("stark långsiktig INVEST-bedömning")

    # "Ignored" = muted/boring price action, not a collapse and not a chase.
    muted = 0
    if np.isfinite(m1) and -.10 <= m1 <= .06:
        muted += 1
    if np.isfinite(m3) and -.15 <= m3 <= .12:
        muted += 1
    if np.isfinite(dist) and -.12 <= dist <= .08:
        muted += 1
    if np.isfinite(momentum) and -.10 <= momentum <= .15:
        muted += 1
    if muted >= 2:
        supports.append("kursintresset är dämpat snarare än euforiskt")

    # Avoid cheap-looking value traps.
    deterioration = (
        falling_knife
        or len(neg_families) >= 2
        or (np.isfinite(report_neg) and report_neg >= 2 and (not np.isfinite(report_pos) or report_neg >= report_pos))
        or (np.isfinite(hidden_level) and hidden_level < 0)
        or (np.isfinite(accel_level) and accel_level < 0)
    )
    if deterioration:
        warnings.append("svagare kurs sammanfaller med verifierad fundamental försämring")
    if np.isfinite(quality) and quality < 65:
        warnings.append("bolagskvaliteten är inte tillräckligt hög")
    if np.isfinite(risk) and risk < 55:
        warnings.append("riskprofilen är för svag")
    if np.isfinite(valuation) and valuation < 35:
        warnings.append("värderingsmodellen signalerar inte ett attraktivt kvalitetsläge")
    if crowded:
        warnings.append("förväntningsbilden är redan trång")
    if np.isfinite(m3) and m3 > .25:
        warnings.append("aktien är inte förbiseddd – kursen har redan gått starkt")
    if np.isfinite(m3) and m3 < -.30:
        warnings.append("kursfallet är för stort för att kallas tillfälligt ointresse utan mer bevis")

    durable = sum([
        np.isfinite(quality) and quality >= 75,
        np.isfinite(risk) and risk >= 65,
        np.isfinite(roe) and roe >= .15,
        np.isfinite(margin) and margin >= .10,
        np.isfinite(fcf_yield) and fcf_yield > 0,
        np.isfinite(invest) and invest >= 70,
    ])
    long_horizon = horizon in {"year", "long", "lifetime"}

    if not long_horizon:
        tier = 0
        label = "— Compounder-signalen används bara långsiktigt"
    elif deterioration:
        tier = -1
        label = "⚠️ Inte förbiseddd compounder – försämring måste utredas"
    elif durable < 3:
        tier = 0
        label = "— För lite bevisad compounder-kvalitet"
    elif muted < 2:
        tier = 1
        label = "🟡 Kvalitetscompounder – men inte tydligt förbisedd"
    elif durable >= 5 and not crowded and (not np.isfinite(valuation) or valuation >= 50):
        tier = 3
        label = "💎 Quality compounder temporarily ignored"
    else:
        tier = 2
        label = "🟢 Stark compounder i tillfälligt marknadsskugga"

    rank = float(max(tier, 0) * 100 + min(durable, 6) * 6 + min(muted, 4) * 5 - min(len(warnings), 4) * 8)
    if tier < 0:
        rank = -100.0

    why = "; ".join(supports[:5]) if supports else "ingen tydlig kombination av uthållig kvalitet och dämpat marknadsintresse"
    if warnings:
        why += ". Motargument: " + "; ".join(warnings[:3])

    return {
        "Ignored compounder": label,
        "Ignored compounder nivå": tier,
        "Ignored compounder rangvärde": rank,
        "Ignored compounder kvalitetspoäng": durable,
        "Ignored compounder ointressepoäng": muted,
        "Ignored compounder stöd": "; ".join(supports[:6]),
        "Ignored compounder varningar": "; ".join(warnings[:5]),
        "Ignored compounder förklaring": why,
    }


def add_quality_compounder_ignored(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    extra = pd.DataFrame([assess_quality_compounder_ignored(r, horizon) for _, r in out.iterrows()], index=out.index)
    overlap = [c for c in extra.columns if c in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    return out.join(extra)
