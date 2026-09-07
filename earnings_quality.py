from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


EARNINGS_QUALITY_SCHEMA_VERSION = 2


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _find_row(frame: pd.DataFrame | None, names: list[str]) -> pd.Series:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(dtype=float)
    for name in names:
        if name in frame.index:
            s = pd.to_numeric(frame.loc[name], errors="coerce").dropna()
            if not s.empty:
                try:
                    s.index = pd.to_datetime(s.index)
                    return s.sort_index(ascending=False)
                except Exception:
                    return s
    return pd.Series(dtype=float)


def _ratio(a: pd.Series, b: pd.Series, *, positive_denominator: bool = False) -> pd.Series:
    if a.empty or b.empty:
        return pd.Series(dtype=float)
    common = a.index.intersection(b.index)
    if len(common) == 0:
        return pd.Series(dtype=float)
    av = pd.to_numeric(a.loc[common], errors="coerce")
    bv = pd.to_numeric(b.loc[common], errors="coerce")
    if positive_denominator:
        bv = bv.where(bv > 0)
    out = av / bv.replace(0, np.nan)
    return out.replace([np.inf, -np.inf], np.nan).dropna().sort_index(ascending=False)


def _latest(s: pd.Series) -> float:
    return _num(s.iloc[0]) if not s.empty else np.nan


def _median_recent(s: pd.Series, n: int = 4) -> float:
    if s.empty:
        return np.nan
    vals = pd.to_numeric(s.iloc[:n], errors="coerce").dropna()
    return float(vals.median()) if len(vals) else np.nan


def _trend(series: pd.Series, n: int = 4) -> float:
    if len(series) < 2:
        return np.nan
    s = pd.to_numeric(series.iloc[:n], errors="coerce").dropna()
    if len(s) < 2:
        return np.nan
    return _num(s.iloc[0]) - _num(s.iloc[-1])


def _latest_growth(series: pd.Series) -> float:
    """Latest annual growth; missing/non-meaningful base stays missing."""
    if len(series) < 2:
        return np.nan
    latest = _num(series.iloc[0])
    previous = _num(series.iloc[1])
    if not np.isfinite(latest) or not np.isfinite(previous) or abs(previous) < 1e-12:
        return np.nan
    # Growth from a negative base is hard to interpret as a percentage and is
    # deliberately not used for the earnings-vs-cash divergence diagnostic.
    if previous <= 0:
        return np.nan
    return latest / previous - 1.0


def _positive_share(series: pd.Series, n: int = 4) -> float:
    if series.empty:
        return np.nan
    vals = pd.to_numeric(series.iloc[:n], errors="coerce").dropna()
    if not len(vals):
        return np.nan
    return float((vals > 0).mean())


def _cash_flow_accrual_ratio(net_income: pd.Series, ocf: pd.Series, total_assets: pd.Series) -> pd.Series:
    """Cash-flow accruals = (net income - operating cash flow) / average assets.

    This is a compact cash-flow version of accrual quality. Positive values mean
    accounting earnings exceed cash from operations. We only compute periods where
    average assets are positive. No current data is used to fill historical gaps.
    """
    if net_income.empty or ocf.empty or total_assets.empty:
        return pd.Series(dtype=float)
    common = net_income.index.intersection(ocf.index).intersection(total_assets.index)
    if len(common) < 2:
        return pd.Series(dtype=float)
    dates = sorted(common, reverse=True)
    out: dict[pd.Timestamp, float] = {}
    for i, date in enumerate(dates[:-1]):
        older = dates[i + 1]
        ni = _num(net_income.loc[date])
        cash = _num(ocf.loc[date])
        a_now = _num(total_assets.loc[date])
        a_old = _num(total_assets.loc[older])
        avg_assets = np.nanmean([a_now, a_old]) if np.isfinite(a_now) and np.isfinite(a_old) else np.nan
        if np.isfinite(ni) and np.isfinite(cash) and np.isfinite(avg_assets) and avg_assets > 0:
            out[pd.Timestamp(date)] = (ni - cash) / avg_assets
    if not out:
        return pd.Series(dtype=float)
    return pd.Series(out, dtype=float).sort_index(ascending=False)


def build_earnings_quality_metrics(
    income: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    balance: pd.DataFrame | None,
) -> dict[str, Any]:
    """Earnings Quality 2.0: test whether reported profit is backed by cash.

    Uses only reported statement rows available at analysis time. Missing rows stay
    missing. The diagnostics are descriptive evidence, not a return forecast.
    """
    net_income = _find_row(income, ["Net Income", "Net Income Common Stockholders"])
    revenue = _find_row(income, ["Total Revenue", "Operating Revenue"])
    ocf = _find_row(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    fcf = _find_row(cashflow, ["Free Cash Flow"])
    if fcf.empty:
        capex = _find_row(cashflow, ["Capital Expenditure", "Capital Expenditures"])
        if not ocf.empty and not capex.empty:
            common = ocf.index.intersection(capex.index)
            cap = capex.loc[common]
            fcf = (ocf.loc[common] + cap.where(cap <= 0, -cap)).dropna().sort_index(ascending=False)

    change_wc = _find_row(cashflow, ["Change In Working Capital", "Change To Working Capital"])
    receivables = _find_row(balance, ["Accounts Receivable", "Receivables", "Net Receivables"])
    inventory = _find_row(balance, ["Inventory", "Inventories"])
    total_assets = _find_row(balance, ["Total Assets"])

    # Cash conversion ratios are only meaningful when reported net income is positive.
    ocf_to_income = _ratio(ocf, net_income, positive_denominator=True)
    fcf_to_income = _ratio(fcf, net_income, positive_denominator=True)
    receivables_to_sales = _ratio(receivables, revenue, positive_denominator=True)
    inventory_to_sales = _ratio(inventory, revenue, positive_denominator=True)

    wc_to_ocf = _ratio(change_wc.abs(), ocf.abs(), positive_denominator=True)
    accrual_ratio = _cash_flow_accrual_ratio(net_income, ocf, total_assets)

    ni_growth = _latest_growth(net_income)
    ocf_growth = _latest_growth(ocf)
    profit_cash_growth_gap = ni_growth - ocf_growth if np.isfinite(ni_growth) and np.isfinite(ocf_growth) else np.nan

    return {
        "Earnings Quality schema": EARNINGS_QUALITY_SCHEMA_VERSION,
        "Kassaflöde/vinst senaste": _latest(ocf_to_income),
        "Kassaflöde/vinst median": _median_recent(ocf_to_income),
        "Kassaflöde/vinst trend": _trend(ocf_to_income),
        "FCF/vinst senaste": _latest(fcf_to_income),
        "FCF/vinst median": _median_recent(fcf_to_income),
        "Rörelsekapital senaste förändring": _latest(change_wc),
        "Rörelsekapitalpåverkan/OCF": _latest(wc_to_ocf),
        "Kundfordringar/omsättning": _latest(receivables_to_sales),
        "Kundfordringar/omsättning trend": _trend(receivables_to_sales),
        "Lager/omsättning": _latest(inventory_to_sales),
        "Lager/omsättning trend": _trend(inventory_to_sales),
        "Accruals/tillgångar senaste": _latest(accrual_ratio),
        "Accruals/tillgångar median": _median_recent(accrual_ratio),
        "Vinsttillväxt senaste": ni_growth,
        "OCF-tillväxt senaste": ocf_growth,
        "Vinst minus OCF tillväxtgap": profit_cash_growth_gap,
        "Positivt OCF andel": _positive_share(ocf),
        "Positivt FCF andel": _positive_share(fcf),
        "Earnings Quality år": int(max(len(ocf_to_income.iloc[:4]), len(fcf_to_income.iloc[:4]), len(accrual_ratio.iloc[:4]))),
    }


def assess_earnings_quality(metrics: dict[str, Any]) -> dict[str, Any]:
    positives: list[str] = []
    warnings: list[str] = []
    hard: list[str] = []

    ocf_latest = _num(metrics.get("Kassaflöde/vinst senaste"))
    ocf_med = _num(metrics.get("Kassaflöde/vinst median"))
    ocf_trend = _num(metrics.get("Kassaflöde/vinst trend"))
    fcf_latest = _num(metrics.get("FCF/vinst senaste"))
    fcf_med = _num(metrics.get("FCF/vinst median"))
    wc_impact = _num(metrics.get("Rörelsekapitalpåverkan/OCF"))
    recv_trend = _num(metrics.get("Kundfordringar/omsättning trend"))
    inv_trend = _num(metrics.get("Lager/omsättning trend"))
    accrual_latest = _num(metrics.get("Accruals/tillgångar senaste"))
    accrual_med = _num(metrics.get("Accruals/tillgångar median"))
    growth_gap = _num(metrics.get("Vinst minus OCF tillväxtgap"))
    positive_ocf_share = _num(metrics.get("Positivt OCF andel"))
    positive_fcf_share = _num(metrics.get("Positivt FCF andel"))
    years_val = _num(metrics.get("Earnings Quality år"))
    years = int(years_val if np.isfinite(years_val) else 0)

    evidence_values = [
        ocf_latest, ocf_med, fcf_latest, fcf_med, wc_impact, recv_trend, inv_trend,
        accrual_latest, accrual_med, growth_gap, positive_ocf_share, positive_fcf_share,
    ]
    evidence = sum(np.isfinite(x) for x in evidence_values)

    score = 50.0
    if np.isfinite(ocf_med):
        if ocf_med >= 1.0:
            score += 14
            positives.append("redovisad vinst stöds väl av pengar från den löpande verksamheten")
        elif ocf_med < 0.65:
            score -= 18
            warnings.append("den redovisade vinsten har omvandlats svagt till kassaflöde")
    if np.isfinite(fcf_med):
        if fcf_med >= 0.75:
            score += 10
            positives.append("en stor del av vinsten har även blivit fritt kassaflöde")
        elif fcf_med < 0.35:
            score -= 14
            warnings.append("lite av vinsten har blivit fritt kassaflöde efter investeringar")

    # A single recent collapse matters even when the multi-year median looks good.
    if np.isfinite(ocf_latest) and ocf_latest < 0.45:
        score -= 11
        warnings.append("senaste året visar ovanligt svag omvandling från vinst till kassaflöde")
    if np.isfinite(fcf_latest) and fcf_latest < 0:
        score -= 18
        warnings.append("senaste fria kassaflödet är negativt trots redovisad vinst")
        hard.append("negativt fritt kassaflöde trots redovisad vinst")

    # Earnings Quality 2.0: cash-flow accruals. High positive accruals mean more
    # accounting earnings are not showing up in operating cash flow.
    if np.isfinite(accrual_med):
        if accrual_med <= -0.02:
            score += 8
            positives.append("vinsten har i flera år varit försiktigare än kassaflödet")
        elif accrual_med >= 0.10:
            score -= 15
            warnings.append("en ovanligt stor del av vinsten saknar stöd i operativt kassaflöde")
        elif accrual_med >= 0.06:
            score -= 8
            warnings.append("en förhöjd del av vinsten saknar stöd i operativt kassaflöde")
    if np.isfinite(accrual_latest) and accrual_latest >= 0.15:
        score -= 10
        warnings.append("senaste året har ett stort gap mellan redovisad vinst och operativt kassaflöde")

    # Profit growth that materially outruns operating cash growth is a warning,
    # but never a hard veto by itself because working-capital timing can be temporary.
    if np.isfinite(growth_gap):
        if growth_gap >= 0.30:
            score -= 10
            warnings.append("vinsten växer klart snabbare än kassaflödet")
        elif growth_gap <= -0.20:
            score += 4
            positives.append("kassaflödet utvecklas minst lika starkt som vinsten")

    if np.isfinite(ocf_trend):
        if ocf_trend <= -0.45:
            score -= 7
            warnings.append("omvandlingen från vinst till kassaflöde har försämrats tydligt")
        elif ocf_trend >= 0.35:
            score += 3
            positives.append("omvandlingen från vinst till kassaflöde har förbättrats")

    if np.isfinite(wc_impact) and wc_impact > 0.45:
        score -= 7
        warnings.append("förändringar i rörelsekapitalet har haft stor påverkan på kassaflödet")

    if np.isfinite(recv_trend):
        if recv_trend > 0.05:
            score -= 8
            warnings.append("kundfordringar har vuxit snabbare än omsättningen")
        elif recv_trend < -0.03:
            score += 3
            positives.append("kundfordringar har inte dragit iväg relativt omsättningen")

    if np.isfinite(inv_trend):
        if inv_trend > 0.05:
            score -= 6
            warnings.append("lagret har vuxit snabbare än omsättningen")
        elif inv_trend < -0.03:
            score += 2
            positives.append("lagret har minskat relativt omsättningen")

    if np.isfinite(positive_ocf_share):
        if positive_ocf_share >= 1.0:
            score += 4
            positives.append("operativt kassaflöde har varit positivt varje tillgängligt år")
        elif positive_ocf_share < 0.5:
            score -= 8
            warnings.append("operativt kassaflöde har ofta varit negativt")
    if np.isfinite(positive_fcf_share) and positive_fcf_share < 0.5:
        score -= 6
        warnings.append("fritt kassaflöde har ofta varit negativt")

    score = float(np.clip(score, 0, 100))

    if evidence < 2 or years < 2:
        status = "FÖR LITE UNDERLAG"
    elif hard or score < 35:
        status = "SVAG VINSTKVALITET"
    elif score < 55:
        status = "KRÄVER KONTROLL"
    elif score >= 72:
        status = "STARK VINSTKVALITET"
    else:
        status = "NORMAL VINSTKVALITET"

    if not np.isfinite(accrual_latest) and not np.isfinite(accrual_med):
        accrual_status = "FÖR LITE UNDERLAG"
    elif (np.isfinite(accrual_latest) and accrual_latest >= 0.15) or (np.isfinite(accrual_med) and accrual_med >= 0.10):
        accrual_status = "FÖRHÖJD RISK"
    elif np.isfinite(accrual_med) and accrual_med <= -0.02:
        accrual_status = "STARKT KASSASTÖD"
    else:
        accrual_status = "NORMALT"

    return {
        **metrics,
        "Vinstkvalitet": round(score, 1),
        "Vinstkvalitet status": status,
        "Vinstkvalitet underlag": int(evidence),
        "Vinstkvalitet styrkor": "; ".join(positives[:4]) if positives else "inga tydliga positiva kassaflödessignaler",
        "Vinstkvalitet varningar": "; ".join(warnings[:4]) if warnings else "inga tydliga varningssignaler i tillgängliga data",
        "Vinstkvalitet hårt stopp": "; ".join(hard),
        "Periodiseringsrisk status": accrual_status,
        "Periodiseringsrisk förklaring": (
            "Jämför redovisad vinst med operativt kassaflöde, skalat mot bolagets tillgångar. "
            "Högt positivt värde betyder att mer av vinsten ännu inte syns som pengar i verksamheten."
        ),
    }


def apply_earnings_quality_gate(case: dict[str, Any]) -> dict[str, Any]:
    out = dict(case)
    status = str(out.get("Vinstkvalitet status", ""))
    gate = str(out.get("Djupkontroll", ""))
    if status == "SVAG VINSTKVALITET" and gate in {"Klarar djupkontroll", "Neutral djupkontroll"}:
        out["Djupkontroll"] = "Kräver extra kontroll"
        out["Vinstkvalitet gate note"] = "Djupcaset sänktes eftersom redovisad vinst inte stöds tillräckligt väl av kassaflödet."
    else:
        out["Vinstkvalitet gate note"] = ""
    return out
