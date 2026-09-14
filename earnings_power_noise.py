from __future__ import annotations

import math
import re
from typing import Any

import numpy as np
import pandas as pd


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _txt(v: Any) -> str:
    return str(v or "").strip().lower()


_TEMPORARY_TERMS = re.compile(
    r"\b(temporary|temporar(?:y|ily)|transitory|one[- ]off|non[- ]recurring|restructur(?:ing|ing charge)|"
    r"engångs|tillfällig|tillfälligt|omstrukturering|lageravveckling|inventory correction)\b",
    re.I,
)
_NEGATIVE_GUIDANCE = re.compile(r"profit warning|cuts? guidance|lower(?:s|ed) outlook|sänk(?:er|t) prognos|vinstvarn", re.I)
_POSITIVE_GUIDANCE = re.compile(r"raises? guidance|raised outlook|höj(?:er|d) prognos|höj(?:er|da) utsikter", re.I)


def assess_earnings_power_noise(row: pd.Series | dict[str, Any], horizon: str) -> dict[str, Any]:
    """Find headline earnings weakness that is not confirmed by the broader earning-power picture.

    A weak quarter is never called 'temporary' without explicit text evidence. When such evidence is
    absent, Borsify only reports a mismatch between headline earnings and the broader operating data.
    This is ranking context after buy gates, never a standalone buy signal.
    """
    r = row
    quality = _num(r.get("Kvalitet")); risk = _num(r.get("Risk")); invest = _num(r.get("INVEST Score"))
    earn_yoy = _num(r.get("Vinst YoY senaste kvartal")); margin_yoy = _num(r.get("Marginal YoY förändring"))
    rev_yoy = _num(r.get("Omsättning YoY senaste kvartal")); rev_acc = _num(r.get("Omsättning acceleration"))
    fcf_yoy = _num(r.get("FCF YoY senaste kvartal")); surprise = _num(r.get("Senaste EPS-överraskning"))
    report_pos = _num(r.get("Report Delta positiva")); report_neg = _num(r.get("Report Delta negativa"))
    eps_rev = _num(r.get("EPS-estimat förändring")); rev_balance = _num(r.get("EPS-revisionsbalans"))

    text_fields = [
        r.get("Report Delta guidance"), r.get("Report Delta förklaring"), r.get("Catalyst Evidence"),
        r.get("Catalyst Why Now"), r.get("Ledningssignal förklaring"), r.get("News Impact Summary"),
        r.get("News Surprise Summary"), r.get("Fresh Change Summary"),
    ]
    evidence_text = " | ".join(str(x or "") for x in text_fields)
    explicit_temporary = bool(_TEMPORARY_TERMS.search(evidence_text))
    guidance_negative = bool(_NEGATIVE_GUIDANCE.search(evidence_text))
    guidance_positive = bool(_POSITIVE_GUIDANCE.search(evidence_text))

    headline_weakness = []
    if np.isfinite(earn_yoy) and earn_yoy <= -.10: headline_weakness.append(f"vinsten föll {abs(earn_yoy):.0%} år/år")
    if np.isfinite(margin_yoy) and margin_yoy <= -.015: headline_weakness.append(f"marginalen försämrades {abs(margin_yoy):.1%}-enheter")
    if np.isfinite(surprise) and surprise <= -.05: headline_weakness.append(f"EPS missade förväntan med cirka {abs(surprise):.0%}")

    supports = []
    if np.isfinite(rev_yoy) and rev_yoy >= .03: supports.append("omsättningen växer fortfarande")
    if np.isfinite(rev_acc) and rev_acc >= 0: supports.append("försäljningstillväxten bromsar inte")
    if np.isfinite(fcf_yoy) and fcf_yoy >= .05: supports.append("fritt kassaflöde förbättras")
    if np.isfinite(quality) and quality >= 70: supports.append("bolagskvaliteten är fortsatt hög")
    if np.isfinite(risk) and risk >= 60: supports.append("riskprofilen är fortsatt robust")
    if np.isfinite(invest) and invest >= 65: supports.append("långsiktig INVEST-bedömning är stark")
    if np.isfinite(report_pos) and np.isfinite(report_neg) and report_pos > report_neg: supports.append("rapportdelta är netto positiv trots rubriksvaghet")
    if np.isfinite(eps_rev) and eps_rev >= 0: supports.append("estimaten har inte sänkts")
    if np.isfinite(rev_balance) and rev_balance >= 0: supports.append("revisionsbalansen är inte negativ")
    if guidance_positive: supports.append("guidance/utsikter har uttryckligen stärkts")
    if explicit_temporary: supports.append("rapport-/nyhetstext beskriver en uttryckligen tillfällig eller engångsmässig faktor")

    warnings = []
    if guidance_negative: warnings.append("guidance/utsikter har sänkts")
    if np.isfinite(report_neg) and report_neg >= 2 and (not np.isfinite(report_pos) or report_neg >= report_pos):
        warnings.append("rapportförsämringen är bredare än bara rubrikvinsten")
    if np.isfinite(eps_rev) and eps_rev <= -.04: warnings.append("vinstestimaten har sänkts tydligt")
    if np.isfinite(rev_balance) and rev_balance <= -.35: warnings.append("revisionsbalansen är tydligt negativ")
    if np.isfinite(fcf_yoy) and fcf_yoy <= -.20: warnings.append("kassaflödet försämras kraftigt")
    if np.isfinite(rev_yoy) and rev_yoy <= -.05: warnings.append("omsättningen minskar tydligt")

    broad_break = guidance_negative or len(warnings) >= 2
    long_horizon = horizon in {"year", "long", "lifetime"}
    support_n = len([s for s in supports if "tillfällig" not in s])

    if not long_horizon:
        tier = 0; label = "— Earnings-power-signalen används bara långsiktigt"
    elif not headline_weakness:
        tier = 0; label = "— Ingen tydlig rubriksvaghet att normalisera"
    elif broad_break:
        tier = -1; label = "⚠️ Svagheten ser bred ut – behandla inte som tillfälligt brus"
    elif support_n < 3:
        tier = 0; label = "— Rubriksvaghet men för lite stöd för dold intjäningskraft"
    elif explicit_temporary and support_n >= 4:
        tier = 3; label = "💎 Earnings power hidden by temporary noise"
    elif support_n >= 4:
        tier = 2; label = "🟢 Underliggande intjäningskraft ser starkare ut än rubrikresultatet"
    else:
        tier = 1; label = "🟡 Möjlig earnings-power mismatch – fler bevis behövs"

    rank = float(max(tier, 0) * 100 + min(support_n, 7) * 6 + (15 if explicit_temporary and tier > 0 else 0) - min(len(warnings), 4) * 10)
    if tier < 0: rank = -100.0

    why = "; ".join(headline_weakness[:3]) if headline_weakness else "ingen tydlig rubriksvaghet"
    if supports: why += ". Underliggande stöd: " + "; ".join(supports[:5])
    if not explicit_temporary and tier > 0:
        why += ". Borsify har inte explicit bevis för att svagheten är tillfällig och kallar därför detta mismatch, inte engångseffekt."
    if warnings: why += ". Motargument: " + "; ".join(warnings[:3])

    return {
        "Earnings power noise": label,
        "Earnings power noise nivå": tier,
        "Earnings power noise rangvärde": rank,
        "Earnings power temporary verified": explicit_temporary,
        "Earnings power headline weakness": "; ".join(headline_weakness[:4]),
        "Earnings power stöd": "; ".join(supports[:7]),
        "Earnings power varningar": "; ".join(warnings[:5]),
        "Earnings power förklaring": why,
    }


def add_earnings_power_noise(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    extra = pd.DataFrame([assess_earnings_power_noise(r, horizon) for _, r in out.iterrows()], index=out.index)
    overlap = [c for c in extra.columns if c in out.columns]
    if overlap: out = out.drop(columns=overlap)
    return out.join(extra)
