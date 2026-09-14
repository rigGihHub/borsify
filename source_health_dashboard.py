from __future__ import annotations
"""Aggregate Borsify source-health telemetry into a compact operational dashboard."""

from typing import Any
import pandas as pd

IMPACT = {
    "bulk_prices": "ranking, momentum, köpläge, prisfilter",
    "single_prices": "fallback-kurser för enskilda aktier",
    "fx": "SEK-konvertering, börsvärde och likviditetsfilter",
    "index": "relativ styrka och benchmark",
    "fundamentals": "värdering, kvalitet, utdelning och bolagsprofil",
    "deep": "KPI-inflection, estimat, rapportdjup och management-signaler",
}

ORDER = ["bulk_prices","single_prices","fx","index","fundamentals","deep"]


def _status_rank(status: str) -> int:
    s=(status or "").upper()
    if s in {"ERROR","DEGRADED","CIRCUIT_OPEN"}: return 3
    if s in {"PARTIAL","NO_DATA"}: return 2
    if s in {"OK","EMPTY_REQUEST"}: return 0
    return 1


def _normalize_health(name: str, value: Any) -> dict[str, Any]:
    # Per-symbol maps (single prices/fundamentals) are collapsed to worst current status.
    if isinstance(value, dict) and value and all(isinstance(v, dict) for v in value.values()):
        items=list(value.items())
        worst_name,worst=max(items,key=lambda kv:_status_rank(str(kv[1].get("status") or "")))
        statuses=[str(v.get("status") or "") for _,v in items]
        attempts=max([int(v.get("attempts") or 0) for _,v in items] or [0])
        circuits=sum(bool(v.get("circuit_open")) for _,v in items)
        errors=[]
        for sym,v in items:
            err=v.get("error") or v.get("classified_error") or "; ".join(map(str,v.get("errors") or []))
            if err:
                errors.append(f"{sym}: {err}")
        return {
            "endpoint":name,
            "status":str(worst.get("status") or "UNKNOWN"),
            "scope":f"{len(items)} aktier",
            "attempts":attempts,
            "circuit_open":circuits>0,
            "errors":" | ".join(errors[:3]),
            "impact":IMPACT.get(name,""),
        }
    v=value if isinstance(value,dict) else {}
    err=v.get("error") or v.get("classified_error") or "; ".join(map(str,v.get("errors") or []))
    status=str(v.get("status") or "UNKNOWN")
    scope=""
    if "requested" in v and "returned" in v:
        scope=f"{v.get('returned',0)}/{v.get('requested',0)}"
    return {
        "endpoint":name,
        "status":status,
        "scope":scope,
        "attempts":int(v.get("attempts") or 0) if not isinstance(v.get("attempts"),dict) else max([int(x or 0) for x in v["attempts"].values()] or [0]),
        "circuit_open":bool(v.get("circuit_open")) or bool(v.get("circuits_open")),
        "errors":str(err or ""),
        "impact":IMPACT.get(name,""),
    }


def build_source_health_rows(session_state: Any, deep_rows: pd.DataFrame | None = None) -> pd.DataFrame:
    rows=[]
    mapping={
        "bulk_prices":"bq_source_health_bulk_prices",
        "single_prices":"bq_source_health_single_prices",
        "fx":"bq_source_health_fx",
        "index":"bq_source_health_index",
        "fundamentals":"bq_source_health_fundamentals",
        "deep":"bq_source_health_deep",
    }
    for name,key in mapping.items():
        value=session_state.get(key)
        if value is not None:
            rows.append(_normalize_health(name,value))

    # Deep source health is propagated into analysed rows, not global session state.
    if not any(r.get("endpoint")=="deep" for r in rows) and isinstance(deep_rows,pd.DataFrame) and not deep_rows.empty and "Deep source status" in deep_rows.columns:
        sub=deep_rows[deep_rows["Deep source status"].astype(str)!=""].copy()
        if not sub.empty:
            worst=sub.iloc[sub["Deep source status"].map(lambda x:_status_rank(str(x))).argmax()]
            rows.append({
                "endpoint":"deep",
                "status":str(worst.get("Deep source status") or "UNKNOWN"),
                "scope":f"{len(sub)} analyser",
                "attempts":0,
                "circuit_open":bool(worst.get("Deep source circuit open")),
                "errors":str(worst.get("Deep source errors") or worst.get("Deep source error types") or ""),
                "impact":IMPACT["deep"],
            })
    if not rows:
        return pd.DataFrame(columns=["endpoint","status","scope","attempts","circuit_open","errors","impact"])
    out=pd.DataFrame(rows)
    out["_order"]=out["endpoint"].map(lambda x:ORDER.index(x) if x in ORDER else 99)
    return out.sort_values("_order").drop(columns="_order").reset_index(drop=True)


def summarize_source_health(rows: pd.DataFrame | None) -> dict[str, Any]:
    if rows is None or rows.empty:
        return {"status":"⚪ Ingen källstatus ännu","ok":0,"warning":0,"error":0,"circuit":0,
                "message":"Källstatus visas efter att Borsify har gjort minst en datahämtning."}
    ranks=rows["status"].astype(str).map(_status_rank)
    error=int((ranks>=3).sum())
    warning=int((ranks==2).sum())
    ok=int((ranks==0).sum())
    circuit=int(rows["circuit_open"].fillna(False).astype(bool).sum())
    if error or circuit:
        status="🔴 Källproblem påverkar analysen"
    elif warning:
        status="🟡 Några källor är partiella"
    else:
        status="🟢 Datakällor fungerar"
    return {
        "status":status,"ok":ok,"warning":warning,"error":error,"circuit":circuit,
        "message":f"{ok} OK · {warning} partiella · {error} fel · {circuit} öppna circuit breakers",
    }
