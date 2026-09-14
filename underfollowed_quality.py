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


def assess_underfollowed_quality(row: pd.Series | dict[str, Any], horizon: str) -> dict[str, Any]:
    """Find high-quality companies with *observed* low attention.

    Low analyst/media attention is context, never a positive signal by itself. A strong
    label requires good Borsify data coverage and durable fundamentals. Missing analyst
    coverage is explicitly not interpreted as low coverage.
    """
    r = row
    analysts = _num(r.get("Analytiker antal"))
    news_n = _num(r.get("News Flow Unique Items 30d"))
    news_status = str(r.get("News Flow Status") or "").strip()
    coverage = _num(r.get("Datatäckning"))
    turnover = _num(r.get("Omsättning MSEK/dag"))

    quality = _num(r.get("Kvalitet"))
    risk = _num(r.get("Risk"))
    roe = _num(r.get("ROE"))
    margin = _num(r.get("Vinstmarginal"))
    fcf_yield = _num(r.get("FCF yield"))
    invest = _num(r.get("INVEST Score"))
    valuation = _num(r.get("Värdering"))

    neg_families = [x.strip() for x in str(r.get("Förändringsbekräftelse negativa familjer") or "").split(",") if x.strip()]
    report_neg = _num(r.get("Report Delta negativa"))
    report_pos = _num(r.get("Report Delta positiva"))
    falling_knife = _yes(r.get("Fallande kniv varning"))
    crowded = _yes(r.get("Crowded varning")) or _yes(r.get("Crowded stark varning"))

    supports: list[str] = []
    warnings: list[str] = []

    observed_analyst = np.isfinite(analysts) and analysts >= 0
    low_analyst = observed_analyst and analysts <= 3
    if low_analyst:
        supports.append(f"endast {int(analysts)} observerade analytiker följer bolaget")
    elif not observed_analyst:
        warnings.append("analytikertäckning saknas och får inte tolkas som låg bevakning")
    else:
        warnings.append("bolaget har inte låg observerad analytikertäckning")

    # Media quietness is only a secondary context signal. It can never qualify a case
    # unless analyst coverage is observed and fundamentals/data quality are strong.
    observed_news = bool(news_status) and np.isfinite(news_n) and news_n >= 0
    low_news = observed_news and news_n <= 3
    if low_news:
        supports.append(f"lågt observerat nyhetsflöde ({int(news_n)} unika poster på 30 dagar)")

    durable = 0
    if np.isfinite(quality) and quality >= 75:
        durable += 1; supports.append("hög bolagskvalitet")
    if np.isfinite(risk) and risk >= 65:
        durable += 1; supports.append("robust riskprofil")
    if np.isfinite(roe) and roe >= .15:
        durable += 1; supports.append(f"stark ROE ({roe:.0%})")
    if np.isfinite(margin) and margin >= .10:
        durable += 1; supports.append(f"god vinstmarginal ({margin:.0%})")
    if np.isfinite(fcf_yield) and fcf_yield > 0:
        durable += 1; supports.append("positiv fri-kassaflödesyield")
    if np.isfinite(invest) and invest >= 70:
        durable += 1; supports.append("stark långsiktig INVEST-bedömning")

    data_ok = np.isfinite(coverage) and coverage >= .65
    if data_ok:
        supports.append(f"Borsify har god egen datatäckning ({coverage:.0%})")
    else:
        warnings.append("Borsifys egen datatäckning är för låg eller saknas")

    deterioration = (
        falling_knife
        or len(neg_families) >= 2
        or (np.isfinite(report_neg) and report_neg >= 2 and (not np.isfinite(report_pos) or report_neg >= report_pos))
    )
    if deterioration:
        warnings.append("fundamental försämring gör låg uppmärksamhet till ett risktecken, inte ett fynd")
    if crowded:
        warnings.append("förväntningsbilden är redan trång trots låg bevakning")
    if np.isfinite(turnover) and turnover < 1.0:
        warnings.append("mycket låg handelsomsättning ökar exekveringsrisken")
    if np.isfinite(valuation) and valuation < 35:
        warnings.append("värderingsbilden ger inte stöd för ett tydligt kvalitetsfynd")

    long_horizon = horizon in {"year", "long", "lifetime"}
    liquid_enough = not np.isfinite(turnover) or turnover >= 1.0

    if not long_horizon:
        tier = 0
        label = "— Underfollowed Quality används bara långsiktigt"
    elif not observed_analyst:
        tier = 0
        label = "— Underfollowed kan inte verifieras"
    elif not low_analyst:
        tier = 0
        label = "— Inte tydligt underfollowed"
    elif deterioration:
        tier = -1
        label = "⚠️ Underfollowed men fundamental försämring dominerar"
    elif not data_ok or durable < 3:
        tier = 0
        label = "— Låg bevakning utan tillräckligt kvalitetsbevis"
    elif durable >= 5 and liquid_enough and (low_news or not observed_news) and not crowded:
        tier = 3
        label = "💎 Underfollowed Quality · stark fyndkandidat"
    elif durable >= 4 and liquid_enough and not crowded:
        tier = 2
        label = "🟢 Hög kvalitet · låg observerad bevakning"
    else:
        tier = 1
        label = "🟡 Underfollowed kvalitetscase – men fler bevis behövs"

    # Analyst count itself is deliberately not a rank gradient: 1 analyst is not
    # 'better' than 3 analysts. Once low coverage is established, quality/data win.
    rank = float(max(tier, 0) * 100 + min(durable, 6) * 7 + (6 if low_news else 0) - min(len(warnings), 4) * 8)
    if tier < 0:
        rank = -100.0

    why = "; ".join(supports[:6]) if supports else "ingen verifierad kombination av hög kvalitet och låg uppmärksamhet"
    if warnings:
        why += ". Motargument: " + "; ".join(warnings[:3])

    return {
        "Underfollowed Quality": label,
        "Underfollowed Quality nivå": tier,
        "Underfollowed Quality rangvärde": rank,
        "Underfollowed Quality kvalitetspoäng": durable,
        "Underfollowed Quality analytiker": analysts if observed_analyst else np.nan,
        "Underfollowed Quality nyhetsflöde": news_n if observed_news else np.nan,
        "Underfollowed Quality stöd": "; ".join(supports[:7]),
        "Underfollowed Quality varningar": "; ".join(warnings[:5]),
        "Underfollowed Quality förklaring": why,
    }


def add_underfollowed_quality(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    extra = pd.DataFrame([assess_underfollowed_quality(r, horizon) for _, r in out.iterrows()], index=out.index)
    overlap = [c for c in extra.columns if c in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    return out.join(extra)
