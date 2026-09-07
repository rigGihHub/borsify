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


def _relative_gap(a: Any, b: Any) -> float:
    x, y = _num(a), _num(b)
    if not (np.isfinite(x) and np.isfinite(y)):
        return np.nan
    scale = max(abs(x), abs(y), 1e-12)
    return float(abs(x - y) / scale)


def _latest_row(frame: Any, names: list[str]) -> float:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return np.nan
    for name in names:
        if name in frame.index:
            series = pd.to_numeric(frame.loc[name], errors="coerce").dropna()
            if not series.empty:
                # Yahoo statement columns are normally newest first, but sort dates
                # where possible so the check remains deterministic.
                try:
                    dated = []
                    for col, val in series.items():
                        ts = pd.to_datetime(col, errors="coerce")
                        if not pd.isna(ts):
                            dated.append((ts, float(val)))
                    if dated:
                        return max(dated, key=lambda x: x[0])[1]
                except Exception:
                    pass
                return float(series.iloc[0])
    return np.nan


def _statement_fcf(cashflow: Any) -> float:
    direct = _latest_row(cashflow, ["Free Cash Flow"])
    if np.isfinite(direct):
        return direct
    ocf = _latest_row(cashflow, ["Operating Cash Flow", "Total Cash From Operating Activities"])
    capex = _latest_row(cashflow, ["Capital Expenditure", "Capital Expenditures"])
    if np.isfinite(ocf) and np.isfinite(capex):
        # Yahoo usually stores capex as negative outflow.
        return float(ocf + capex) if capex <= 0 else float(ocf - capex)
    return np.nan


def assess_fundamental_redundancy(snapshot: dict[str, Any] | pd.Series, raw: dict[str, Any]) -> dict[str, Any]:
    """Cross-check decision-critical fundamentals through independent payload paths.

    This is deliberately *not* labelled independent-source verification: the current
    implementation compares Yahoo's broad quote/info payload, fast_info and statement
    tables. That catches stale/unit/sign inconsistencies without pretending that one
    provider equals source redundancy. A future external/primary-source adapter can
    populate the same evidence contract.
    """
    strengths: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []
    checks = 0

    fast = raw.get("fast_info") if isinstance(raw.get("fast_info"), dict) else {}

    # 1) Price: broad daily history vs fast quote path. Small timing differences are fine.
    broad_price = _num(snapshot.get("Pris"))
    fast_price = _num(fast.get("last_price"))
    gap = _relative_gap(broad_price, fast_price)
    if np.isfinite(gap):
        checks += 1
        if gap <= 0.03:
            strengths.append("kursen stämmer mellan två Yahoo-vägar")
        elif gap <= 0.08:
            warnings.append(f"kursen skiljer {gap:.0%} mellan Yahoo-vägar")
        else:
            blockers.append(f"kursen skiljer {gap:.0%} mellan Yahoo-vägar")

    # 2) Market cap: quote/info vs fast_info. This is a useful scale/unit sanity check.
    broad_mc = _num(snapshot.get("_Raw marketCap"))
    if not np.isfinite(broad_mc):
        local_b = _num(snapshot.get("Börsvärde lokal mdr"))
        broad_mc = local_b * 1e9 if np.isfinite(local_b) else np.nan
    fast_mc = _num(fast.get("market_cap"))
    gap = _relative_gap(broad_mc, fast_mc)
    if np.isfinite(gap):
        checks += 1
        if gap <= 0.12:
            strengths.append("börsvärdet stämmer mellan två Yahoo-vägar")
        elif gap <= 0.35:
            warnings.append(f"börsvärdet skiljer {gap:.0%} mellan Yahoo-vägar")
        else:
            blockers.append(f"börsvärdet skiljer {gap:.0%} mellan Yahoo-vägar")

    # 3) Snapshot TTM/current fields vs latest financial statement. We only hard-stop
    # extreme scale contradictions. Normal TTM-vs-annual changes become warnings.
    pairs = [
        ("fritt kassaflöde", snapshot.get("_Raw freeCashflow"), _statement_fcf(raw.get("cashflow"))),
        ("total skuld", snapshot.get("_Raw totalDebt"), _latest_row(raw.get("balance"), ["Total Debt"])),
        ("omsättning", snapshot.get("_Raw totalRevenue"), _latest_row(raw.get("income"), ["Total Revenue", "Operating Revenue"])),
        ("nettoresultat", snapshot.get("_Raw netIncome"), _latest_row(raw.get("income"), ["Net Income", "Net Income Common Stockholders"])),
    ]
    for label, broad, statement in pairs:
        x, y = _num(broad), _num(statement)
        if not (np.isfinite(x) and np.isfinite(y)):
            continue
        checks += 1
        # Opposite signs are meaningful for earnings/FCF, but can legitimately occur
        # between TTM and latest annual period, so warn rather than veto.
        if label in {"fritt kassaflöde", "nettoresultat"} and x * y < 0:
            warnings.append(f"{label} har olika tecken i aktuell snapshot och senaste årsrapport")
            continue
        gap = _relative_gap(x, y)
        ratio = max(abs(x), abs(y)) / max(min(abs(x), abs(y)), 1e-12)
        if ratio >= 20:
            blockers.append(f"{label} skiljer extremt mycket mellan snapshot och rapport")
        elif np.isfinite(gap) and gap <= 0.35:
            strengths.append(f"{label} är rimligt förenligt mellan snapshot och rapport")
        elif np.isfinite(gap) and gap > 0.70:
            warnings.append(f"{label} skiljer tydligt mellan snapshot och rapport")

    if blockers:
        status = "STOPP – MOTSÄGELSE"
    elif warnings:
        status = "KONTROLLERA"
    elif checks >= 2:
        status = "INTERN KONTROLL OK"
    else:
        status = "FÖR LITE UNDERLAG"

    external = str(raw.get("external_verification_status") or "SAKNAS")
    if external == "VERIFIERAD":
        external_text = "oberoende extern källa verifierad"
    else:
        external_text = "oberoende extern källa är inte verifierad"

    return {
        "Redundans status": status,
        "Redundans kontroller": int(checks),
        "Redundans styrkor": "; ".join(strengths[:5]) if strengths else "inga interna dubbelkontroller verifierade",
        "Redundans varningar": "; ".join(warnings[:5]) if warnings else "inga tydliga interna motsägelser",
        "Redundans stopp": "; ".join(blockers[:4]),
        "Extern verifiering": external,
        "Extern verifiering text": external_text,
        "Redundans metod": "Yahoo quote/info + fast_info + finansiella rapporttabeller; inte oberoende datakällor",
    }
