from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

from independent_case_validation import independent_case_sample


SHORT_BUY_GATES = {"Kortsiktigt toppcase", "Starkt kortsiktigt case"}
LONG_BUY_GATES = {"Toppcase", "Starkt case"}


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _snapshot(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def frozen_decision(record: pd.Series | dict[str, Any]) -> str:
    """Return the decision that was knowable when the finalist was frozen.

    New records carry an explicit decision in snapshot_json. Older records fall back
    to the frozen gate, never to current/live model data.
    """
    snap = _snapshot(record.get("snapshot_json"))
    explicit = str(snap.get("Ledger Decision") or "").strip().upper()
    if explicit in {"RECOMMENDED", "NOT_RECOMMENDED"}:
        return explicit

    gate = str(record.get("gate") or "").strip()
    horizon_type = str(record.get("horizon_type") or "").strip().lower()
    if horizon_type == "short":
        return "RECOMMENDED" if gate in SHORT_BUY_GATES else "NOT_RECOMMENDED"
    if horizon_type == "long":
        return "RECOMMENDED" if gate in LONG_BUY_GATES else "NOT_RECOMMENDED"
    return "UNKNOWN"


def _reason_from_snapshot(record: pd.Series | dict[str, Any]) -> str:
    snap = _snapshot(record.get("snapshot_json"))
    horizon_type = str(record.get("horizon_type") or "").lower()
    gate = str(record.get("gate") or snap.get("Case Gate") or snap.get("Short Alpha Gate") or "—")
    reasons: list[str] = []

    if horizon_type == "long":
        fstatus = str(snap.get("Fundamental Data status") or "")
        if fstatus == "STOPP":
            reasons.append("bolagsdatan klarade inte kvalitetskontrollen")
        veto_count = _num(snap.get("Case Veto Count"))
        if np.isfinite(veto_count) and veto_count >= 1:
            reasons.append("modellen såg ett eller flera motbevis")
        trap = _num(snap.get("Value Trap Risk"))
        if np.isfinite(trap) and trap >= 70:
            reasons.append("hög risk att aktien var billig av fel skäl")
        evidence = _num(snap.get("Case Evidence Count"))
        if np.isfinite(evidence) and evidence <= 2:
            reasons.append("för få oberoende stöd")
        deep = str(snap.get("Djupkontroll") or "")
        if deep in {"Avstå tills vidare", "Hög value-trap-risk", "Otillräcklig data"}:
            reasons.append("djupkontrollen stoppade eller kunde inte verifiera caset")
        catalyst = str(snap.get("Catalyst Signal") or "").lower()
        if catalyst and ("ingen tydlig" in catalyst or "otillräck" in catalyst):
            reasons.append("ingen tydlig aktuell anledning kunde verifieras")
    elif horizon_type == "short":
        vetoes = str(snap.get("Short Vetoes") or "").strip()
        if vetoes and vetoes != "—":
            reasons.append("ett kortsiktigt stopp fanns")
        confirmations = _num(snap.get("Short Confirmation Count"))
        if np.isfinite(confirmations) and confirmations < 3:
            reasons.append("för få kortsiktiga bekräftelser")
        relative = _num(snap.get("Short Relative Strength"))
        if np.isfinite(relative) and relative < 50:
            reasons.append("aktien gick svagt jämfört med marknaden")
        trend = _num(snap.get("Short Trend"))
        if np.isfinite(trend) and trend < 50:
            reasons.append("trenden var svag")
        catalyst = str(snap.get("Catalyst Signal") or "").lower()
        if catalyst and ("ingen tydlig" in catalyst or "otillräck" in catalyst):
            reasons.append("ingen tydlig aktuell anledning kunde verifieras")

    if reasons:
        return "; ".join(dict.fromkeys(reasons))
    return f"fryst bedömning: {gate}" if gate and gate != "—" else "orsaken går inte att läsa ur den frysta datan"


def false_negative_analysis(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
    relative_threshold: float = 0.10,
    raw_threshold: float = 0.15,
) -> pd.DataFrame:
    """Find rejected finalists that later became clear winners.

    The result is descriptive only. A miss is defined conservatively as at least
    +10 percentage points vs benchmark when the whole cohort has benchmark data,
    otherwise at least +15% raw return. Current/live data is never reconstructed.
    """
    cols = [
        "Datum", "Ticker", "Bolag", "Typ", "Rank", "Fryst bedömning", "Utfall",
        "Mätning", "Varför den valdes bort", "Version", "record_id",
    ]
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame(columns=cols)

    recs = recommendations.copy()
    outs = outcomes.copy()
    if "horizon" not in outs.columns or "record_id" not in outs.columns or "record_id" not in recs.columns:
        return pd.DataFrame(columns=cols)
    outs = outs[outs["horizon"].astype(str).eq(str(horizon))].copy()
    if outs.empty:
        return pd.DataFrame(columns=cols)

    merged = recs.merge(outs, on="record_id", how="inner", suffixes=("", "_out"))
    if merged.empty:
        return pd.DataFrame(columns=cols)
    merged = independent_case_sample(merged, horizon)
    if merged.empty:
        return pd.DataFrame(columns=cols)

    merged["_decision"] = merged.apply(frozen_decision, axis=1)
    rejected = merged[merged["_decision"].eq("NOT_RECOMMENDED")].copy()
    if rejected.empty:
        return pd.DataFrame(columns=cols)

    raw = pd.to_numeric(merged.get("return_pct"), errors="coerce")
    excess = pd.to_numeric(merged.get("excess_return_pct"), errors="coerce") if "excess_return_pct" in merged.columns else pd.Series(np.nan, index=merged.index)
    use_relative = bool(len(merged)) and excess.notna().all()

    rejected["_metric"] = (
        pd.to_numeric(rejected.get("excess_return_pct"), errors="coerce")
        if use_relative
        else pd.to_numeric(rejected.get("return_pct"), errors="coerce")
    )
    threshold = float(relative_threshold if use_relative else raw_threshold)
    rejected = rejected[rejected["_metric"].notna() & (rejected["_metric"] >= threshold)].copy()
    if rejected.empty:
        return pd.DataFrame(columns=cols)

    rejected = rejected.sort_values(["_metric", "rank"], ascending=[False, True], na_position="last")
    rows: list[dict[str, Any]] = []
    for _, row in rejected.iterrows():
        rows.append({
            "Datum": str(row.get("captured_date") or "—"),
            "Ticker": str(row.get("symbol") or "—"),
            "Bolag": str(row.get("name") or row.get("symbol") or "—"),
            "Typ": "Kort sikt" if str(row.get("horizon_type")) == "short" else "Lång sikt",
            "Rank": row.get("rank"),
            "Fryst bedömning": str(row.get("gate") or "—"),
            "Utfall": float(row["_metric"]),
            "Mätning": "Mot index" if use_relative else "Rå kursutveckling",
            "Varför den valdes bort": _reason_from_snapshot(row),
            "Version": str(row.get("model_version") or "—"),
            "record_id": str(row.get("record_id") or ""),
        })
    return pd.DataFrame(rows, columns=cols)


def false_negative_summary(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
) -> dict[str, Any]:
    """Summarise the miss rate among matured rejected finalists."""
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return {"status": "För lite historik", "evaluated_rejected": 0, "misses": 0, "miss_rate": np.nan,
                "text": "Det finns ännu inga mogna bortvalda finalister att utvärdera."}

    recs = recommendations.copy()
    outs = outcomes[outcomes["horizon"].astype(str).eq(str(horizon))].copy() if "horizon" in outcomes.columns else pd.DataFrame()
    if outs.empty:
        return {"status": "För lite historik", "evaluated_rejected": 0, "misses": 0, "miss_rate": np.nan,
                "text": "Det finns ännu inga mogna bortvalda finalister att utvärdera."}

    merged = recs.merge(outs[["record_id"]].drop_duplicates(), on="record_id", how="inner")
    merged = independent_case_sample(merged, horizon) if not merged.empty else merged
    if merged.empty:
        evaluated_rejected = 0
    else:
        evaluated_rejected = int(merged.apply(frozen_decision, axis=1).eq("NOT_RECOMMENDED").sum())
    misses = false_negative_analysis(recommendations, outcomes, horizon)
    miss_count = int(len(misses))
    rate = (miss_count / evaluated_rejected) if evaluated_rejected else np.nan
    if evaluated_rejected < 10:
        status = "För lite historik"
        text = f"{miss_count} tydliga missar bland {evaluated_rejected} mogna bortvalda finalister. Underlaget är för litet för modelländringar."
    else:
        status = "Historik finns"
        text = f"{miss_count} tydliga missar bland {evaluated_rejected} mogna bortvalda finalister ({rate:.0%}). Det visar vad modellen missat – inte hur den ska viktas om."
    return {"status": status, "evaluated_rejected": evaluated_rejected, "misses": miss_count, "miss_rate": rate, "text": text}


def rejection_signal_states(record: pd.Series | dict[str, Any]) -> dict[str, tuple[str, bool | None]]:
    """Return frozen reasons that could have contributed to a rejected finalist.

    Tri-state handling matters: old snapshots that do not contain a field are excluded
    for that signal rather than being treated as a clean comparison case.
    """
    snap = _snapshot(record.get("snapshot_json"))
    horizon_type = str(record.get("horizon_type") or "").lower()
    signals: dict[str, tuple[str, bool | None]] = {}

    def add(key: str, label: str, state: bool | None) -> None:
        signals[key] = (label, state)

    if horizon_type == "long":
        fstatus = str(snap.get("Fundamental Data status") or "")
        add("fundamental_stop", "Bolagsdatan stoppade caset", fstatus == "STOPP" if fstatus else None)

        veto = _num(snap.get("Case Veto Count"))
        add("veto", "Ett eller flera motbevis fanns", bool(veto >= 1) if np.isfinite(veto) else None)

        trap = _num(snap.get("Value Trap Risk"))
        add("value_trap", "Hög risk att aktien var billig av fel skäl", bool(trap >= 70) if np.isfinite(trap) else None)

        evidence = _num(snap.get("Case Evidence Count"))
        add("few_evidence", "För få oberoende stöd", bool(evidence <= 2) if np.isfinite(evidence) else None)

        deep = str(snap.get("Djupkontroll") or "")
        deep_stop_values = {"Avstå tills vidare", "Hög value-trap-risk", "Otillräcklig data"}
        add("deep_stop", "Djupkontrollen stoppade caset", deep in deep_stop_values if deep else None)

        catalyst = str(snap.get("Catalyst Signal") or "").lower()
        add(
            "weak_catalyst",
            "Ingen tydlig aktuell anledning kunde verifieras",
            ("ingen tydlig" in catalyst or "otillräck" in catalyst) if catalyst else None,
        )
    elif horizon_type == "short":
        vetoes = str(snap.get("Short Vetoes") or "").strip()
        add("short_veto", "Ett kortsiktigt stopp fanns", (vetoes != "—") if vetoes else None)

        confirmations = _num(snap.get("Short Confirmation Count"))
        add("few_confirmations", "För få kortsiktiga bekräftelser", bool(confirmations < 3) if np.isfinite(confirmations) else None)

        relative = _num(snap.get("Short Relative Strength"))
        add("weak_relative", "Svag utveckling jämfört med marknaden", bool(relative < 50) if np.isfinite(relative) else None)

        trend = _num(snap.get("Short Trend"))
        add("weak_trend", "Svag trend", bool(trend < 50) if np.isfinite(trend) else None)

        catalyst = str(snap.get("Catalyst Signal") or "").lower()
        add(
            "weak_catalyst",
            "Ingen tydlig aktuell anledning kunde verifieras",
            ("ingen tydlig" in catalyst or "otillräck" in catalyst) if catalyst else None,
        )
    return signals


def rejection_rule_audit(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
    *,
    relative_threshold: float = 0.10,
    raw_threshold: float = 0.15,
    min_exposed: int = 5,
    min_unexposed: int = 5,
) -> pd.DataFrame:
    """Compare miss frequency for rejected finalists with vs without each frozen reason.

    This does *not* say that a rule should be loosened. It identifies rejection reasons
    worth investigating when they are disproportionately common among later winners.
    One common outcome basis is used for the whole rejected cohort.
    """
    cols = [
        "Stopporsak", "Med orsaken", "Missar med orsaken", "Missfrekvens med orsaken",
        "Utan orsaken", "Missfrekvens utan orsaken", "Skillnad procentenheter",
        "Medianutfall med orsaken", "Medianutfall utan orsaken", "Mätning", "Status",
    ]
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame(columns=cols)
    if "record_id" not in recommendations.columns or "record_id" not in outcomes.columns or "horizon" not in outcomes.columns:
        return pd.DataFrame(columns=cols)

    outs = outcomes[outcomes["horizon"].astype(str).eq(str(horizon))].copy()
    if outs.empty:
        return pd.DataFrame(columns=cols)
    merged = recommendations.merge(outs, on="record_id", how="inner", suffixes=("", "_out"))
    if merged.empty:
        return pd.DataFrame(columns=cols)
    merged = independent_case_sample(merged, horizon)
    if merged.empty:
        return pd.DataFrame(columns=cols)
    merged["_decision"] = merged.apply(frozen_decision, axis=1)
    rejected = merged[merged["_decision"].eq("NOT_RECOMMENDED")].copy()
    if rejected.empty:
        return pd.DataFrame(columns=cols)

    raw_all = pd.to_numeric(merged.get("return_pct"), errors="coerce")
    rel_all = pd.to_numeric(merged.get("excess_return_pct"), errors="coerce") if "excess_return_pct" in merged.columns else pd.Series(np.nan, index=merged.index)
    use_relative = bool(len(merged)) and rel_all.notna().all()
    rejected["_metric"] = (
        pd.to_numeric(rejected.get("excess_return_pct"), errors="coerce")
        if use_relative else pd.to_numeric(rejected.get("return_pct"), errors="coerce")
    )
    rejected = rejected[rejected["_metric"].notna()].copy()
    if rejected.empty:
        return pd.DataFrame(columns=cols)
    threshold = float(relative_threshold if use_relative else raw_threshold)
    rejected["_miss"] = rejected["_metric"] >= threshold

    all_keys: dict[str, str] = {}
    states_per_row: list[dict[str, tuple[str, bool | None]]] = []
    for _, row in rejected.iterrows():
        states = rejection_signal_states(row)
        states_per_row.append(states)
        for key, (label, _) in states.items():
            all_keys[key] = label

    rows: list[dict[str, Any]] = []
    for key, label in all_keys.items():
        states = [d.get(key, (label, None))[1] for d in states_per_row]
        work = rejected[["_metric", "_miss"]].copy()
        work["_state"] = states
        work = work[work["_state"].notna()].copy()
        if work.empty:
            continue
        exposed = work[work["_state"] == True]
        clean = work[work["_state"] == False]
        n_exp, n_clean = len(exposed), len(clean)
        exp_rate = float(exposed["_miss"].mean()) if n_exp else np.nan
        clean_rate = float(clean["_miss"].mean()) if n_clean else np.nan
        diff_pp = (exp_rate - clean_rate) * 100 if np.isfinite(exp_rate) and np.isfinite(clean_rate) else np.nan
        enough = n_exp >= min_exposed and n_clean >= min_unexposed
        flagged = enough and int(exposed["_miss"].sum()) >= 3 and np.isfinite(diff_pp) and diff_pp >= 15
        status = "Granska om regeln är för hård" if flagged else ("Kan följas" if enough else "För lite underlag")
        rows.append({
            "Stopporsak": label,
            "Med orsaken": int(n_exp),
            "Missar med orsaken": int(exposed["_miss"].sum()) if n_exp else 0,
            "Missfrekvens med orsaken": exp_rate,
            "Utan orsaken": int(n_clean),
            "Missfrekvens utan orsaken": clean_rate,
            "Skillnad procentenheter": diff_pp,
            "Medianutfall med orsaken": float(exposed["_metric"].median()) if n_exp else np.nan,
            "Medianutfall utan orsaken": float(clean["_metric"].median()) if n_clean else np.nan,
            "Mätning": "Mot index" if use_relative else "Rå kursutveckling",
            "Status": status,
        })
    if not rows:
        return pd.DataFrame(columns=cols)
    result = pd.DataFrame(rows, columns=cols)
    rank = {"Granska om regeln är för hård": 0, "Kan följas": 1, "För lite underlag": 2}
    result["_rank"] = result["Status"].map(rank).fillna(3)
    result["_diff"] = pd.to_numeric(result["Skillnad procentenheter"], errors="coerce").fillna(-999)
    return result.sort_values(["_rank", "_diff", "Med orsaken"], ascending=[True, False, False]).drop(columns=["_rank", "_diff"]).reset_index(drop=True)


def rejection_rule_audit_summary(audit: pd.DataFrame) -> dict[str, Any]:
    if audit is None or audit.empty:
        return {"status": "För lite historik", "count": 0,
                "text": "Det finns ännu inte tillräcklig historik för att jämföra stoppreglerna."}
    flagged = audit[audit["Status"].eq("Granska om regeln är för hård")]
    usable = audit[audit["Status"].isin(["Granska om regeln är för hård", "Kan följas"])]
    if not flagged.empty:
        top = flagged.iloc[0]
        return {
            "status": "Regel värd att granska",
            "count": int(len(flagged)),
            "text": (f"{len(flagged)} stopporsak(er) syns oftare bland senare vinnare än i jämförbara bortval. "
                     f"Störst skillnad gäller '{top['Stopporsak']}'. Det är en signal för granskning – inte ett skäl att automatiskt sänka kraven."),
        }
    if not usable.empty:
        return {"status": "Historik finns – ingen tydlig för hård regel ännu", "count": int(len(usable)),
                "text": "Det finns jämförbara bortval, men ingen stopporsak missar vinnare tydligt oftare ännu."}
    return {"status": "För lite historik", "count": 0,
            "text": "Stopporsaker finns i historiken, men grupperna är ännu för små för en rimlig jämförelse."}
