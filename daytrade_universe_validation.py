from __future__ import annotations
from typing import Callable, Any
import numpy as np
import pandas as pd

from daytrade_validation import build_point_in_time_daytrade, evaluate_daytrade


def split_downloaded_histories(data: pd.DataFrame, symbols: list[str]) -> dict[str,pd.DataFrame]:
    """Split one yfinance multi-ticker download into per-symbol frames."""
    if data is None or data.empty:
        return {}
    syms=list(dict.fromkeys([str(s).upper().strip() for s in symbols if str(s).strip()]))
    if not syms:
        return {}
    if len(syms)==1:
        frame=data.copy()
        if isinstance(frame.columns,pd.MultiIndex):
            for level in (0,1):
                try:
                    frame=frame.xs(syms[0],axis=1,level=level,drop_level=True)
                    break
                except Exception:
                    continue
        return {syms[0]:frame} if "Close" in frame.columns else {}

    if not isinstance(data.columns,pd.MultiIndex):
        return {}
    l0=set(map(str,data.columns.get_level_values(0)))
    l1=set(map(str,data.columns.get_level_values(1)))
    out={}
    for sym in syms:
        try:
            if sym in l0:
                frame=data[sym].copy()
            elif sym in l1:
                frame=data.xs(sym,axis=1,level=1,drop_level=True).copy()
            else:
                continue
            if "Close" in frame.columns:
                out[sym]=frame
        except Exception:
            continue
    return out


def validate_universe(
    histories: dict[str,pd.DataFrame],
    *,
    horizon_days: int,
    roundtrip_cost_bps: float,
    country_fn: Callable[[str],str] | None = None,
) -> tuple[pd.DataFrame,pd.DataFrame,dict[str,Any]]:
    """Validate the frozen daytrader proxy across many securities."""
    rows=[]
    pooled=[]
    for symbol,history in histories.items():
        pit=build_point_in_time_daytrade(history)
        if pit.empty:
            continue
        stats=evaluate_daytrade(pit,horizon_days,roundtrip_cost_bps)
        n=int(stats.get("signals",0) or 0)
        if n <= 0:
            continue
        country=country_fn(symbol) if country_fn else "—"
        rows.append({
            "Ticker":symbol,
            "Land":country,
            "Signaler":n,
            "Median efter kostnader":stats.get("net_median",np.nan),
            "Andel positiva affärer":stats.get("hit_rate",np.nan),
            "Skillnad mot vanlig dag":stats.get("median_excess",np.nan),
            "Vinst/förlust-kvot":stats.get("profit_factor",np.nan),
        })
        spaced=pit[pit["BuyGateProxy"].eq(True)].copy()
        col="Gross1d" if horizon_days==1 else "Gross2d"
        vals=pd.to_numeric(spaced.get(col),errors="coerce").dropna()
        if not vals.empty:
            net=vals-float(roundtrip_cost_bps)/10000.0
            pooled.extend([(symbol,country,float(v)) for v in net.tolist()])

    per_symbol=pd.DataFrame(rows)
    if not pooled:
        return per_symbol,pd.DataFrame(),{
            "symbols_tested":len(histories),"symbols_with_signals":0,"signals":0
        }

    pool=pd.DataFrame(pooled,columns=["Ticker","Land","Netto"])
    country_rows=[]
    for country,g in pool.groupby("Land"):
        vals=g["Netto"]
        country_rows.append({
            "Land":country,
            "Aktier med signaler":int(g["Ticker"].nunique()),
            "Signaler":int(len(g)),
            "Median efter kostnader":float(vals.median()),
            "Andel positiva affärer":float((vals>0).mean()),
        })
    by_country=pd.DataFrame(country_rows).sort_values(
        ["Signaler","Land"],ascending=[False,True]
    ).reset_index(drop=True)

    vals=pool["Netto"]
    summary={
        "symbols_tested":int(len(histories)),
        "symbols_with_signals":int(pool["Ticker"].nunique()),
        "signals":int(len(vals)),
        "median_net":float(vals.median()),
        "hit_rate":float((vals>0).mean()),
        "positive_symbols_share":float(
            (per_symbol["Median efter kostnader"]>0).mean()
        ) if not per_symbol.empty else np.nan,
        "countries_with_signals":int(pool["Land"].nunique()),
    }
    return per_symbol,by_country,summary


def universe_validation_label(summary: dict[str,Any]) -> tuple[str,str]:
    signals=int(summary.get("signals",0) or 0)
    symbols=int(summary.get("symbols_with_signals",0) or 0)
    median=float(summary.get("median_net",np.nan))
    share=float(summary.get("positive_symbols_share",np.nan))
    if signals < 50 or symbols < 5:
        return (
            "För lite underlag",
            "Det finns för få historiska köpsignaler eller för få aktier för att bedöma om mönstret verkar generellt."
        )
    if np.isfinite(median) and median>0 and np.isfinite(share) and share>=.60:
        return (
            "Lovande historiskt mönster – fortfarande osäkert",
            "Resultatet är positivt för många aktier, men historik kan inte visa vad som händer framöver."
        )
    if np.isfinite(median) and median>0:
        return (
            "Blandat historiskt stöd",
            "Det samlade resultatet är positivt, men det verkar inte fungera tillräckligt jämnt mellan aktierna."
        )
    return (
        "Ingen tydlig historisk fördel",
        "Testet visar inte att de här köpsignalerna har gett ett tydligt bättre resultat efter kostnader."
    )
