from __future__ import annotations

from typing import Any, Iterable
import math

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        value = float(value)
        return value if math.isfinite(value) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _find_row(frame: pd.DataFrame | None, names: Iterable[str]) -> pd.Series:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(dtype=float)
    lookup = {str(i).strip().lower(): i for i in frame.index}
    for name in names:
        key = str(name).strip().lower()
        if key in lookup:
            s = pd.to_numeric(frame.loc[lookup[key]], errors="coerce").dropna()
            if s.empty:
                continue
            try:
                s.index = pd.to_datetime(s.index, errors="coerce")
                s = s[~s.index.isna()].sort_index(ascending=False)
            except Exception:
                pass
            return s.astype(float)
    return pd.Series(dtype=float)


def _ratio_series(numer: pd.Series, denom: pd.Series) -> pd.Series:
    if numer.empty or denom.empty:
        return pd.Series(dtype=float)
    common = numer.index.intersection(denom.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    d = pd.to_numeric(denom.loc[common], errors="coerce").replace(0, np.nan)
    n = pd.to_numeric(numer.loc[common], errors="coerce")
    return (n / d).replace([np.inf, -np.inf], np.nan).dropna().sort_index(ascending=False)


def _yoy(series: pd.Series, offset: int = 4) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) <= offset:
        return np.nan
    latest, prior = _num(s.iloc[0]), _num(s.iloc[offset])
    if np.isfinite(latest) and np.isfinite(prior) and prior != 0:
        return latest / prior - 1
    return np.nan


def _qoq(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 2:
        return np.nan
    latest, prior = _num(s.iloc[0]), _num(s.iloc[1])
    if np.isfinite(latest) and np.isfinite(prior) and prior != 0:
        return latest / prior - 1
    return np.nan


def _pick_index(frame: pd.DataFrame | None, preferred: tuple[str, ...] = ("+1y", "0y", "+1q", "0q")) -> pd.Series:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(dtype=object)
    idx_map = {str(i).strip().lower(): i for i in frame.index}
    for key in preferred:
        original = idx_map.get(key.lower())
        if original is not None:
            row = frame.loc[original]
            return row if isinstance(row, pd.Series) else pd.Series(row)
    try:
        row = frame.iloc[0]
        return row if isinstance(row, pd.Series) else pd.Series(row)
    except Exception:
        return pd.Series(dtype=object)


def _col_value(row: pd.Series, names: Iterable[str]) -> float:
    if row.empty:
        return np.nan
    lookup = {str(c).strip().lower(): c for c in row.index}
    for name in names:
        col = lookup.get(str(name).strip().lower())
        if col is not None:
            value = _num(row.get(col))
            if np.isfinite(value):
                return value
    return np.nan


def _eps_revision_change(eps_trend: pd.DataFrame | None) -> tuple[float, str]:
    row = _pick_index(eps_trend)
    if row.empty:
        return np.nan, "—"
    current = _col_value(row, ["current", "currentEstimate", "avg"])
    for label, aliases in [
        ("30 dagar", ["30daysAgo", "30DaysAgo", "30dAgo"]),
        ("60 dagar", ["60daysAgo", "60DaysAgo", "60dAgo"]),
        ("90 dagar", ["90daysAgo", "90DaysAgo", "90dAgo"]),
        ("7 dagar", ["7daysAgo", "7DaysAgo", "7dAgo"]),
    ]:
        previous = _col_value(row, aliases)
        if np.isfinite(current) and np.isfinite(previous) and previous != 0:
            return current / previous - 1, label
    return np.nan, "—"


def _revision_balance(eps_revisions: pd.DataFrame | None) -> float:
    row = _pick_index(eps_revisions)
    if row.empty:
        return np.nan
    up = _col_value(row, ["upLast30days", "upLast30Days", "upLast30days"])
    down = _col_value(row, ["downLast30days", "downLast30Days", "downLast30days"])
    if not np.isfinite(up) and not np.isfinite(down):
        up = _col_value(row, ["upLast7days", "upLast7Days"])
        down = _col_value(row, ["downLast7days", "downLast7Days"])
    if not np.isfinite(up) and not np.isfinite(down):
        return np.nan
    up = up if np.isfinite(up) else 0.0
    down = down if np.isfinite(down) else 0.0
    total = up + down
    return (up - down) / total if total > 0 else 0.0


def _latest_surprise(earnings_history: pd.DataFrame | None) -> float:
    if earnings_history is None or not isinstance(earnings_history, pd.DataFrame) or earnings_history.empty:
        return np.nan
    columns = {str(c).strip().lower(): c for c in earnings_history.columns}
    col = None
    for name in ["surprisePercent", "surprise%", "surprise"]:
        if name.lower() in columns:
            col = columns[name.lower()]
            break
    if col is None:
        return np.nan
    s = pd.to_numeric(earnings_history[col], errors="coerce").dropna()
    if s.empty:
        return np.nan
    try:
        idx = pd.to_datetime(s.index, errors="coerce")
        if idx.notna().any():
            s = s.loc[idx.argsort()[::-1]]
    except Exception:
        pass
    value = _num(s.iloc[0])
    # yfinance has used both decimal and percentage-point representations.
    if np.isfinite(value) and abs(value) > 2:
        value /= 100.0
    return value


def build_inflection_metrics(
    quarterly_income: pd.DataFrame | None,
    quarterly_cashflow: pd.DataFrame | None,
    eps_trend: pd.DataFrame | None = None,
    eps_revisions: pd.DataFrame | None = None,
    earnings_history: pd.DataFrame | None = None,
) -> dict[str, Any]:
    """Build change-focused evidence without inventing missing estimates.

    Financial statement fields are observed quarterly data. Analyst fields are
    kept separate because they are estimates/opinions and may be unavailable.
    """
    revenue = _find_row(quarterly_income, ["Total Revenue", "Operating Revenue"])
    operating_income = _find_row(quarterly_income, ["Operating Income", "EBIT"])
    net_income = _find_row(quarterly_income, ["Net Income", "Net Income Common Stockholders"])
    fcf = _find_row(quarterly_cashflow, ["Free Cash Flow"])
    if fcf.empty:
        ocf = _find_row(quarterly_cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
        capex = _find_row(quarterly_cashflow, ["Capital Expenditure", "Capital Expenditures"])
        common = ocf.index.intersection(capex.index)
        if len(common):
            cap = capex.loc[common]
            fcf = (ocf.loc[common] + cap.where(cap <= 0, -cap)).dropna().sort_index(ascending=False)

    op_margin = _ratio_series(operating_income, revenue)
    net_margin = _ratio_series(net_income, revenue)
    margin_series = op_margin if len(op_margin) >= 2 else net_margin

    latest_margin = _num(margin_series.iloc[0]) if len(margin_series) else np.nan
    yoy_margin = latest_margin - _num(margin_series.iloc[4]) if len(margin_series) >= 5 else np.nan
    qoq_margin = latest_margin - _num(margin_series.iloc[1]) if len(margin_series) >= 2 else np.nan

    eps_change, eps_window = _eps_revision_change(eps_trend)
    revision_balance = _revision_balance(eps_revisions)
    surprise = _latest_surprise(earnings_history)

    rev_yoy = _yoy(revenue)
    previous_rev_yoy = np.nan
    if len(revenue) >= 6:
        current_without_latest = revenue.iloc[1:]
        previous_rev_yoy = _yoy(current_without_latest)

    return {
        "Kvartalsdata antal": int(max(len(revenue), len(net_income), len(fcf))),
        "Omsättning YoY senaste kvartal": rev_yoy,
        "Omsättning YoY föregående kvartal": previous_rev_yoy,
        "Omsättning acceleration": rev_yoy - previous_rev_yoy if np.isfinite(rev_yoy) and np.isfinite(previous_rev_yoy) else np.nan,
        "Omsättning QoQ": _qoq(revenue),
        "Marginal senaste kvartal": latest_margin,
        "Marginal YoY förändring": yoy_margin,
        "Marginal QoQ förändring": qoq_margin,
        "FCF YoY senaste kvartal": _yoy(fcf),
        "Vinst YoY senaste kvartal": _yoy(net_income),
        "EPS-estimat förändring": eps_change,
        "EPS-estimat jämförelseperiod": eps_window,
        "EPS-revisionsbalans": revision_balance,
        "Senaste EPS-överraskning": surprise,
    }


def assess_inflection(metrics: dict[str, Any]) -> dict[str, Any]:
    """Transparent inflection/revision triage.

    The score is an evidence index, not an expected-return forecast. Strong
    negative estimate revisions are deliberately harder to offset than a single
    positive quarter is to reward.
    """
    score = 50.0
    positive: list[str] = []
    negative: list[str] = []
    evidence = 0

    eps_change = _num(metrics.get("EPS-estimat förändring"))
    rev_balance = _num(metrics.get("EPS-revisionsbalans"))
    rev_yoy = _num(metrics.get("Omsättning YoY senaste kvartal"))
    rev_acc = _num(metrics.get("Omsättning acceleration"))
    margin_yoy = _num(metrics.get("Marginal YoY förändring"))
    margin_qoq = _num(metrics.get("Marginal QoQ förändring"))
    fcf_yoy = _num(metrics.get("FCF YoY senaste kvartal"))
    earnings_yoy = _num(metrics.get("Vinst YoY senaste kvartal"))
    surprise = _num(metrics.get("Senaste EPS-överraskning"))

    if np.isfinite(eps_change):
        evidence += 1
        if eps_change >= .05:
            score += 18; positive.append(f"EPS-estimat har höjts cirka {eps_change:.1%}")
        elif eps_change >= .02:
            score += 10; positive.append(f"EPS-estimat har höjts cirka {eps_change:.1%}")
        elif eps_change <= -.05:
            score -= 24; negative.append(f"EPS-estimat har sänkts cirka {abs(eps_change):.1%}")
        elif eps_change <= -.02:
            score -= 14; negative.append(f"EPS-estimat har sänkts cirka {abs(eps_change):.1%}")

    if np.isfinite(rev_balance):
        evidence += 1
        if rev_balance >= .35:
            score += 10; positive.append("fler analytiker har höjt än sänkt estimaten")
        elif rev_balance <= -.35:
            score -= 13; negative.append("fler analytiker har sänkt än höjt estimaten")

    if np.isfinite(rev_acc):
        evidence += 1
        if rev_acc >= .05 and np.isfinite(rev_yoy) and rev_yoy > 0:
            score += 11; positive.append("omsättningstillväxten accelererar")
        elif rev_acc <= -.08:
            score -= 10; negative.append("omsättningstillväxten bromsar tydligt")

    if np.isfinite(margin_yoy):
        evidence += 1
        if margin_yoy >= .02:
            score += 13; positive.append(f"marginalen är cirka {margin_yoy:.1%}-enheter bättre än för ett år sedan")
        elif margin_yoy <= -.03:
            score -= 15; negative.append(f"marginalen är cirka {abs(margin_yoy):.1%}-enheter sämre än för ett år sedan")
    elif np.isfinite(margin_qoq):
        evidence += 1
        if margin_qoq >= .02:
            score += 7; positive.append("marginalen förbättrades tydligt mot föregående kvartal")
        elif margin_qoq <= -.03:
            score -= 8; negative.append("marginalen försämrades tydligt mot föregående kvartal")

    if np.isfinite(fcf_yoy):
        evidence += 1
        if fcf_yoy >= .20:
            score += 8; positive.append("kvartalets fria kassaflöde har förbättrats tydligt mot förra året")
        elif fcf_yoy <= -.30:
            score -= 10; negative.append("kvartalets fria kassaflöde har försämrats tydligt mot förra året")

    if np.isfinite(earnings_yoy):
        evidence += 1
        if earnings_yoy >= .15:
            score += 6; positive.append("kvartalsvinsten växer tydligt mot förra året")
        elif earnings_yoy <= -.25:
            score -= 8; negative.append("kvartalsvinsten har fallit tydligt mot förra året")

    if np.isfinite(surprise):
        evidence += 1
        if surprise >= .05:
            score += 6; positive.append(f"senaste rapporterade EPS slog estimatet med cirka {surprise:.1%}")
        elif surprise <= -.05:
            score -= 8; negative.append(f"senaste rapporterade EPS missade estimatet med cirka {abs(surprise):.1%}")

    score = float(np.clip(score, 0, 100))
    confidence = float(np.clip(15 + evidence * 12, 0, 100))

    if evidence < 2:
        label = "Otillräcklig förändringsdata"
    elif score >= 72 and len(positive) >= 2:
        label = "Positiv inflektion"
    elif score >= 60 and positive:
        label = "Tidiga förbättringstecken"
    elif score <= 35 and negative:
        label = "Tydlig försämring"
    elif score <= 45 and negative:
        label = "Negativ förändring"
    else:
        label = "Neutral / oklar förändring"

    if positive:
        why_now = positive[0] + "."
        if len(positive) > 1:
            why_now += " Dessutom " + positive[1] + "."
    elif negative:
        why_now = "Inget positivt inflektionscase kan verifieras; " + negative[0] + "."
    else:
        why_now = "Ingen tydlig förändring kan verifieras i tillgängliga kvartals- eller estimatdata."

    return {
        **metrics,
        "Inflection Score": round(score, 1),
        "Inflection Confidence": round(confidence, 1),
        "Inflection Signal": label,
        "Varför nu": why_now,
        "Positiva förändringar": "; ".join(positive[:4]) if positive else "inga tydliga positiva förändringar verifierade",
        "Negativa förändringar": "; ".join(negative[:4]) if negative else "inga tydliga negativa förändringar verifierade",
        "Inflection Evidence Count": evidence,
    }


def apply_inflection_gate(case: dict[str, Any]) -> dict[str, Any]:
    """Let deterioration veto weak long-term cases, but never let hype rescue traps."""
    out = dict(case)
    gate = str(out.get("Djupkontroll", "Otillräcklig data"))
    signal = str(out.get("Inflection Signal", ""))
    eps_change = _num(out.get("EPS-estimat förändring"))

    if gate in {"Avstå tills vidare", "Hög value-trap-risk", "Otillräcklig data"}:
        return out
    if signal == "Tydlig försämring" or (np.isfinite(eps_change) and eps_change <= -.05):
        out["Djupkontroll"] = "Kräver extra kontroll"
        out["Inflection Gate Note"] = "Djupcaset sänktes eftersom färska förändrings-/estimatdata försämrats tydligt."
    elif signal == "Negativ förändring" and gate == "Klarar djupkontroll":
        out["Djupkontroll"] = "Neutral djupkontroll"
        out["Inflection Gate Note"] = "Caset fick lägre prioritet eftersom färska förändringsdata inte stödjer den historiska styrkan."
    return out


def inflection_rank_value(row: dict[str, Any] | pd.Series) -> float:
    """Ranking aid only after the fundamental/value-trap gate has been passed."""
    signal_order = {
        "Positiv inflektion": 5.0,
        "Tidiga förbättringstecken": 4.0,
        "Neutral / oklar förändring": 3.0,
        "Otillräcklig förändringsdata": 2.0,
        "Negativ förändring": 1.0,
        "Tydlig försämring": 0.0,
    }
    return signal_order.get(str(row.get("Inflection Signal", "")), 2.0)
