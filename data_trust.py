from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd


def _num(v: Any) -> float:
    try:
        x=float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _age_days(value: Any) -> float:
    if value is None or str(value).strip() in {"","—","nan","None"}:
        return np.nan
    try:
        ts=pd.Timestamp(value)
        if ts.tzinfo is not None:
            ts=ts.tz_localize(None)
        now=pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)
        return float(max(0,(now.normalize()-ts.normalize()).days))
    except Exception:
        return np.nan


def assess_data_trust(row: pd.Series | dict[str,Any]) -> dict[str,Any]:
    """Create a compact source/freshness passport for a recommendation.

    This is about trust in the inputs, not expected return.
    """
    qc=str(row.get("Universe QC","") or "")
    coverage=_num(row.get("Datatäckning"))
    price_date=row.get("Prisdatum")
    price_age=_age_days(price_date)
    fundamental_at=str(row.get("Fundamental hämtad","") or "")
    report_date=str(row.get("Rapportdatum","") or "")

    strengths=[]
    warnings=[]
    blockers=[]

    if qc=="VERIFIERAD":
        strengths.append("grundläggande marknadsdata verifierad")
    elif qc=="DELVIS VERIFIERAD":
        warnings.append("marknadsdatan är bara delvis verifierad")
    elif qc=="EXKLUDERA":
        blockers.append("marknadsdatan har underkänts")

    if np.isfinite(price_age):
        if price_age <= 4:
            strengths.append("kursdatum är färskt")
        elif price_age <= 7:
            warnings.append(f"senaste kursen är {int(price_age)} dagar gammal")
        else:
            blockers.append(f"senaste kursen är {int(price_age)} dagar gammal")
    else:
        blockers.append("kursdatum saknas eller kan inte tolkas")

    if np.isfinite(coverage):
        if coverage >= .70:
            strengths.append("god täckning i bolagsdata")
        elif coverage < .50:
            warnings.append("många centrala bolagsuppgifter saknas")
    else:
        warnings.append("datatäckningen kan inte mätas")

    if fundamental_at and fundamental_at not in {"—","None","nan"}:
        strengths.append("bolagsdata har en registrerad hämtningstid")
    else:
        warnings.append("hämtningstid för bolagsdata saknas")

    if report_date and report_date not in {"—","None","nan"}:
        strengths.append("rapportdatum finns för djupanalysen")
        report_status=f"Rapportdatum: {report_date[:10]}"
    else:
        report_status="Rapportdatum: inte verifierat i den breda scanningen"

    if blockers:
        status="STOPP"
    elif warnings:
        status="ANVÄNDBART MED VARNING"
    else:
        status="GOTT UNDERLAG"

    return {
        "Data Trust status":status,
        "Data Trust styrkor":"; ".join(strengths[:4]) if strengths else "inga verifierade styrkor registrerade",
        "Data Trust varningar":"; ".join(warnings[:4]) if warnings else "inga tydliga datavarningar",
        "Data Trust stopp":"; ".join(blockers),
        "Data Trust kursålder dagar":price_age,
        "Data Trust källa":"Yahoo Finance via yfinance",
        "Data Trust kursdatum":str(price_date or "—"),
        "Data Trust bolagsdata hämtad":fundamental_at or "—",
        "Data Trust rapportstatus":report_status,
    }


def add_data_trust(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    records=[assess_data_trust(r) for _,r in out.iterrows()]
    trust=pd.DataFrame(records,index=out.index)
    overlap=[c for c in trust.columns if c in out.columns]
    if overlap:
        out=out.drop(columns=overlap)
    return out.join(trust)
