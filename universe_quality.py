from __future__ import annotations
import math
from datetime import datetime, timezone
from typing import Any
import numpy as np
import pandas as pd

def _price_age_days(value: Any) -> float:
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

def _num(v: Any) -> float:
    try:
        x=float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan

def assess_universe_quality(row: dict[str,Any] | pd.Series) -> dict[str,Any]:
    """Assess whether a successfully fetched ticker is usable for ranking.

    This checks market-data integrity, not whether the stock is a good investment.
    Missing fundamentals may lower confidence but do not get silently invented.
    """
    r=row.to_dict() if isinstance(row,pd.Series) else dict(row)
    issues=[]
    positives=[]

    price=_num(r.get("Pris"))
    if not np.isfinite(price) or price <= 0:
        issues.append("saknar giltig aktuell kurs")
    else:
        positives.append("giltig kurs")

    price_date=str(r.get("Prisdatum") or "").strip()
    price_age=_price_age_days(price_date)
    if not price_date or price_date=="—" or not np.isfinite(price_age):
        issues.append("saknar verifierbart kursdatum")
    elif price_age > 7:
        issues.append(f"kursdatum är för gammalt ({int(price_age)} dagar)")
    elif price_age > 4:
        issues.append(f"kursdatum är {int(price_age)} dagar gammalt")
    else:
        positives.append("kursdatum är färskt")

    hist=r.get("_history")
    hist_len=len(hist) if isinstance(hist,pd.DataFrame) else 0
    if hist_len < 20:
        issues.append("för kort kurshistorik")
    elif hist_len >= 120:
        positives.append("tillräcklig historik")

    name=str(r.get("Namn") or "").strip()
    ticker=str(r.get("Ticker") or "").strip()
    if not name or name==ticker:
        issues.append("bolagsnamn kunde inte verifieras")
    else:
        positives.append("bolagsnamn verifierat")

    currency=str(r.get("Valuta") or "").strip()
    if not currency:
        issues.append("valuta saknas")
    else:
        positives.append("valuta verifierad")

    fundamental_fields=["P/E","Forward P/E","ROE","Vinstmarginal","Börsvärde BSEK"]
    fundamental_count=sum(np.isfinite(_num(r.get(k))) for k in fundamental_fields)
    if fundamental_count == 0:
        issues.append("saknar centrala fundamentala datapunkter")
    elif fundamental_count >= 3:
        positives.append("god fundamental täckning")

    # Hard exclusions are reserved for data that cannot support a reliable quote/history.
    hard = (
        not np.isfinite(price) or price <= 0 or hist_len < 20 or
        not price_date or price_date=="—" or not np.isfinite(price_age) or price_age > 7
    )
    if hard:
        status="EXKLUDERA"
    elif fundamental_count == 0 or len(issues) >= 2:
        status="DELVIS VERIFIERAD"
    else:
        status="VERIFIERAD"

    score=max(0, min(100, 100 - 18*len(issues)))
    if hard:
        score=min(score,35)

    return {
        "Universe QC":status,
        "Universe QC Score":float(score),
        "Universe QC Problem":"; ".join(issues) if issues else "inga tydliga datakvalitetsproblem",
        "Universe QC Stöd":"; ".join(positives) if positives else "ingen verifierad kvalitetsindikator",
        "Universe QC Historikdagar":int(hist_len),
        "Universe QC Fundamental datapunkter":int(fundamental_count),
        "Universe QC Kursålder dagar":price_age,
    }

def apply_universe_quality(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    rec={idx:assess_universe_quality(row) for idx,row in out.iterrows()}
    q=pd.DataFrame.from_dict(rec,orient="index")
    overlap=[c for c in q.columns if c in out.columns]
    if overlap:
        out=out.drop(columns=overlap)
    return out.join(q,how="left")

def filter_rankable_universe(df: pd.DataFrame) -> tuple[pd.DataFrame,pd.DataFrame]:
    """Return rankable rows and rows rejected for hard market-data reasons."""
    if df is None or df.empty:
        empty=df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
        return empty, empty
    q=apply_universe_quality(df) if "Universe QC" not in df.columns else df.copy()
    rejected=q[q["Universe QC"].eq("EXKLUDERA")].copy()
    rankable=q[~q["Universe QC"].eq("EXKLUDERA")].copy()
    return rankable,rejected

def quality_summary(df: pd.DataFrame) -> dict[str,int]:
    if df is None or df.empty or "Universe QC" not in df.columns:
        return {"verified":0,"partial":0,"excluded":0,"total":0}
    s=df["Universe QC"].value_counts()
    return {
        "verified":int(s.get("VERIFIERAD",0)),
        "partial":int(s.get("DELVIS VERIFIERAD",0)),
        "excluded":int(s.get("EXKLUDERA",0)),
        "total":int(len(df)),
    }
