from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd

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

def _score_excess(excess: float) -> float:
    if not np.isfinite(excess):
        return 50.0
    # -15 percentage points relative performance = weak, +15 = strong.
    return float(np.clip((excess + .15) / .30 * 100.0, 0.0, 100.0))

def add_relative_strength(df: pd.DataFrame) -> pd.DataFrame:
    """Compare each stock with peers in the same scanned market and sector.

    Uses only the current scan; no external benchmark is fabricated. Peer medians
    need at least 3 observations. Sector strength measures whether the sector median
    itself beats the market median.
    """
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()

    out=df.copy()
    old=[
        "Jämförelsemarknad","Marknad 1 mån","Marknad 3 mån",
        "Sektor 1 mån","Sektor 3 mån","Relativ marknad 1 mån","Relativ marknad 3 mån",
        "Relativ sektor 1 mån","Relativ sektor 3 mån","Sektorstyrka 1 mån","Sektorstyrka 3 mån",
        "Relativ styrka","Relativ styrka förklaring","Relativ styrka underlag",
    ]
    out=out.drop(columns=[c for c in old if c in out.columns],errors="ignore")
    out["Jämförelsemarknad"]=out.get("Ticker",pd.Series("",index=out.index)).map(_market_bucket)

    for col in ["1 mån","3 mån"]:
        out[col]=pd.to_numeric(out.get(col,pd.Series(np.nan,index=out.index)),errors="coerce")

    market_stats={}
    for (market,),g in out.groupby(["Jämförelsemarknad"],dropna=False):
        market_stats[(market,"1 mån")]=float(g["1 mån"].median()) if g["1 mån"].notna().sum()>=3 else np.nan
        market_stats[(market,"3 mån")]=float(g["3 mån"].median()) if g["3 mån"].notna().sum()>=3 else np.nan

    sector_stats={}
    sector_counts={}
    sectors=out.get("Sektor",pd.Series("Okänd",index=out.index)).fillna("Okänd").astype(str)
    out["_sector_tmp"]=sectors
    for (market,sector),g in out.groupby(["Jämförelsemarknad","_sector_tmp"],dropna=False):
        for col in ["1 mån","3 mån"]:
            count=int(g[col].notna().sum())
            sector_counts[(market,sector,col)]=count
            sector_stats[(market,sector,col)]=float(g[col].median()) if count>=3 and sector.lower()!="okänd" else np.nan

    rows=[]
    for _,r in out.iterrows():
        market=str(r.get("Jämförelsemarknad") or "")
        sector=str(r.get("_sector_tmp") or "Okänd")
        m1=_num(r.get("1 mån")); m3=_num(r.get("3 mån"))
        market1=_num(market_stats.get((market,"1 mån")))
        market3=_num(market_stats.get((market,"3 mån")))
        sector1=_num(sector_stats.get((market,sector,"1 mån")))
        sector3=_num(sector_stats.get((market,sector,"3 mån")))

        rel_m1=m1-market1 if np.isfinite(m1) and np.isfinite(market1) else np.nan
        rel_m3=m3-market3 if np.isfinite(m3) and np.isfinite(market3) else np.nan
        rel_s1=m1-sector1 if np.isfinite(m1) and np.isfinite(sector1) else np.nan
        rel_s3=m3-sector3 if np.isfinite(m3) and np.isfinite(sector3) else np.nan
        sec_strength1=sector1-market1 if np.isfinite(sector1) and np.isfinite(market1) else np.nan
        sec_strength3=sector3-market3 if np.isfinite(sector3) and np.isfinite(market3) else np.nan

        components=[]
        for value,weight in [(rel_m1,.25),(rel_m3,.35),(rel_s1,.15),(rel_s3,.20),(sec_strength3,.05)]:
            if np.isfinite(value):
                components.append((_score_excess(value),weight))
        if components:
            total_weight=sum(w for _,w in components)
            score=sum(s*w for s,w in components)/total_weight
        else:
            score=50.0

        positive=[]
        negative=[]
        if np.isfinite(rel_m3):
            (positive if rel_m3>0 else negative).append(
                f"aktien har gått {abs(rel_m3):.1%} {'bättre' if rel_m3>0 else 'sämre'} än jämförbara aktier på samma marknad på tre månader"
            )
        if np.isfinite(rel_s3):
            (positive if rel_s3>0 else negative).append(
                f"aktien har gått {abs(rel_s3):.1%} {'bättre' if rel_s3>0 else 'sämre'} än sin sektor på tre månader"
            )
        if np.isfinite(sec_strength3):
            (positive if sec_strength3>0 else negative).append(
                f"sektorn har gått {abs(sec_strength3):.1%} {'bättre' if sec_strength3>0 else 'sämre'} än marknaden"
            )
        explanation="; ".join((positive+negative)[:3]) or "för få jämförbara aktier för en säker relativ jämförelse"
        peer_count=sector_counts.get((market,sector,"3 mån"),0)
        rows.append({
            "Marknad 1 mån":market1,"Marknad 3 mån":market3,
            "Sektor 1 mån":sector1,"Sektor 3 mån":sector3,
            "Relativ marknad 1 mån":rel_m1,"Relativ marknad 3 mån":rel_m3,
            "Relativ sektor 1 mån":rel_s1,"Relativ sektor 3 mån":rel_s3,
            "Sektorstyrka 1 mån":sec_strength1,"Sektorstyrka 3 mån":sec_strength3,
            "Relativ styrka":float(score),
            "Relativ styrka förklaring":explanation,
            "Relativ styrka underlag":f"{peer_count} aktier i samma sektor på {market}" if peer_count else f"marknadsjämförelse för {market}",
        })

    rel=pd.DataFrame(rows,index=out.index)
    out=out.drop(columns=["_sector_tmp"])
    return out.join(rel)

def relative_strength_label(row: pd.Series | dict[str,Any]) -> str:
    score=_num(row.get("Relativ styrka"))
    if not np.isfinite(score):
        return "För lite underlag"
    if score>=68:
        return "Starkare än jämförelsen"
    if score>=55:
        return "Något starkare än jämförelsen"
    if score>=45:
        return "Ungefär i nivå med jämförelsen"
    return "Svagare än jämförelsen"
