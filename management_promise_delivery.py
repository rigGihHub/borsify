from __future__ import annotations
"""Prospective management promise-vs-delivery memory.

Only explicit, dated guidance claims are eligible. The module never reconstructs old
promises from today's data. Numeric delivery can only be judged when both a target and
a later actual for the same metric are available; otherwise it records the promise and
reports that delivery is still unverified.
"""
import hashlib, json, math, re, sqlite3
from typing import Any
import numpy as np
import pandas as pd

UP_WORDS=("höj","raise","raised","increase","increased","above","över")
DOWN_WORDS=("sänk","cut","lower","lowered","below","under","profit warning")
METRICS={
    "revenue":("revenue","sales","omsättning"),
    "margin":("margin","marginal"),
    "eps":("eps","vinst per aktie"),
    "fcf":("fcf","free cash flow","fritt kassaflöde"),
}

def _date(v:Any)->str:
    s=str(v or "").strip()
    return s[:10] if len(s)>=10 and s[:4].isdigit() else ""

def _num(v:Any)->float:
    try:
        x=float(v); return x if math.isfinite(x) else np.nan
    except Exception:return np.nan

def parse_explicit_guidance(text:Any, source_date:Any="", symbol:str="")->list[dict[str,Any]]:
    raw=str(text or "").strip()
    if not raw or "ingen explicit guidningsförändring" in raw.lower():
        return []
    low=raw.lower()
    direction="raised" if any(w in low for w in UP_WORDS) else "lowered" if any(w in low for w in DOWN_WORDS) else "stated"
    metric="unspecified"
    for key,words in METRICS.items():
        if any(w in low for w in words):
            metric=key; break
    # A numeric target is accepted only when tied to an identifiable metric.
    nums=re.findall(r"(?<!\d)(-?\d+(?:[.,]\d+)?)\s*(%)?",raw)
    target=np.nan; unit=""
    if metric!="unspecified" and nums:
        n,pct=nums[-1]
        target=float(n.replace(",",".")); unit="%" if pct else "raw"
        if pct: target/=100.0
    d=_date(source_date)
    canonical=f"{symbol.upper()}|{d}|{metric}|{direction}|{raw}"
    return [{
        "promise_id":hashlib.sha256(canonical.encode()).hexdigest()[:24],
        "symbol":symbol.strip().upper(),"source_date":d,"metric":metric,
        "direction":direction,"target":target,"unit":unit,"promise_text":raw,
    }]

def ensure_management_promise_table(conn:sqlite3.Connection)->None:
    conn.execute("""CREATE TABLE IF NOT EXISTS management_promises(
        promise_id TEXT PRIMARY KEY, symbol TEXT NOT NULL, source_date TEXT NOT NULL DEFAULT '',
        metric TEXT NOT NULL, direction TEXT NOT NULL, target REAL, unit TEXT NOT NULL DEFAULT '',
        promise_text TEXT NOT NULL, captured_date TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")

def save_management_promises(conn:sqlite3.Connection,promises:list[dict[str,Any]],captured_date:str)->None:
    ensure_management_promise_table(conn)
    for p in promises:
        conn.execute("""INSERT OR IGNORE INTO management_promises
        (promise_id,symbol,source_date,metric,direction,target,unit,promise_text,captured_date)
        VALUES(?,?,?,?,?,?,?,?,?)""",(p["promise_id"],p["symbol"],p["source_date"],p["metric"],p["direction"],
        None if not np.isfinite(_num(p.get("target"))) else float(p["target"]),p["unit"],p["promise_text"],_date(captured_date) or str(captured_date)))

def promises_for_symbol(conn:sqlite3.Connection,symbol:str)->pd.DataFrame:
    ensure_management_promise_table(conn)
    return pd.read_sql_query("SELECT * FROM management_promises WHERE symbol=? ORDER BY source_date,captured_date",
                             conn,params=(symbol.strip().upper(),))

def assess_promise_delivery(promises:pd.DataFrame|None, actuals:dict[str,Any]|None=None)->dict[str,Any]:
    if promises is None or promises.empty:
        return {"Management promise status":"— Ingen explicit guidance-historik ännu","Management promise antal":0,
                "Management promise verifierbara":0,"Management promise levererade":0,
                "Management promise träff":np.nan,
                "Management promise förklaring":"Borsify har ännu ingen explicit point-in-time guidance att jämföra. Äldre löften återskapas inte."}
    actuals=actuals or {}
    verifiable=0; delivered=0; misses=[]
    for _,p in promises.iterrows():
        metric=str(p.get("metric") or "")
        target=_num(p.get("target")); actual=_num(actuals.get(metric))
        if metric=="unspecified" or not np.isfinite(target) or not np.isfinite(actual):
            continue
        verifiable+=1
        direction=str(p.get("direction") or "")
        ok = actual>=target if direction=="raised" else actual<=target if direction=="lowered" else abs(actual-target)<=max(abs(target)*.05,.005)
        delivered+=int(ok)
        if not ok: misses.append(metric)
    if verifiable==0:
        status="🟡 Löften finns – leverans ännu inte verifierbar"
        why="Explicita guidance-punkter är frysta, men Borsify saknar ännu matchande senare actuals för samma KPI."
        hit=np.nan
    else:
        hit=delivered/verifiable
        status="🟢 Stark promise-vs-delivery-historik" if verifiable>=3 and hit>=.75 else "⚠️ Svag promise-vs-delivery-historik" if verifiable>=3 and hit<.5 else "🟡 Promise-vs-delivery bygger fortfarande historik"
        why=f"{delivered} av {verifiable} numeriskt jämförbara frysta löften är uppfyllda enligt tillgängliga senare actuals."
        if misses: why+=" Missade KPI:er: "+", ".join(sorted(set(misses)))+"."
    return {"Management promise status":status,"Management promise antal":int(len(promises)),
            "Management promise verifierbara":verifiable,"Management promise levererade":delivered,
            "Management promise träff":hit,"Management promise förklaring":why}
