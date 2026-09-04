from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd


def _frame_present(value: Any) -> bool:
    return isinstance(value, pd.DataFrame) and not value.empty


def _latest_date(*frames: pd.DataFrame | None) -> pd.Timestamp | None:
    dates: list[pd.Timestamp] = []
    for frame in frames:
        if not _frame_present(frame):
            continue
        for col in frame.columns:
            ts = pd.to_datetime(col, errors="coerce")
            if not pd.isna(ts):
                if getattr(ts, "tzinfo", None) is not None:
                    ts = ts.tz_localize(None)
                dates.append(ts)
    return max(dates) if dates else None


def _age_days(ts: pd.Timestamp | None, now: Any = None) -> float:
    if ts is None:
        return np.nan
    current = pd.Timestamp(now) if now is not None else pd.Timestamp(datetime.now(timezone.utc))
    if current.tzinfo is not None:
        current = current.tz_localize(None)
    return float(max(0, (current.normalize() - ts.normalize()).days))


def assess_fundamental_data_confidence(
    raw: dict[str, Any],
    assessment: dict[str, Any] | None = None,
    now: Any = None,
) -> dict[str, Any]:
    """Judge whether the fundamental inputs are current and complete enough.

    This is a data-quality gate, not an investment score. It deliberately looks at
    independently observable properties of the Yahoo statement payload: whether
    core statements exist, whether quarterly evidence exists, and how old the most
    recent verifiable statement date is. Missing data is never inferred.
    """
    assessment = assessment or {}
    income = raw.get("income")
    cashflow = raw.get("cashflow")
    balance = raw.get("balance")
    q_income = raw.get("quarterly_income")
    q_cashflow = raw.get("quarterly_cashflow")
    q_balance = raw.get("quarterly_balance")

    annual_present = {
        "resultaträkning": _frame_present(income),
        "kassaflöde": _frame_present(cashflow),
        "balansräkning": _frame_present(balance),
    }
    quarterly_present = {
        "kvartalsresultat": _frame_present(q_income),
        "kvartalskassaflöde": _frame_present(q_cashflow),
        "kvartalsbalans": _frame_present(q_balance),
    }
    annual_count = sum(annual_present.values())
    quarterly_count = sum(quarterly_present.values())

    annual_date = _latest_date(income, cashflow, balance)
    quarterly_date = _latest_date(q_income, q_cashflow, q_balance)
    latest_date = max([x for x in (annual_date, quarterly_date) if x is not None], default=None)
    age = _age_days(latest_date, now=now)

    strengths: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []

    if annual_count == 3:
        strengths.append("resultat, kassaflöde och balans finns")
    elif annual_count == 2:
        warnings.append("en av de tre centrala årsrapporterna saknas")
    else:
        blockers.append("minst två centrala årsrapporter saknas")

    if quarterly_count >= 2:
        strengths.append("färska kvartalsserier finns i flera rapportdelar")
    elif quarterly_count == 1:
        warnings.append("kvartalsunderlaget finns bara i en rapportdel")
    else:
        warnings.append("verifierbara kvartalsserier saknas")

    if np.isfinite(age):
        if age <= 150:
            strengths.append(f"senaste verifierbara rapportperiod är {int(age)} dagar gammal")
        elif age <= 220:
            warnings.append(f"senaste verifierbara rapportperiod är {int(age)} dagar gammal")
        else:
            blockers.append(f"senaste verifierbara rapportperiod är {int(age)} dagar gammal")
    else:
        blockers.append("datum för senaste finansiella rapportperiod kan inte verifieras")

    deep_conf = pd.to_numeric(assessment.get("Deep Confidence"), errors="coerce")
    if pd.notna(deep_conf):
        if float(deep_conf) >= 65:
            strengths.append("djupanalysen har god datatäckning")
        elif float(deep_conf) < 50:
            blockers.append("djupanalysen har för låg datatäckning")
        else:
            warnings.append("djupanalysens datatäckning är begränsad")

    # A single missing quarterly frame should not veto a case when current data is
    # otherwise verifiable. Hard stops are reserved for stale/unverifiable dates,
    # very incomplete annual statements, or already weak deep-data coverage.
    if blockers:
        status = "STOPP"
    elif warnings:
        status = "ANVÄNDBART MED VARNING"
    else:
        status = "STARKT UNDERLAG"

    return {
        "Fundamental Data status": status,
        "Fundamental Data stopp": "; ".join(blockers),
        "Fundamental Data varningar": "; ".join(warnings[:4]) if warnings else "inga tydliga datavarningar",
        "Fundamental Data styrkor": "; ".join(strengths[:4]) if strengths else "inga verifierade styrkor registrerade",
        "Fundamental Data senaste rapportperiod": latest_date.date().isoformat() if latest_date is not None else "—",
        "Fundamental Data rapportålder dagar": age,
        "Fundamental Data årsrapporter": int(annual_count),
        "Fundamental Data kvartalsrapporter": int(quarterly_count),
    }
