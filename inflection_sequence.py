from __future__ import annotations
"""Prospective sequencing of business -> estimates -> report -> market signals.

Events are stored only when observed. Re-running a scan cannot create a new historical
event for the same symbol/signal/source date. No pre-v4.08 history is reconstructed.
"""
import sqlite3, hashlib, math
from typing import Any
import numpy as np
import pandas as pd

SIGNAL_ORDER={"business_kpi":1,"estimate_revision":2,"report_confirmation":3,"market_reaction":4}

def ensure_sequence_table(conn:sqlite3.Connection)->None:
    conn.execute("""CREATE TABLE IF NOT EXISTS inflection_sequence_events(
      event_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, signal_type TEXT NOT NULL,
      source_date TEXT NOT NULL, captured_date TEXT NOT NULL, strength REAL,
      label TEXT NOT NULL DEFAULT '', detail TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

def _date(v:Any)->str:
    s=str(v or "").strip()
    return s[:10] if len(s)>=10 and s[:4].isdigit() else ""

def _num(v:Any)->float:
    try:
        x=float(v); return x if math.isfinite(x) else np.nan
    except Exception:return np.nan

def event(symbol:str,signal_type:str,source_date:Any,captured_date:Any,strength:Any,label:str,detail:str)->dict[str,Any]|None:
    sd=_date(source_date); cd=_date(captured_date)
    if signal_type not in SIGNAL_ORDER or not sd or not cd:return None
    key=f"{symbol.upper()}|{signal_type}|{sd}"
    return {"event_id":hashlib.sha256(key.encode()).hexdigest()[:24],"symbol":symbol.upper(),
            "signal_type":signal_type,"source_date":sd,"captured_date":cd,"strength":_num(strength),
            "label":str(label or ""),"detail":str(detail or "")}

def events_from_snapshot(symbol:str,row:dict[str,Any],captured_date:str)->list[dict[str,Any]]:
    out=[]
    report_date=_date(row.get("Rapportminne rapportdatum") or row.get("Post-report datum"))
    # Business KPI inflection is eligible only when it was actually computed and positive.
    kpi_level=_num(row.get("KPI Inflection nivå"))
    if np.isfinite(kpi_level) and kpi_level>=2 and report_date:
        out.append(event(symbol,"business_kpi",report_date,captured_date,kpi_level,row.get("KPI Inflection",""),row.get("KPI Inflection förklaring","")))
    est=_num(row.get("EPS-estimat förändring"))
    if np.isfinite(est) and est>=.02:
        # Estimate snapshots currently have scan date, not a verified revision timestamp.
        # Use captured_date as source date rather than pretending a historical date.
        out.append(event(symbol,"estimate_revision",captured_date,captured_date,est,row.get("Konsensusförändring status",""),row.get("Förväntningsacceleration förklaring","")))
    if bool(row.get("Report Delta kandidat")) and report_date:
        out.append(event(symbol,"report_confirmation",report_date,captured_date,row.get("Report Delta positiva"),row.get("Report Delta status",""),row.get("Report Delta förklaring","")))
    reaction=_num(row.get("Report Delta kursreaktion"))
    if np.isfinite(reaction) and reaction>=.03 and report_date:
        out.append(event(symbol,"market_reaction",report_date,captured_date,reaction,"positiv marknadsreaktion",f"kursreaktion {reaction:+.1%}"))
    return [x for x in out if x]

def save_events(conn:sqlite3.Connection,events:list[dict[str,Any]])->None:
    ensure_sequence_table(conn)
    for e in events:
        conn.execute("""INSERT OR IGNORE INTO inflection_sequence_events
        (event_id,symbol,signal_type,source_date,captured_date,strength,label,detail) VALUES(?,?,?,?,?,?,?,?)""",
        tuple(e[k] if not (k=="strength" and not np.isfinite(_num(e[k]))) else None for k in
              ["event_id","symbol","signal_type","source_date","captured_date","strength","label","detail"]))

def history(conn:sqlite3.Connection,symbol:str)->pd.DataFrame:
    ensure_sequence_table(conn)
    return pd.read_sql_query("SELECT * FROM inflection_sequence_events WHERE symbol=? ORDER BY source_date,captured_date,signal_type",
                             conn,params=(symbol.upper(),))

def summarize_sequence(df:pd.DataFrame|None)->dict[str,Any]:
    if df is None or df.empty:
        return {"Inflection Sequence":"— Sekvenshistorik byggs","Inflection Sequence steg":0,
                "Inflection Sequence lead days":np.nan,
                "Inflection Sequence förklaring":"Inga prospektivt frysta sekvenshändelser ännu. Borsify återskapar inte äldre signaler."}
    d=df.copy(); d["source_date"]=pd.to_datetime(d["source_date"],errors="coerce"); d=d.dropna(subset=["source_date"])
    first=d.sort_values("source_date").drop_duplicates("signal_type",keep="first")
    types=set(first["signal_type"].astype(str))
    lead=np.nan
    if "business_kpi" in types and "market_reaction" in types:
        a=first[first.signal_type=="business_kpi"]["source_date"].iloc[0]
        b=first[first.signal_type=="market_reaction"]["source_date"].iloc[0]
        lead=float((b-a).days)
    ordered=sorted(types,key=lambda x:SIGNAL_ORDER.get(x,99))
    names={"business_kpi":"verksamhets-KPI","estimate_revision":"estimatrevidering","report_confirmation":"rapportbekräftelse","market_reaction":"marknadsreaktion"}
    text=" → ".join(names[x] for x in ordered)
    if np.isfinite(lead):
        text+=f". Första observerade verksamhets-KPI föregick första positiva marknadsreaktionen med {int(lead)} dagar." if lead>0 else ". Ingen positiv tidsfördel för verksamhets-KPI är ännu verifierad."
    return {"Inflection Sequence":text or "—","Inflection Sequence steg":len(types),"Inflection Sequence lead days":lead,
            "Inflection Sequence förklaring":"Sekvensen bygger endast på frysta point-in-time-händelser. Den visar observationsordning, inte kausalitet."}
