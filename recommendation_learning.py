from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

MIN_COHORT = 8
STRONGER_MIN_COHORT = 15

def _num(value: Any) -> float:
    try:
        x=float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan

def _snapshot(raw: Any) -> dict[str,Any]:
    if isinstance(raw,dict):
        return raw
    try:
        value=json.loads(str(raw or "{}"))
        return value if isinstance(value,dict) else {}
    except Exception:
        return {}

def _score_bucket(v: Any) -> str:
    x=_num(v)
    if not np.isfinite(x):
        return "Score saknas"
    if x < 60: return "Under 60"
    if x < 70: return "60–69"
    if x < 80: return "70–79"
    return "80+"

def _confidence_bucket(v: Any) -> str:
    x=_num(v)
    if not np.isfinite(x):
        return "Underlag saknas"
    if x < 50: return "Under 50"
    if x < 70: return "50–69"
    if x < 85: return "70–84"
    return "85+"

def prepare_learning_data(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> pd.DataFrame:
    """Join frozen recommendation-time facts to later outcomes.

    Only information actually stored when the recommendation was made is used.
    Missing historical fields remain missing; they are never reconstructed from
    today's data.
    """
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame()

    rec=recommendations.copy()
    out=outcomes.copy()
    required_rec={"record_id","horizon_type","gate","score","confidence","model_version","snapshot_json"}
    required_out={"record_id","horizon","return_pct"}
    if not required_rec.issubset(rec.columns) or not required_out.issubset(out.columns):
        return pd.DataFrame()

    merged=out.merge(
        rec[[
            "record_id","symbol","name","horizon_type","gate","score","confidence",
            "model_version","profile","market","rank","captured_date","snapshot_json"
        ]],
        on="record_id",how="inner",
    )
    merged["return_pct"]=pd.to_numeric(merged["return_pct"],errors="coerce")
    if "excess_return_pct" in merged.columns:
        merged["excess_return_pct"]=pd.to_numeric(merged["excess_return_pct"],errors="coerce")
    merged=merged.dropna(subset=["return_pct"]).copy()
    if merged.empty:
        return merged

    snapshots=merged["snapshot_json"].map(_snapshot)
    merged["Sektor"]=snapshots.map(lambda s: str(s.get("Sektor") or "Okänd"))
    merged["Short Trend"]=snapshots.map(lambda s: _num(s.get("Short Trend")))
    merged["Short Relative Strength"]=snapshots.map(lambda s: _num(s.get("Short Relative Strength")))
    merged["Short Participation"]=snapshots.map(lambda s: _num(s.get("Short Participation")))
    merged["Short Revisions"]=snapshots.map(lambda s: _num(s.get("Short Revisions")))
    merged["Short Catalyst"]=snapshots.map(lambda s: _num(s.get("Short Catalyst")))
    merged["Case Evidence Count"]=snapshots.map(lambda s: _num(s.get("Case Evidence Count")))
    merged["Value Trap Risk"]=snapshots.map(lambda s: str(s.get("Value Trap Risk") or "Okänd"))
    merged["Scoregrupp"]=merged["score"].map(_score_bucket)
    merged["Underlagsgrupp"]=merged["confidence"].map(_confidence_bucket)
    merged["positive"]=merged["return_pct"]>0
    merged["gain_10"]=merged["return_pct"]>=.10
    merged["loss_10"]=merged["return_pct"]<=-.10
    return merged

def learning_metric_basis(data: pd.DataFrame) -> str:
    """Use benchmark-relative outcomes only when the selected sample is complete.

    Older frozen outcomes may predate benchmark tracking. We deliberately avoid
    mixing raw and benchmark-relative returns inside the same cohort comparison.
    """
    if data is not None and not data.empty and "excess_return_pct" in data.columns:
        rel=pd.to_numeric(data["excess_return_pct"],errors="coerce")
        if rel.notna().all():
            return "relative"
    return "raw"


def _evaluation_returns(data: pd.DataFrame) -> pd.Series:
    if learning_metric_basis(data)=="relative":
        return pd.to_numeric(data["excess_return_pct"],errors="coerce")
    return pd.to_numeric(data["return_pct"],errors="coerce")


def _cohort_rows(data: pd.DataFrame, column: str, min_count: int=MIN_COHORT) -> pd.DataFrame:
    if data is None or data.empty or column not in data.columns:
        return pd.DataFrame()
    work=data.copy()
    work[column]=work[column].fillna("Saknas").astype(str)
    rows=[]
    basis=learning_metric_basis(work)
    metric_col="excess_return_pct" if basis=="relative" else "return_pct"
    for name,g in work.groupby(column,dropna=False):
        n=len(g)
        metric=pd.to_numeric(g[metric_col],errors="coerce")
        rows.append({
            "Grupp":str(name),
            "Antal":int(n),
            "Median":float(metric.median()),
            "Snitt":float(metric.mean()),
            "Positiva":float((metric>0).mean()),
            "Minst +10 %":float((metric>=.10).mean()),
            "Högst −10 %":float((metric<=-.10).mean()),
            "Mätning":"Mot index" if basis=="relative" else "Rå kursutveckling",
            "Tillräckligt underlag":bool(n>=min_count),
        })
    return pd.DataFrame(rows).sort_values(["Tillräckligt underlag","Median","Antal"],ascending=[False,False,False])

def learning_tables(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
) -> dict[str,pd.DataFrame]:
    data=prepare_learning_data(recommendations,outcomes)
    if data.empty:
        return {}
    data=data[data["horizon"].astype(str).eq(str(horizon))].copy()
    if data.empty:
        return {}
    return {
        "Bedömning":_cohort_rows(data,"gate"),
        "Score":_cohort_rows(data,"Scoregrupp"),
        "Underlag":_cohort_rows(data,"Underlagsgrupp"),
        "Sektor":_cohort_rows(data,"Sektor"),
        "Modellversion":_cohort_rows(data,"model_version"),
    }

def strongest_and_weakest(
    table: pd.DataFrame,
    min_count: int=MIN_COHORT,
) -> tuple[dict[str,Any]|None,dict[str,Any]|None]:
    if table is None or table.empty:
        return None,None
    enough=table[table["Antal"]>=min_count].copy()
    if len(enough)<2:
        return None,None
    best=enough.sort_values(["Median","Positiva","Antal"],ascending=[False,False,False]).iloc[0].to_dict()
    worst=enough.sort_values(["Median","Positiva","Antal"],ascending=[True,True,False]).iloc[0].to_dict()
    return best,worst

def learning_summary(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
) -> dict[str,Any]:
    """Create cautious plain-Swedish conclusions from descriptive history."""
    data=prepare_learning_data(recommendations,outcomes)
    if data.empty:
        return {
            "status":"För lite historik",
            "count":0,
            "text":"Borsify har ännu inga mogna utfall att lära av för den här perioden.",
        }
    data=data[data["horizon"].astype(str).eq(str(horizon))].copy()
    n=len(data)
    unique_cases=int(data["record_id"].nunique()) if "record_id" in data else n
    if n < MIN_COHORT:
        return {
            "status":"För lite historik",
            "count":n,
            "unique_cases":unique_cases,
            "text":f"Bara {n} mogna utfall finns. Borsify väntar tills minst {MIN_COHORT} finns innan grupper jämförs.",
        }

    tables=learning_tables(recommendations,outcomes,horizon)
    findings=[]
    for title in ["Bedömning","Score","Underlag","Sektor"]:
        best,worst=strongest_and_weakest(tables.get(title,pd.DataFrame()))
        if best and worst and best["Grupp"]!=worst["Grupp"]:
            spread=float(best["Median"])-float(worst["Median"])
            if abs(spread)>=.03:
                findings.append({
                    "dimension":title,
                    "best":best,
                    "worst":worst,
                    "spread":spread,
                })

    if not findings:
        return {
            "status":"Historik finns – inget tydligt mönster ännu",
            "count":n,
            "unique_cases":unique_cases,
            "text":"Det finns tillräckligt många utfall för att börja följa mönster, men ingen grupp skiljer sig tydligt nog för att Borsify ska dra en praktisk slutsats.",
            "findings":[],
        }

    findings=sorted(findings,key=lambda x:abs(x["spread"]),reverse=True)
    top=findings[0]
    b=top["best"]; w=top["worst"]
    cautious=(
        f"I den sparade historiken har gruppen “{b['Grupp']}” haft bättre medianutfall "
        f"({b['Median']:+.1%}, {int(b['Antal'])} utfall) än “{w['Grupp']}” "
        f"({w['Median']:+.1%}, {int(w['Antal'])} utfall) inom {top['dimension'].lower()}. "
        "Det är en observation från Borsifys egen historik, inte ett bevis på att samma mönster fortsätter."
    )
    return {
        "status":"Möjligt historiskt mönster",
        "count":n,
        "unique_cases":unique_cases,
        "text":cautious,
        "findings":findings,
    }

def score_band_monotonicity(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
) -> dict[str,Any]:
    """Check whether higher frozen score bands have generally done better.

    This is diagnostic only; no automatic weight or threshold changes follow.
    """
    tables=learning_tables(recommendations,outcomes,horizon)
    table=tables.get("Score",pd.DataFrame())
    if table.empty:
        return {"status":"För lite underlag"}
    order=["Under 60","60–69","70–79","80+"]
    work=table[table["Grupp"].isin(order) & (table["Antal"]>=MIN_COHORT)].copy()
    if len(work)<2:
        return {"status":"För lite underlag"}
    mapping={x:i for i,x in enumerate(order)}
    work["_order"]=work["Grupp"].map(mapping)
    work=work.sort_values("_order")
    med=work["Median"].to_numpy(dtype=float)
    improving=bool(all(med[i+1]>=med[i] for i in range(len(med)-1)))
    worsening=bool(all(med[i+1]<=med[i] for i in range(len(med)-1)))
    if improving and med[-1]-med[0]>=.03:
        status="Högre score har hittills följts av bättre utfall"
    elif worsening and med[0]-med[-1]>=.03:
        status="Varning: högre score har inte gett bättre utfall"
    else:
        status="Ingen tydlig ordning mellan score och utfall"
    return {
        "status":status,
        "groups":int(len(work)),
        "lowest":float(med[0]),
        "highest":float(med[-1]),
    }

def data_limits_note(recommendations: pd.DataFrame) -> str:
    if recommendations is None or recommendations.empty:
        return "Ingen rekommendationshistorik finns ännu."
    return (
        "Borsify använder bara sådant som frystes när rekommendationen skapades. "
        "Nyare funktioner som inte finns i äldre sparade case kan därför inte testas bakåt i efterhand. "
        "Saknade historiska uppgifter lämnas saknade i stället för att fyllas i med dagens data."
    )
