from __future__ import annotations
"""Prospective validation of early inflection signals.

An early signal is only classified after enough time has elapsed. Confirmation requires
a later signal in the expected chain; a false start requires both maturity and absence
of confirmation. This prevents today's missing data from being called a failure.
"""
import math
from typing import Any
import numpy as np
import pandas as pd

LATER={"business_kpi":{"estimate_revision","report_confirmation","market_reaction"},
       "estimate_revision":{"report_confirmation","market_reaction"}}

def classify_early_signals(events:pd.DataFrame|None, as_of:Any, maturity_days:int=120)->pd.DataFrame:
    cols=["symbol","early_type","early_date","status","confirmation_type","confirmation_date","days_to_confirmation"]
    if events is None or events.empty:return pd.DataFrame(columns=cols)
    d=events.copy()
    d["source_date"]=pd.to_datetime(d["source_date"],errors="coerce")
    d=d.dropna(subset=["source_date"])
    now=pd.Timestamp(as_of).tz_localize(None) if getattr(pd.Timestamp(as_of),"tzinfo",None) else pd.Timestamp(as_of)
    rows=[]
    for _,e in d[d["signal_type"].isin(LATER)].iterrows():
        sym=str(e["symbol"]); typ=str(e["signal_type"]); dt=e["source_date"]
        later=d[(d["symbol"].astype(str)==sym)&(d["signal_type"].isin(LATER[typ]))&(d["source_date"]>dt)].sort_values("source_date")
        age=(now-dt).days
        if not later.empty:
            c=later.iloc[0]; days=int((c["source_date"]-dt).days)
            status="confirmed"
            rows.append({"symbol":sym,"early_type":typ,"early_date":dt.date().isoformat(),"status":status,
                         "confirmation_type":str(c["signal_type"]),"confirmation_date":c["source_date"].date().isoformat(),
                         "days_to_confirmation":days})
        elif age>=maturity_days:
            rows.append({"symbol":sym,"early_type":typ,"early_date":dt.date().isoformat(),"status":"false_start",
                         "confirmation_type":"","confirmation_date":"","days_to_confirmation":np.nan})
        else:
            rows.append({"symbol":sym,"early_type":typ,"early_date":dt.date().isoformat(),"status":"pending",
                         "confirmation_type":"","confirmation_date":"","days_to_confirmation":np.nan})
    return pd.DataFrame(rows,columns=cols)

def summarize_false_starts(classified:pd.DataFrame|None)->dict[str,Any]:
    if classified is None or classified.empty:
        return {"False Start status":"— Historik byggs","False Start mogna":0,"False Start confirmed":0,
                "False Start false":0,"False Start confirmation rate":np.nan,
                "False Start median dagar":np.nan,
                "False Start förklaring":"Inga mogna prospektiva tidiga signaler finns ännu."}
    mature=classified[classified.status.isin(["confirmed","false_start"])]
    pending=int((classified.status=="pending").sum())
    if mature.empty:
        return {"False Start status":"🟡 Tidiga signaler väntar på facit","False Start mogna":0,"False Start confirmed":0,
                "False Start false":0,"False Start confirmation rate":np.nan,"False Start median dagar":np.nan,
                "False Start förklaring":f"{pending} tidiga signaler är ännu inom mognadsfönstret och klassas därför inte som misslyckade."}
    conf=int((mature.status=="confirmed").sum()); false=int((mature.status=="false_start").sum())
    rate=conf/len(mature)
    days=pd.to_numeric(mature.loc[mature.status=="confirmed","days_to_confirmation"],errors="coerce").dropna()
    status="🟢 Tidiga signaler bekräftas ofta" if len(mature)>=5 and rate>=.7 else "⚠️ Många tidiga signaler dör ut" if len(mature)>=5 and rate<.4 else "🟡 För litet facit för slutsats"
    return {"False Start status":status,"False Start mogna":int(len(mature)),"False Start confirmed":conf,
            "False Start false":false,"False Start confirmation rate":rate,
            "False Start median dagar":float(days.median()) if not days.empty else np.nan,
            "False Start förklaring":f"{conf} av {len(mature)} mogna tidiga signaler har följts av ett senare steg i inflection-kedjan. {pending} väntar fortfarande på facit. Bekräftelse är observationsordning, inte bevis på kausalitet."}

def calibration_by_outcome(recommendations:pd.DataFrame|None,outcomes:pd.DataFrame|None,horizon:str)->pd.DataFrame:
    """Realised returns for frozen false-start state. Never rebuilds old classifications."""
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:return pd.DataFrame()
    if "False Start frozen state" not in recommendations.columns:return pd.DataFrame()
    o=outcomes[outcomes["horizon"]==horizon].copy()
    m=o.merge(recommendations[["record_id","False Start frozen state"]],on="record_id",how="left")
    m["return_pct"]=pd.to_numeric(m["return_pct"],errors="coerce")
    m=m.dropna(subset=["return_pct"])
    m=m[m["False Start frozen state"].astype(str).isin(["confirmed","false_start","pending"])]
    rows=[]
    for state,g in m.groupby("False Start frozen state"):
        rows.append({"State":state,"Antal":len(g),"MedianReturn":g.return_pct.median(),
                     "HitRate":(g.return_pct>0).mean(),"Gain10":(g.return_pct>=.10).mean(),
                     "Loss10":(g.return_pct<=-.10).mean()})
    return pd.DataFrame(rows)
