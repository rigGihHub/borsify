from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd

from buy_quality_gate import BUY_THRESHOLDS

def _num(v: Any) -> float:
    try:
        x=float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan

def _market_bucket(symbol: str) -> str:
    s=str(symbol or "").upper()
    suffixes={
        ".ST":"Sverige",".CO":"Danmark",".OL":"Norge",".HE":"Finland",
        ".DE":"Tyskland",".L":"Storbritannien",".TO":"Kanada",".V":"Kanada",
        ".PA":"Frankrike",".AS":"Nederländerna",".BR":"Belgien",".MI":"Italien",
        ".MC":"Spanien",".SW":"Schweiz",".LS":"Portugal",
    }
    for suffix,name in suffixes.items():
        if s.endswith(suffix):
            return name
    return "USA"

def classify_market(group: pd.DataFrame) -> dict[str,Any]:
    """Classify one scanned market using median returns and breadth.

    This is a conservative current-scan regime proxy, not a forecast. At least five
    usable stocks are required; otherwise the regime is UNKNOWN and does not alter
    buy thresholds.
    """
    if group is None or group.empty:
        return {
            "Marknadsläge":"FÖR LITE UNDERLAG",
            "Marknadsläge justering":0.0,
            "Marknadsläge förklaring":"För få aktier för att bedöma marknadsläget.",
            "Marknad antal":0,
        }

    m1=pd.to_numeric(group.get("1 mån"),errors="coerce")
    m3=pd.to_numeric(group.get("3 mån"),errors="coerce")
    usable=int(pd.concat([m1,m3],axis=1).dropna(how="all").shape[0])
    if usable < 5:
        return {
            "Marknadsläge":"FÖR LITE UNDERLAG",
            "Marknadsläge justering":0.0,
            "Marknadsläge förklaring":f"Bara {usable} aktier har tillräcklig kursdata i denna marknad.",
            "Marknad antal":usable,
        }

    med1=float(m1.median()) if m1.notna().any() else np.nan
    med3=float(m3.median()) if m3.notna().any() else np.nan
    breadth1=float((m1>0).mean()) if m1.notna().any() else np.nan
    breadth3=float((m3>0).mean()) if m3.notna().any() else np.nan

    very_weak=(
        np.isfinite(med1) and med1 <= -.05
        and np.isfinite(med3) and med3 <= -.10
        and np.isfinite(breadth1) and breadth1 < .35
        and np.isfinite(breadth3) and breadth3 < .35
    )
    weak=(
        very_weak
        or (
            np.isfinite(med1) and med1 <= -.03
            and np.isfinite(breadth1) and breadth1 < .45
        )
        or (
            np.isfinite(med3) and med3 <= -.08
            and np.isfinite(breadth3) and breadth3 < .40
        )
    )
    strong=(
        np.isfinite(med1) and med1 >= .02
        and np.isfinite(med3) and med3 >= .05
        and np.isfinite(breadth1) and breadth1 >= .60
        and np.isfinite(breadth3) and breadth3 >= .60
    )

    if very_weak:
        status="MYCKET SVAG"
    elif weak:
        status="SVAG"
    elif strong:
        status="STARK"
    else:
        status="NEUTRAL"

    def pct(x):
        return "—" if not np.isfinite(x) else f"{x:+.1%}".replace(".",",")
    def share(x):
        return "—" if not np.isfinite(x) else f"{x:.0%}"

    explanation=(
        f"Medianen är {pct(med1)} på en månad och {pct(med3)} på tre månader. "
        f"{share(breadth1)} av aktierna är upp på en månad och {share(breadth3)} på tre månader."
    )

    return {
        "Marknadsläge":status,
        "Marknadsläge justering":0.0,  # horizon-specific adjustment is added later
        "Marknadsläge förklaring":explanation,
        "Marknad antal":usable,
        "Marknad median 1 mån":med1,
        "Marknad median 3 mån":med3,
        "Marknad bredd 1 mån":breadth1,
        "Marknad bredd 3 mån":breadth3,
    }

def required_score_adjustment(status: str, horizon: str) -> float:
    """Weak markets can raise requirements; strong markets never lower them."""
    status=str(status or "")
    if status=="MYCKET SVAG":
        return {"day":4.0,"medium":5.0,"long":3.0,"lifetime":2.0}[horizon]
    if status=="SVAG":
        return {"day":2.0,"medium":3.0,"long":2.0,"lifetime":1.0}[horizon]
    return 0.0

def add_market_regime(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()

    out=df.copy()
    out["Marknad för lägesbedömning"]=out.get("Ticker",pd.Series("",index=out.index)).map(_market_bucket)

    stats={}
    for market,g in out.groupby("Marknad för lägesbedömning",dropna=False):
        stats[str(market)]=classify_market(g)

    rows=[]
    score_col={
        "day":"Daytrade Score",
        "medium":"Mellan Score",
        "long":"Lång Score",
        "lifetime":"Livstid Score",
    }[horizon]
    base=BUY_THRESHOLDS[horizon]

    for _,r in out.iterrows():
        market=str(r.get("Marknad för lägesbedömning") or "")
        info=dict(stats.get(market,classify_market(pd.DataFrame())))
        adj=required_score_adjustment(info.get("Marknadsläge",""),horizon)
        required=base+adj
        score=_num(r.get(score_col))
        passed=(not np.isfinite(score)) or score>=required
        # NaN remains neutral here; the ordinary buy gate already rejects missing score.
        info["Marknadsläge justering"]=adj
        info["Marknadskrav"]=required
        info["Marknadskrav godkänd"]=bool(passed)
        info["Marknadskrav stopp"]=(
            f"svagt marknadsläge höjer köpkravet till {required:.0f}"
            if np.isfinite(score) and score<required and adj>0 else ""
        )
        rows.append(info)

    regime=pd.DataFrame(rows,index=out.index)
    overlap=[c for c in regime.columns if c in out.columns]
    if overlap:
        out=out.drop(columns=overlap)
    return out.join(regime)

def filter_market_regime_eligible(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    if "Marknadskrav godkänd" not in df.columns:
        return df.copy()
    return df[df["Marknadskrav godkänd"].eq(True)].copy()

def market_regime_user_text(row: pd.Series | dict[str,Any]) -> str:
    status=str(row.get("Marknadsläge","") or "")
    adj=_num(row.get("Marknadsläge justering"))
    explanation=str(row.get("Marknadsläge förklaring","") or "")
    if status in {"SVAG","MYCKET SVAG"} and np.isfinite(adj) and adj>0:
        return f"{status.capitalize()} marknad. Borsify kräver därför {adj:.0f} extra poäng för köp. {explanation}"
    if status=="STARK":
        return f"Stark marknad, men Borsify sänker inte sina vanliga köpkrav. {explanation}"
    if status=="NEUTRAL":
        return f"Marknaden är varken tydligt stark eller svag. {explanation}"
    return explanation or "För lite underlag för att ändra köpkraven."
