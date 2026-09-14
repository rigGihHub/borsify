from __future__ import annotations
"""Point-in-time evidence lab for frozen Borsify signals.

The lab is deliberately conservative: it evaluates only values that were frozen in the
recommendation snapshot. It does not reconstruct missing historical signals and it
never changes production weights automatically.
"""
import json, math
from typing import Any
import numpy as np
import pandas as pd

SIGNALS=[
 ("Deal Conviction","Deal Conviction nivå",lambda x:x>=2),
 ("KPI Inflection","KPI Inflection nivå",lambda x:x>=2),
 ("Management execution","Management execution nivå",lambda x:x>=2),
 ("Margin recovery","Margin recovery nivå",lambda x:x>=2),
 ("Revision breadth","Revision breadth nivå",lambda x:x>=2),
 ("Operating leverage","Operating leverage nivå",lambda x:x>=2),
 ("Cash conversion inflection","Cash conversion inflection nivå",lambda x:x>=2),
 ("Hidden inflection","Hidden inflection nivå",lambda x:x>=2),
 ("Mispriced acceleration","Mispriced acceleration nivå",lambda x:x>=2),
 ("Ignored compounder","Ignored compounder nivå",lambda x:x>=2),
 ("Underfollowed Quality","Underfollowed Quality nivå",lambda x:x>=2),
 ("Balance-sheet optionality","Balance-sheet optionality nivå",lambda x:x>=2),
]

def _snap(v:Any)->dict[str,Any]:
    if isinstance(v,dict):return v
    try:return json.loads(v or "{}")
    except Exception:return {}

def build_signal_evidence(recommendations:pd.DataFrame|None,outcomes:pd.DataFrame|None,horizon:str,min_cases:int=8)->pd.DataFrame:
    cols=["Signal","Signal N","Control N","Median signal","Median control","Median edge","Hit signal","Hit control",
          "Gain10 signal","Loss10 signal","Status"]
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:return pd.DataFrame(columns=cols)
    o=outcomes[outcomes["horizon"]==horizon].copy()
    if o.empty:return pd.DataFrame(columns=cols)
    rec=recommendations[["record_id","snapshot_json"]].copy()
    rec["_s"]=rec["snapshot_json"].map(_snap)
    merged=o.merge(rec[["record_id","_s"]],on="record_id",how="inner")
    merged["return_pct"]=pd.to_numeric(merged["return_pct"],errors="coerce")
    merged=merged.dropna(subset=["return_pct"])
    rows=[]
    for name,field,pred in SIGNALS:
        vals=[]
        for s in merged["_s"]:
            try:v=float(s.get(field))
            except Exception:v=np.nan
            vals.append(v)
        v=pd.Series(vals,index=merged.index,dtype=float)
        available=v.notna()
        sig=merged[available & v.map(lambda x: pred(x) if pd.notna(x) else False)]
        ctl=merged[available & ~v.map(lambda x: pred(x) if pd.notna(x) else False)]
        if sig.empty and ctl.empty:continue
        med_s=float(sig.return_pct.median()) if not sig.empty else np.nan
        med_c=float(ctl.return_pct.median()) if not ctl.empty else np.nan
        edge=med_s-med_c if math.isfinite(med_s) and math.isfinite(med_c) else np.nan
        enough=len(sig)>=min_cases and len(ctl)>=min_cases
        if not enough:status="Bygger facit"
        elif edge>.03:status="Lovande · kräver fortsatt prospektiv validering"
        elif edge<-.03:status="Varningssignal · underpresterar kontroll"
        else:status="Ingen tydlig edge"
        rows.append({"Signal":name,"Signal N":len(sig),"Control N":len(ctl),"Median signal":med_s,"Median control":med_c,
                     "Median edge":edge,"Hit signal":float((sig.return_pct>0).mean()) if not sig.empty else np.nan,
                     "Hit control":float((ctl.return_pct>0).mean()) if not ctl.empty else np.nan,
                     "Gain10 signal":float((sig.return_pct>=.10).mean()) if not sig.empty else np.nan,
                     "Loss10 signal":float((sig.return_pct<=-.10).mean()) if not sig.empty else np.nan,"Status":status})
    out=pd.DataFrame(rows,columns=cols)
    if not out.empty:out=out.sort_values(["Signal N","Median edge"],ascending=[False,False],na_position="last")
    return out.reset_index(drop=True)

def redundancy_matrix(recommendations:pd.DataFrame|None,min_overlap:int=8)->pd.DataFrame:
    if recommendations is None or recommendations.empty or "snapshot_json" not in recommendations:return pd.DataFrame()
    snaps=recommendations["snapshot_json"].map(_snap)
    data={}
    for name,field,pred in SIGNALS:
        vals=[]
        for s in snaps:
            try:v=float(s.get(field)); vals.append(float(pred(v)))
            except Exception:vals.append(np.nan)
        ser=pd.Series(vals,dtype=float)
        if ser.notna().sum()>=min_overlap:data[name]=ser
    if len(data)<2:return pd.DataFrame()
    return pd.DataFrame(data).corr(min_periods=min_overlap)

def redundancy_pairs(matrix:pd.DataFrame|None,threshold:float=.70)->pd.DataFrame:
    cols=["Signal A","Signal B","Korrelation","Status"]
    if matrix is None or matrix.empty:return pd.DataFrame(columns=cols)
    rows=[]; names=list(matrix.columns)
    for i,a in enumerate(names):
        for b in names[i+1:]:
            c=matrix.loc[a,b]
            if pd.notna(c) and abs(float(c))>=threshold:
                rows.append({"Signal A":a,"Signal B":b,"Korrelation":float(c),
                             "Status":"Möjlig redundans – granska dubbelräkning"})
    return pd.DataFrame(rows,columns=cols).sort_values("Korrelation",ascending=False) if rows else pd.DataFrame(columns=cols)

def lab_summary(evidence:pd.DataFrame)->dict[str,Any]:
    if evidence is None or evidence.empty:
        return {"status":"För lite fryst utfallsdata","promising":0,"warning":0,"message":"Signal Evidence Lab behöver mogna point-in-time-rekommendationer."}
    promising=int(evidence.Status.astype(str).str.startswith("Lovande").sum())
    warning=int(evidence.Status.astype(str).str.startswith("Varningssignal").sum())
    return {"status":"Prospektiv signaldiagnostik","promising":promising,"warning":warning,
            "message":"Resultaten är deskriptiva. Labbet får inte automatiskt ändra score, ranking eller signalvikter."}
