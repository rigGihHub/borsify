from __future__ import annotations

from dataclasses import dataclass
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
            if not s.empty:
                try:
                    s.index = pd.to_datetime(s.index, errors="coerce")
                    s = s[~s.index.isna()].sort_index(ascending=False)
                except Exception:
                    pass
                return s.astype(float)
    return pd.Series(dtype=float)


def _latest(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    return _num(s.iloc[0]) if not s.empty else np.nan


def _oldest(series: pd.Series, max_points: int = 4) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna().iloc[:max_points]
    return _num(s.iloc[-1]) if len(s) >= 2 else np.nan


def _change(series: pd.Series, max_points: int = 4) -> float:
    latest, old = _latest(series), _oldest(series, max_points)
    if np.isfinite(latest) and np.isfinite(old) and old != 0:
        return latest / old - 1
    return np.nan


def _cagr(series: pd.Series, max_points: int = 4) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna().iloc[:max_points]
    if len(s) < 2:
        return np.nan
    latest, old = _num(s.iloc[0]), _num(s.iloc[-1])
    periods = len(s) - 1
    if periods <= 0 or not (np.isfinite(latest) and np.isfinite(old)) or latest <= 0 or old <= 0:
        return np.nan
    return (latest / old) ** (1 / periods) - 1


def _positive_share(series: pd.Series, max_points: int = 4) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna().iloc[:max_points]
    if s.empty:
        return np.nan
    return float((s > 0).mean())


def _ratio_series(numer: pd.Series, denom: pd.Series) -> pd.Series:
    if numer.empty or denom.empty:
        return pd.Series(dtype=float)
    n = pd.to_numeric(numer, errors="coerce")
    d = pd.to_numeric(denom, errors="coerce")
    common = n.index.intersection(d.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    d2 = d.loc[common].replace(0, np.nan)
    return (n.loc[common] / d2).replace([np.inf, -np.inf], np.nan).dropna().sort_index(ascending=False)


def _latest_statement_date(*frames: pd.DataFrame | None) -> str:
    dates: list[pd.Timestamp] = []
    for frame in frames:
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            for col in frame.columns:
                ts = pd.to_datetime(col, errors="coerce")
                if not pd.isna(ts):
                    dates.append(ts)
    return max(dates).date().isoformat() if dates else "—"


def build_deep_metrics(
    income: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    balance: pd.DataFrame | None,
) -> dict[str, Any]:
    """Extract a conservative multi-year evidence set from Yahoo statements.

    The function intentionally returns missing values rather than inferring figures.
    It is pure so it can be unit-tested without network access.
    """
    revenue = _find_row(income, ["Total Revenue", "Operating Revenue"])
    net_income = _find_row(income, ["Net Income", "Net Income Common Stockholders"])
    operating_income = _find_row(income, ["Operating Income", "EBIT"])
    fcf = _find_row(cashflow, ["Free Cash Flow"])
    if fcf.empty:
        ocf = _find_row(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
        capex = _find_row(cashflow, ["Capital Expenditure", "Capital Expenditures"])
        if not ocf.empty and not capex.empty:
            common = ocf.index.intersection(capex.index)
            if len(common):
                # Yahoo normally stores capex as a negative outflow. If positive, subtract it.
                cap = capex.loc[common]
                fcf = ocf.loc[common] + cap.where(cap <= 0, -cap)
                fcf = fcf.dropna().sort_index(ascending=False)
    total_debt = _find_row(balance, ["Total Debt"])
    cash = _find_row(balance, ["Cash Cash Equivalents And Short Term Investments", "Cash And Cash Equivalents", "Cash"])

    op_margin = _ratio_series(operating_income, revenue)
    fcf_margin = _ratio_series(fcf, revenue)
    net_margin = _ratio_series(net_income, revenue)

    years = int(max(len(revenue.iloc[:4]), len(net_income.iloc[:4]), len(fcf.iloc[:4])))
    latest_debt, latest_cash = _latest(total_debt), _latest(cash)
    net_debt = latest_debt - latest_cash if np.isfinite(latest_debt) and np.isfinite(latest_cash) else np.nan

    return {
        "Historik år": years,
        "Rapportdatum": _latest_statement_date(income, cashflow, balance),
        "Omsättning CAGR": _cagr(revenue),
        "Vinst CAGR": _cagr(net_income),
        "FCF CAGR": _cagr(fcf),
        "Omsättningsförändring": _change(revenue),
        "Vinstförändring": _change(net_income),
        "FCF-förändring": _change(fcf),
        "Rörelsemarginal": _latest(op_margin),
        "Rörelsemarginal trend": _latest(op_margin) - _oldest(op_margin) if len(op_margin) >= 2 else np.nan,
        "Nettomarginal trend": _latest(net_margin) - _oldest(net_margin) if len(net_margin) >= 2 else np.nan,
        "FCF-marginal": _latest(fcf_margin),
        "FCF-marginal trend": _latest(fcf_margin) - _oldest(fcf_margin) if len(fcf_margin) >= 2 else np.nan,
        "Skuldförändring": _change(total_debt),
        "Nettoskuld": net_debt,
        "Positiv FCF-andel": _positive_share(fcf),
        "Positiv vinst-andel": _positive_share(net_income),
        "Senaste FCF": _latest(fcf),
        "Senaste vinst": _latest(net_income),
    }


def value_trap_risk(metrics: dict[str, Any], snapshot: dict[str, Any] | pd.Series) -> tuple[float, list[str]]:
    """Rule-based 0–100 risk indicator. Higher means more evidence of a value trap.

    Points are transparent red flags, not a probabilistic forecast.
    """
    reasons: list[str] = []
    points = 0.0

    fcf = _num(metrics.get("Senaste FCF"))
    fcf_share = _num(metrics.get("Positiv FCF-andel"))
    rev_cagr = _num(metrics.get("Omsättning CAGR"))
    earnings_change = _num(metrics.get("Vinstförändring"))
    fcf_change = _num(metrics.get("FCF-förändring"))
    margin_trend = _num(metrics.get("Rörelsemarginal trend"))
    if not np.isfinite(margin_trend):
        margin_trend = _num(metrics.get("Nettomarginal trend"))
    debt_change = _num(metrics.get("Skuldförändring"))
    debt_equity = _num(snapshot.get("Skuld/eget kapital"))
    current_margin = _num(snapshot.get("Vinstmarginal"))
    current_roe = _num(snapshot.get("ROE"))

    if np.isfinite(fcf) and fcf < 0:
        points += 24; reasons.append("senaste fria kassaflödet är negativt")
    if np.isfinite(fcf_share) and fcf_share < .50:
        points += 14; reasons.append("fritt kassaflöde har varit positivt färre än hälften av åren")
    if np.isfinite(rev_cagr) and rev_cagr < -.03:
        points += 14; reasons.append(f"omsättningen krymper ({rev_cagr:+.1%} årlig trend)")
    if np.isfinite(earnings_change) and earnings_change < -.35:
        points += 14; reasons.append("vinsten har försämrats kraftigt över flerårsperioden")
    if np.isfinite(fcf_change) and fcf_change < -.35:
        points += 12; reasons.append("fritt kassaflöde har försämrats kraftigt")
    if np.isfinite(margin_trend) and margin_trend < -.04:
        points += 12; reasons.append(f"marginalen har fallit cirka {abs(margin_trend):.1%}-enheter")
    if np.isfinite(debt_change) and debt_change > .35:
        points += 12; reasons.append("skulden har ökat tydligt")
    if np.isfinite(debt_equity) and debt_equity > 250:
        points += 16; reasons.append("skuldsättningen är hög relativt eget kapital")
    if np.isfinite(current_margin) and current_margin < 0:
        points += 12; reasons.append("nuvarande vinstmarginal är negativ")
    if np.isfinite(current_roe) and current_roe < 0:
        points += 10; reasons.append("nuvarande ROE är negativ")

    return float(min(100, points)), reasons


def evidence_confidence(metrics: dict[str, Any], snapshot: dict[str, Any] | pd.Series) -> tuple[float, list[str]]:
    """How much evidence is available, not how likely the stock is to rise."""
    history_fields = [
        "Omsättning CAGR", "Vinstförändring", "FCF-förändring", "Rörelsemarginal trend",
        "Skuldförändring", "Positiv FCF-andel",
    ]
    current_fields = ["P/E", "Forward P/E", "FCF-yield", "ROE", "Vinstmarginal", "Skuld/eget kapital"]
    hist_available = sum(np.isfinite(_num(metrics.get(k))) for k in history_fields)
    current_available = sum(np.isfinite(_num(snapshot.get(k))) for k in current_fields)
    years = int(_num(metrics.get("Historik år")) if np.isfinite(_num(metrics.get("Historik år"))) else 0)

    # Confidence is deliberately capped when history is thin.
    score = 20 + hist_available * 8 + current_available * 4 + min(years, 4) * 3
    if years < 3:
        score = min(score, 58)
    score = float(np.clip(score, 0, 100))

    notes: list[str] = []
    if years < 3: notes.append("mindre än tre års användbar historik")
    if hist_available < 4: notes.append("flera flerårsserier saknas")
    if current_available < 4: notes.append("flera aktuella fundamentala fält saknas")
    if not notes: notes.append("god täckning i både aktuell snapshot och flerårshistorik")
    return score, notes


def assess_deep_case(metrics: dict[str, Any], snapshot: dict[str, Any] | pd.Series) -> dict[str, Any]:
    trap, trap_reasons = value_trap_risk(metrics, snapshot)
    confidence, confidence_notes = evidence_confidence(metrics, snapshot)

    positives: list[str] = []
    warnings: list[str] = []
    rev = _num(metrics.get("Omsättning CAGR"))
    fcf = _num(metrics.get("FCF CAGR"))
    fcf_change = _num(metrics.get("FCF-förändring"))
    margin = _num(metrics.get("Rörelsemarginal trend"))
    if not np.isfinite(margin): margin = _num(metrics.get("Nettomarginal trend"))
    debt = _num(metrics.get("Skuldförändring"))
    pos_fcf = _num(metrics.get("Positiv FCF-andel"))
    valuation = _num(snapshot.get("Värdering"))

    if np.isfinite(rev) and rev >= .05: positives.append(f"omsättningen har vuxit cirka {rev:.1%} per år")
    if np.isfinite(fcf) and fcf >= .05: positives.append(f"fritt kassaflöde har vuxit cirka {fcf:.1%} per år")
    elif np.isfinite(fcf_change) and fcf_change >= .20: positives.append("fritt kassaflöde har förbättrats tydligt")
    if np.isfinite(margin) and margin >= .02: positives.append(f"marginalen har förbättrats cirka {margin:.1%}-enheter")
    if np.isfinite(debt) and debt <= -.15: positives.append("skulden har minskat tydligt")
    if np.isfinite(pos_fcf) and pos_fcf >= .75: positives.append("fritt kassaflöde har varit positivt de flesta analyserade åren")

    warnings.extend(trap_reasons)
    if np.isfinite(valuation) and valuation < 45:
        warnings.append("värderingen ser inte tydligt billig ut relativt jämförelsegruppen")

    if confidence < 50:
        gate = "Otillräcklig data"
    elif trap >= 70:
        gate = "Avstå tills vidare"
    elif trap >= 45:
        gate = "Hög value-trap-risk"
    elif trap >= 25:
        gate = "Kräver extra kontroll"
    elif positives and valuation >= 55:
        gate = "Klarar djupkontroll"
    else:
        gate = "Neutral djupkontroll"

    why_market_may_be_wrong = "Ingen tydlig flerårig förbättring kan beläggas ännu."
    if positives:
        if np.isfinite(valuation) and valuation >= 60:
            why_market_may_be_wrong = "Värderingen är relativt attraktiv samtidigt som " + positives[0] + "."
        else:
            why_market_may_be_wrong = positives[0].capitalize() + ", men värderingen måste fortfarande motiveras."

    devils = warnings[0] if warnings else "Flerårsdata visar ingen grov röd flagga, men aktuell rapport och konkurrensläge måste fortfarande läsas."

    return {
        **metrics,
        "Value Trap Risk": round(trap, 1),
        "Deep Confidence": round(confidence, 1),
        "Djupkontroll": gate,
        "Fleråriga styrkor": "; ".join(positives[:3]) if positives else "ingen tydlig flerårig styrka verifierad",
        "Fleråriga varningar": "; ".join(warnings[:3]) if warnings else "inga grova flerårsflaggor i tillgängliga data",
        "Varför marknaden kan ha fel": why_market_may_be_wrong,
        "Devil's Advocate": devils,
        "Confidence-notering": "; ".join(confidence_notes),
    }


def deep_rank_key(row: dict[str, Any] | pd.Series) -> tuple[float, float, float, float]:
    """Transparent gate-first ordering, avoiding an unvalidated mega-score."""
    gate_order = {
        "Klarar djupkontroll": 5,
        "Neutral djupkontroll": 4,
        "Kräver extra kontroll": 3,
        "Hög value-trap-risk": 2,
        "Otillräcklig data": 1,
        "Avstå tills vidare": 0,
    }
    gate = gate_order.get(str(row.get("Djupkontroll", "")), 1)
    trap = _num(row.get("Value Trap Risk")); confidence = _num(row.get("Deep Confidence")); invest = _num(row.get("INVEST Score"))
    return (float(gate), -float(trap if np.isfinite(trap) else 100), float(confidence if np.isfinite(confidence) else 0), float(invest if np.isfinite(invest) else 0))
