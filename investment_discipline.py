from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


INVESTMENT_DISCIPLINE_SCHEMA_VERSION = 1


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


def _latest(s: pd.Series) -> float:
    return _num(s.iloc[0]) if not s.empty else np.nan


def _growth(s: pd.Series) -> float:
    if len(s) < 2:
        return np.nan
    newest, older = _num(s.iloc[0]), _num(s.iloc[1])
    if not np.isfinite(newest) or not np.isfinite(older) or older <= 0:
        return np.nan
    return newest / older - 1.0


def _cagr(s: pd.Series, max_periods: int = 4) -> float:
    vals = pd.to_numeric(s.iloc[:max_periods], errors="coerce").dropna()
    if len(vals) < 2:
        return np.nan
    newest, oldest = _num(vals.iloc[0]), _num(vals.iloc[-1])
    years = len(vals) - 1
    if newest <= 0 or oldest <= 0 or years <= 0:
        return np.nan
    return (newest / oldest) ** (1 / years) - 1.0


def _ratio(a: pd.Series, b: pd.Series, *, abs_a: bool = False) -> pd.Series:
    if a.empty or b.empty:
        return pd.Series(dtype=float)
    common = a.index.intersection(b.index)
    if not len(common):
        return pd.Series(dtype=float)
    av = pd.to_numeric(a.loc[common], errors="coerce")
    if abs_a:
        av = av.abs()
    bv = pd.to_numeric(b.loc[common], errors="coerce").where(lambda x: x > 0)
    return (av / bv).replace([np.inf, -np.inf], np.nan).dropna().sort_index(ascending=False)


def _trend(s: pd.Series, n: int = 4) -> float:
    vals = pd.to_numeric(s.iloc[:n], errors="coerce").dropna()
    if len(vals) < 2:
        return np.nan
    return _num(vals.iloc[0]) - _num(vals.iloc[-1])


def _sector_profile(sector: Any) -> str:
    text = str(sector or "").lower()
    if any(x in text for x in ("financial", "bank", "insurance", "finans")):
        return "FINANS"
    if any(x in text for x in ("real estate", "reit", "fastighet")):
        return "FASTIGHET"
    if any(x in text for x in ("utilities", "utility", "kraft", "elnät", "energy", "materials", "mining", "råvar")):
        return "KAPITALINTENSIV"
    return "NORMAL"


def build_investment_discipline_metrics(
    income: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    balance: pd.DataFrame | None,
) -> dict[str, Any]:
    """Measure whether growth is becoming more or less capital hungry.

    The module only uses statement data available at analysis time. It intentionally
    avoids estimating ROIC with synthetic tax assumptions. Operating return on assets
    and asset turnover are used as transparent efficiency proxies instead.
    """
    revenue = _find_row(income, ["Total Revenue", "Operating Revenue"])
    operating_income = _find_row(income, ["Operating Income", "EBIT"])
    assets = _find_row(balance, ["Total Assets"])
    capex = _find_row(cashflow, ["Capital Expenditure", "Capital Expenditures"])

    capex_sales = _ratio(capex, revenue, abs_a=True)
    asset_turnover = _ratio(revenue, assets)
    operating_roa = _ratio(operating_income, assets)

    asset_growth = _growth(assets)
    revenue_growth = _growth(revenue)
    growth_gap = asset_growth - revenue_growth if np.isfinite(asset_growth) and np.isfinite(revenue_growth) else np.nan

    return {
        "Investment Discipline schema": INVESTMENT_DISCIPLINE_SCHEMA_VERSION,
        "Tillgångstillväxt senaste": asset_growth,
        "Tillgångstillväxt CAGR": _cagr(assets),
        "Omsättningstillväxt senaste ID": revenue_growth,
        "Tillgångar minus omsättning tillväxtgap": growth_gap,
        "Capex/omsättning senaste": _latest(capex_sales),
        "Capex/omsättning trend": _trend(capex_sales),
        "Kapitalomsättning senaste": _latest(asset_turnover),
        "Kapitalomsättning trend": _trend(asset_turnover),
        "Operativ avkastning/tillgångar senaste": _latest(operating_roa),
        "Operativ avkastning/tillgångar trend": _trend(operating_roa),
        "Investment Discipline år": int(max(len(assets.iloc[:4]), len(revenue.iloc[:4]), len(capex_sales.iloc[:4]))),
    }


def assess_investment_discipline(metrics: dict[str, Any], sector: Any = "") -> dict[str, Any]:
    profile = _sector_profile(sector)
    if profile == "FINANS":
        return {
            **metrics,
            "Kapitaldisciplin status": "BRANSCHMÅTT SAKNAS",
            "Kapitaldisciplin styrkor": "—",
            "Kapitaldisciplin varningar": "Tillgångstillväxt och capex är inte jämförbara kvalitetsmått för bank/finans.",
            "Kapitaldisciplin evidens": 0,
            "Kapitaldisciplin profil": profile,
        }

    asset_growth = _num(metrics.get("Tillgångstillväxt senaste"))
    growth_gap = _num(metrics.get("Tillgångar minus omsättning tillväxtgap"))
    capex_sales = _num(metrics.get("Capex/omsättning senaste"))
    capex_trend = _num(metrics.get("Capex/omsättning trend"))
    turnover_trend = _num(metrics.get("Kapitalomsättning trend"))
    roa = _num(metrics.get("Operativ avkastning/tillgångar senaste"))
    roa_trend = _num(metrics.get("Operativ avkastning/tillgångar trend"))

    evidence = sum(np.isfinite(x) for x in [asset_growth, growth_gap, capex_sales, capex_trend, turnover_trend, roa, roa_trend])
    if evidence < 3:
        return {
            **metrics,
            "Kapitaldisciplin status": "FÖR LITE UNDERLAG",
            "Kapitaldisciplin styrkor": "—",
            "Kapitaldisciplin varningar": "För få rapportserier för att bedöma hur kapitalkrävande tillväxten är.",
            "Kapitaldisciplin evidens": evidence,
            "Kapitaldisciplin profil": profile,
        }

    strengths: list[str] = []
    warnings: list[str] = []
    # Capital-intensive businesses get wider tolerances; the metric should compare
    # direction/efficiency rather than punish the business model itself.
    gap_warn = 0.20 if profile == "KAPITALINTENSIV" else 0.12
    gap_hard = 0.35 if profile == "KAPITALINTENSIV" else 0.25
    capex_high = 0.30 if profile in {"KAPITALINTENSIV", "FASTIGHET"} else 0.18

    severe = 0
    if np.isfinite(growth_gap):
        if growth_gap >= gap_hard:
            severe += 1
            warnings.append("tillgångarna växer mycket snabbare än omsättningen")
        elif growth_gap >= gap_warn:
            warnings.append("tillgångarna växer snabbare än omsättningen")
        elif growth_gap <= -0.05:
            strengths.append("omsättningen växer utan lika snabb ökning av tillgångarna")

    if np.isfinite(turnover_trend):
        if turnover_trend <= -0.20:
            severe += 1
            warnings.append("kapitalomsättningen försämras tydligt")
        elif turnover_trend <= -0.08:
            warnings.append("kapitalomsättningen försämras")
        elif turnover_trend >= 0.08:
            strengths.append("kapitalomsättningen förbättras")

    if np.isfinite(roa_trend):
        if roa_trend <= -0.04:
            severe += 1
            warnings.append("operativ avkastning på tillgångarna faller")
        elif roa_trend >= 0.025:
            strengths.append("operativ avkastning på tillgångarna förbättras")

    if np.isfinite(capex_sales) and np.isfinite(capex_trend):
        if capex_sales >= capex_high and capex_trend >= 0.08:
            warnings.append("investeringarna tar en växande andel av omsättningen")
        elif capex_trend <= -0.05 and (not np.isfinite(turnover_trend) or turnover_trend >= -0.05):
            strengths.append("investeringsbehovet minskar relativt omsättningen")

    if severe >= 2:
        status = "KAPITALBINDNING ÖKAR"
    elif warnings:
        status = "KRÄVER KONTROLL"
    elif len(strengths) >= 2:
        status = "EFFEKTIV KAPITALANVÄNDNING"
    else:
        status = "BALANSERAD"

    return {
        **metrics,
        "Kapitaldisciplin status": status,
        "Kapitaldisciplin styrkor": "; ".join(strengths) if strengths else "inga tydliga styrkesignaler",
        "Kapitaldisciplin varningar": "; ".join(warnings) if warnings else "inga tydliga varningssignaler",
        "Kapitaldisciplin evidens": evidence,
        "Kapitaldisciplin profil": profile,
    }


def apply_investment_discipline_gate(case: dict[str, Any]) -> dict[str, Any]:
    """Add a caution for severe capital inefficiency, but never create a hard veto alone."""
    result = dict(case)
    if str(result.get("Kapitaldisciplin status", "")) == "KAPITALBINDNING ÖKAR":
        existing = str(result.get("Fleråriga varningar", "") or "").strip()
        msg = "tillväxten ser mer kapitalkrävande ut"
        if msg not in existing.lower():
            result["Fleråriga varningar"] = "; ".join(x for x in [existing, msg] if x)
    return result
