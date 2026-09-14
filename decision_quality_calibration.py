from __future__ import annotations
"""Prospective calibration of frozen Decision Support quadrants."""

import json
import math
from typing import Any
import numpy as np
import pandas as pd

MIN_CASES_PER_QUADRANT = 8


def _snapshot(v: Any) -> dict[str, Any]:
    if isinstance(v,dict):
        return v
    try:
        return json.loads(v or "{}")
    except Exception:
        return {}


def calibration_table(
    recommendations: pd.DataFrame | None,
    outcomes: pd.DataFrame | None,
    horizon: str,
    min_cases: int = MIN_CASES_PER_QUADRANT,
) -> pd.DataFrame:
    cols=[
        "Beslutsläge","Antal","Medianutfall","Snittutfall","Positiva","≥ +10 %","≤ −10 %",
        "Median mot index","Sämsta observerade median","Status"
    ]
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame(columns=cols)
    if "snapshot_json" not in recommendations.columns or "record_id" not in recommendations.columns:
        return pd.DataFrame(columns=cols)

    rec=recommendations[["record_id","snapshot_json"]].copy()
    rec["_snap"]=rec["snapshot_json"].map(_snapshot)
    rec["Beslutsläge"]=rec["_snap"].map(lambda s:str(s.get("Decision Support quadrant") or "").strip())
    rec=rec[rec["Beslutsläge"]!=""].copy()

    o=outcomes[outcomes["horizon"].astype(str)==str(horizon)].copy()
    if o.empty:
        return pd.DataFrame(columns=cols)

    m=o.merge(rec[["record_id","Beslutsläge"]],on="record_id",how="inner")
    m["return_pct"]=pd.to_numeric(m.get("return_pct"),errors="coerce")
    if "excess_return_pct" in m.columns:
        m["excess_return_pct"]=pd.to_numeric(m["excess_return_pct"],errors="coerce")
    if "worst_return_pct" in m.columns:
        m["worst_return_pct"]=pd.to_numeric(m["worst_return_pct"],errors="coerce")
    m=m.dropna(subset=["return_pct"])
    if m.empty:
        return pd.DataFrame(columns=cols)

    order=[
        "STARK IDÉ / STARK DATA",
        "STARK IDÉ / KRÄVER FÖRSIKTIGHET",
        "STARK IDÉ / SVAG DATA",
        "SVAGARE IDÉ / STARK DATA",
        "SVAG IDÉ / SVAG DATA",
    ]
    rows=[]
    for quadrant,g in m.groupby("Beslutsläge",dropna=False):
        excess=g["excess_return_pct"].dropna() if "excess_return_pct" in g.columns else pd.Series(dtype=float)
        worst=g["worst_return_pct"].dropna() if "worst_return_pct" in g.columns else pd.Series(dtype=float)
        n=len(g)
        rows.append({
            "Beslutsläge":str(quadrant),
            "Antal":int(n),
            "Medianutfall":float(g["return_pct"].median()),
            "Snittutfall":float(g["return_pct"].mean()),
            "Positiva":float((g["return_pct"]>0).mean()),
            "≥ +10 %":float((g["return_pct"]>=.10).mean()),
            "≤ −10 %":float((g["return_pct"]<=-.10).mean()),
            "Median mot index":float(excess.median()) if not excess.empty else np.nan,
            "Sämsta observerade median":float(worst.median()) if not worst.empty else np.nan,
            "Status":"Moget nog för jämförelse" if n>=min_cases else "Bygger facit",
        })
    out=pd.DataFrame(rows,columns=cols)
    out["_o"]=out["Beslutsläge"].map(lambda x:order.index(x) if x in order else 99)
    return out.sort_values(["_o","Antal"],ascending=[True,False]).drop(columns="_o").reset_index(drop=True)


def compare_strong_idea_groups(
    table: pd.DataFrame | None,
    min_cases: int = MIN_CASES_PER_QUADRANT,
) -> dict[str, Any]:
    base={
        "status":"Bygger facit",
        "enough":False,
        "return_edge":np.nan,
        "risk_edge":np.nan,
        "benchmark_edge":np.nan,
        "message":"Det behövs fler mogna case i både stark idé/stark data och stark idé/svag data innan confidence-lagret kan bedömas.",
    }
    if table is None or table.empty:
        return base
    wanted=["STARK IDÉ / STARK DATA","STARK IDÉ / SVAG DATA"]
    rows={}
    for q in wanted:
        g=table[table["Beslutsläge"]==q]
        if not g.empty:
            rows[q]=g.iloc[0]
    if len(rows)<2:
        return base
    a=rows[wanted[0]]; b=rows[wanted[1]]
    if int(a["Antal"])<min_cases or int(b["Antal"])<min_cases:
        return base

    ret=float(a["Medianutfall"])-float(b["Medianutfall"])
    wa=float(a["Sämsta observerade median"]) if pd.notna(a["Sämsta observerade median"]) else np.nan
    wb=float(b["Sämsta observerade median"]) if pd.notna(b["Sämsta observerade median"]) else np.nan
    # Less-negative worst observed return is better.
    risk=wa-wb if np.isfinite(wa) and np.isfinite(wb) else np.nan
    ea=float(a["Median mot index"]) if pd.notna(a["Median mot index"]) else np.nan
    eb=float(b["Median mot index"]) if pd.notna(b["Median mot index"]) else np.nan
    bench=ea-eb if np.isfinite(ea) and np.isfinite(eb) else np.nan

    positive_return=ret>.02
    positive_risk=(not np.isfinite(risk)) or risk>=0
    if positive_return and positive_risk:
        status="Confidence-lagret ser lovande ut"
    elif ret<-.02:
        status="Confidence-lagret bör granskas"
    else:
        status="Ingen tydlig skillnad ännu"

    msg=(
        f"Stark idé/stark data har {ret:+.1%} skillnad i medianutfall mot stark idé/svag data."
    )
    if np.isfinite(risk):
        msg+=f" Skillnaden i median för sämsta observerade periodutfall är {risk:+.1%} (högre är bättre)."
    if np.isfinite(bench):
        msg+=f" Median över index skiljer {bench:+.1%}."
    msg+=" Det är prospektiv diagnostik, inte bevis på framtida avkastning och ändrar inga vikter automatiskt."

    return {
        "status":status,"enough":True,"return_edge":ret,"risk_edge":risk,
        "benchmark_edge":bench,"message":msg,
    }
