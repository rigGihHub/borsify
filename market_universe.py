from __future__ import annotations
from pathlib import Path
import pandas as pd

REQUIRED_COLUMNS = ("Ticker","Land","Nivå")

def load_avanza_universe(path: str | Path) -> pd.DataFrame:
    p=Path(path)
    if not p.exists():
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    try:
        df=pd.read_csv(p)
    except Exception:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    if any(c not in df.columns for c in REQUIRED_COLUMNS):
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    out=df[list(REQUIRED_COLUMNS)].copy()
    out["Ticker"]=out["Ticker"].astype(str).str.strip().str.upper()
    out["Land"]=out["Land"].astype(str).str.strip()
    out["Nivå"]=out["Nivå"].astype(str).str.strip()
    out=out[(out["Ticker"]!="")&(out["Land"]!="")].drop_duplicates("Ticker")
    return out.reset_index(drop=True)

def universe_symbols(df: pd.DataFrame, countries: list[str] | None=None, broad: bool=True) -> list[str]:
    if df is None or df.empty:
        return []
    out=df.copy()
    if countries:
        out=out[out["Land"].isin(countries)]
    if not broad:
        out=out[out["Nivå"].eq("Kärna")]
    return out["Ticker"].astype(str).drop_duplicates().tolist()

def coverage_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Land","Kärna","Bred tillägg","Totalt"])
    rows=[]
    for country,g in df.groupby("Land",sort=True):
        core=int(g["Nivå"].eq("Kärna").sum())
        ext=int(g["Nivå"].eq("Bred").sum())
        rows.append({"Land":country,"Kärna":core,"Bred tillägg":ext,"Totalt":core+ext})
    return pd.DataFrame(rows).sort_values(["Totalt","Land"],ascending=[False,True]).reset_index(drop=True)

def breadth_summary(df: pd.DataFrame) -> dict[str,int]:
    if df is None or df.empty:
        return {"countries":0,"total":0,"core":0,"extended":0}
    return {
        "countries":int(df["Land"].nunique()),
        "total":int(len(df)),
        "core":int(df["Nivå"].eq("Kärna").sum()),
        "extended":int(df["Nivå"].eq("Bred").sum()),
    }
