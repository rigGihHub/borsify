from __future__ import annotations
"""Transparent data-source health for each analysed stock.

This layer never turns missing data into neutral evidence. It reports which analysis
families are weakened or blocked by unavailable/stale inputs.
"""
import math
from typing import Any
import numpy as np
import pandas as pd

def _present(v:Any)->bool:
    return v is not None and str(v).strip() not in {"","—","nan","None","NaT"}

def _num(v:Any)->float:
    try:
        x=float(v); return x if math.isfinite(x) else np.nan
    except Exception:return np.nan

def assess_failure_transparency(row:pd.Series|dict[str,Any])->dict[str,Any]:
    failures=[]; weakened=[]; ok=[]
    trust=str(row.get("Data Trust status") or "")
    if trust=="STOPP": failures.append(str(row.get("Data Trust stopp") or "marknadsdata underkänd"))
    elif trust=="ANVÄNDBART MED VARNING": weakened.append(str(row.get("Data Trust varningar") or "datavarning"))
    elif trust=="GOTT UNDERLAG": ok.append("grundläggande marknads-/bolagsdata")

    if _present(row.get("Deep fetch error")):
        failures.append("djupdata: "+str(row.get("Deep fetch error")))
        weakened.extend(["KPI-inflection","rapport-/estimatdjupanalys"])
    if bool(row.get("Deep source circuit open")):
        failures.append("djupkälla circuit breaker är öppen")
        weakened.extend(["KPI-inflection","rapport-/estimatdjupanalys"])
    if str(row.get("Deep source status") or "") in {"PARTIAL","DEGRADED","ERROR","CIRCUIT_OPEN"}:
        details=str(row.get("Deep source errors") or "").strip()
        missing=str(row.get("Deep source missing") or "").strip()
        weakened.append("djupkälla: "+("; ".join(x for x in [details, missing] if x) or str(row.get("Deep source status"))))

    fundamental_status=str(row.get("Fundamental source status") or "")
    fundamental_errors=str(row.get("Fundamental source errors") or "")
    fundamental_circuit=bool(row.get("Fundamental circuit open"))
    if fundamental_circuit:
        failures.append("fundamental källa circuit breaker är öppen")
        weakened.extend(["värdering","kvalitet","fundamental bolagsanalys"])
    if fundamental_status=="ERROR":
        failures.append("fundamental källa misslyckades"+(": "+fundamental_errors if fundamental_errors else ""))
        weakened.extend(["värdering","kvalitet","fundamental bolagsanalys"])
    elif fundamental_status=="PARTIAL":
        weakened.append("fundamental källa partiell"+(": "+fundamental_errors if fundamental_errors else ""))

    coverage=_num(row.get("Datatäckning"))
    if np.isfinite(coverage) and coverage<.50:
        weakened.append(f"fundamental analys: endast {coverage:.0%} kärnfält")
    if not _present(row.get("Rapportdatum")) and not _present(row.get("Rapportminne rapportdatum")):
        weakened.append("rapportanalys: verifierat rapportdatum saknas")
    if not _present(row.get("KPI-specifika observerade")):
        gaps=str(row.get("KPI-specifika saknas") or "")
        if gaps: weakened.append("bransch-KPI: "+gaps)
    else: ok.append("minst ett branschspecifikt KPI-spår")
    if not _present(row.get("Fundamental hämtad")):
        weakened.append("fundamental färskhet: hämtningstid saknas")
    else: ok.append("fundamental hämtningstid")

    # Explicitly distinguish unavailable from failed.
    if failures: status="🔴 DATAFEL / BLOCKERAD ANALYS"
    elif weakened: status="🟡 DELVIS FÖRSVAGAD ANALYS"
    else: status="🟢 DATAUNDERLAG OK"
    unique=lambda xs:list(dict.fromkeys(x for x in xs if x))
    failures, weakened, ok=map(unique,(failures,weakened,ok))
    confidence_penalty=min(60,25*len(failures)+8*len(weakened))
    return {
        "Data Failure status":status,
        "Data Failure blockerare":"; ".join(failures),
        "Data Failure försvagat":"; ".join(weakened),
        "Data Failure fungerande":"; ".join(ok),
        "Data Failure penalty":confidence_penalty,
        "Data Failure förklaring":(
            ("Blockerare: "+"; ".join(failures)+". " if failures else "")+
            ("Försvagade analyser: "+"; ".join(weakened)+". " if weakened else "")+
            ("Fungerande underlag: "+"; ".join(ok)+"." if ok else "")
        ).strip()
    }

def add_failure_transparency(df:pd.DataFrame)->pd.DataFrame:
    if df is None or df.empty:return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy(); x=pd.DataFrame([assess_failure_transparency(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in x if c in out.columns]
    if overlap:out=out.drop(columns=overlap)
    return out.join(x)
