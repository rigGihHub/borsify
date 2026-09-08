from __future__ import annotations

import json
import math
import re
from typing import Any

import numpy as np
import pandas as pd

MIN_HISTORY = 2
ROBUST_HISTORY = 4


def _num(v: Any) -> float:
    try:
        x=float(v); return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError): return np.nan


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "").strip().lower())


def _directional(direction: str, value: Any) -> float:
    x=_num(value)
    if not math.isfinite(x): return np.nan
    if direction == "positive": return x
    if direction == "negative": return -x
    return np.nan


def _snapshot(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict): return raw
    try: return json.loads(str(raw or "{}"))
    except Exception: return {}


def build_news_event_memory(current: dict[str, Any], ledger: pd.DataFrame | None) -> dict[str, Any]:
    """Compare today's primary event with frozen same-company event history.

    Uses only point-in-time ledger snapshots. Same type + same direction is required.
    Duplicate captures of the same headline are collapsed. No prediction or buy gate is made.
    """
    symbol=str(current.get("Ticker") or current.get("symbol") or "").upper().strip()
    event_type=str(current.get("News Surprise Primary Type") or "—")
    direction=str(current.get("News Surprise Primary Direction") or "uncertain")
    title=str(current.get("News Surprise Primary Title") or "—")
    strength=int(_num(current.get("News Surprise Strength"))) if math.isfinite(_num(current.get("News Surprise Strength"))) else 0
    cur_i=_directional(direction, current.get("News Surprise Immediate Reaction"))
    cur_5=_directional(direction, current.get("News Surprise Five Day Reaction"))

    base={
        "News Event Memory Status":"Otillräcklig historik",
        "News Event Memory Summary":"Det finns ännu inte tillräckligt med fryst historik för samma bolag och händelsetyp.",
        "News Event Memory N":0,
        "News Event Memory Median Immediate":np.nan,
        "News Event Memory Median Two Day":np.nan,
        "News Event Memory Median Five Day":np.nan,
        "News Event Memory Current Gap Immediate":np.nan,
        "News Event Memory Current Gap Five Day":np.nan,
        "News Event Memory Confidence":"Otillräcklig",
        "News Event Memory Event Type":event_type,
        "News Event Memory Direction":direction,
        "News Event Memory Warning":"Historiken är point-in-time och beskrivande, inte en prognos. Små urval är osäkra.",
    }
    if not symbol or event_type in {"", "—", "Oklart"} or direction not in {"positive","negative"} or strength < 2:
        base["News Event Memory Summary"]="Den aktuella nyheten är inte tillräckligt tydligt klassificerad för en historisk jämförelse."
        return base
    if ledger is None or ledger.empty: return base

    seen=set(); events=[]
    for _, rec in ledger.iterrows():
        if str(rec.get("symbol") or "").upper().strip() != symbol: continue
        snap=_snapshot(rec.get("snapshot_json"))
        if str(snap.get("News Surprise Primary Type") or "") != event_type: continue
        if str(snap.get("News Surprise Primary Direction") or "") != direction: continue
        if int(_num(snap.get("News Surprise Strength"))) < 2 if math.isfinite(_num(snap.get("News Surprise Strength"))) else True: continue
        old_title=str(snap.get("News Surprise Primary Title") or "")
        # Prevent the currently observed event, or repeated daily captures of one old event,
        # from masquerading as independent historical observations.
        key=_norm(old_title)
        if not key or key == _norm(title) or key in seen: continue
        seen.add(key)
        immediate=_directional(direction, snap.get("News Surprise Immediate Reaction"))
        two=np.nan  # v3.26 snapshots did not freeze exact 2-session response
        five=_directional(direction, snap.get("News Surprise Five Day Reaction"))
        if math.isfinite(immediate) or math.isfinite(five): events.append((immediate,two,five))

    n=len(events); base["News Event Memory N"]=n
    if n < MIN_HISTORY: return base
    imm=[x[0] for x in events if math.isfinite(x[0])]
    five=[x[2] for x in events if math.isfinite(x[2])]
    mi=float(np.median(imm)) if len(imm)>=MIN_HISTORY else np.nan
    m5=float(np.median(five)) if len(five)>=MIN_HISTORY else np.nan
    base["News Event Memory Median Immediate"]=mi
    base["News Event Memory Median Five Day"]=m5
    base["News Event Memory Confidence"]="Begränsad" if n < ROBUST_HISTORY else "Bättre historik"
    if math.isfinite(cur_i) and math.isfinite(mi): base["News Event Memory Current Gap Immediate"]=cur_i-mi
    if math.isfinite(cur_5) and math.isfinite(m5): base["News Event Memory Current Gap Five Day"]=cur_5-m5

    gap=base["News Event Memory Current Gap Immediate"]
    if math.isfinite(gap) and gap <= -0.02:
        status="Historiskt större reaktion"
        summary=f"{n} äldre liknande händelser i samma bolag har i median följts av större riktad direktreaktion än den aktuella."
    elif math.isfinite(gap) and gap >= 0.02:
        status="Redan starkare reaktion än historiken"
        summary=f"Den aktuella direktreaktionen är större än medianen för {n} äldre liknande händelser i samma bolag."
    else:
        status="Ungefär i linje med historiken"
        summary=f"Den aktuella reaktionen ligger ungefär i linje med {n} äldre liknande händelser i samma bolag."
    if n < ROBUST_HISTORY: summary += " Urvalet är litet och ska tolkas försiktigt."
    base["News Event Memory Status"]=status; base["News Event Memory Summary"]=summary
    return base


def apply_news_event_memory(frame: pd.DataFrame, ledger: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None or frame.empty: return frame.copy() if isinstance(frame,pd.DataFrame) else pd.DataFrame()
    out=frame.copy()
    rows=[build_news_event_memory(r.to_dict(), ledger) for _,r in out.iterrows()]
    mem=pd.DataFrame(rows,index=out.index)
    for c in mem.columns: out[c]=mem[c]
    return out
