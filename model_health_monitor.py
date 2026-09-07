from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

from independent_case_validation import independent_case_sample
from signal_ablation import SHORT_WEIGHTS

MIN_WINDOW = 12
MIN_DATA_WINDOW = 25
MIN_REGIME_CASES = 12
PERFORMANCE_DROP = 0.05
HIT_RATE_DROP = 0.15
CORR_DROP = 0.15
DATA_FLOOR = 0.90
SIGNAL_SHIFT_POINTS = 15.0


def _snapshot(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw or "{}"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _outcome_basis(frame: pd.DataFrame) -> tuple[str, str]:
    if frame is not None and not frame.empty and "excess_return_pct" in frame.columns:
        rel = pd.to_numeric(frame["excess_return_pct"], errors="coerce")
        if rel.notna().all():
            return "excess_return_pct", "Mot index"
    return "return_pct", "Rå kursutveckling"


def _rank_corr(score: pd.Series, outcome: pd.Series) -> float:
    work = pd.DataFrame({"score": score, "outcome": outcome}).dropna()
    if len(work) < 6 or work["score"].nunique() < 2 or work["outcome"].nunique() < 2:
        return np.nan
    return float(work["score"].rank(method="average").corr(work["outcome"].rank(method="average")))


def _short_mature_data(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame()
    required_r = {"record_id", "horizon_type", "score"}
    required_o = {"record_id", "horizon", "return_pct"}
    if not required_r.issubset(recommendations.columns) or not required_o.issubset(outcomes.columns):
        return pd.DataFrame()
    rec = recommendations[recommendations["horizon_type"].astype(str).str.lower().eq("short")].copy()
    out = outcomes[outcomes["horizon"].astype(str).eq(str(horizon))].copy()
    keep = [c for c in ["record_id", "symbol", "captured_date", "score", "snapshot_json", "market", "model_version"] if c in rec.columns]
    merged = rec[keep].merge(out, on="record_id", how="inner", suffixes=("", "_out"))
    merged["score"] = pd.to_numeric(merged["score"], errors="coerce")
    merged["return_pct"] = pd.to_numeric(merged["return_pct"], errors="coerce")
    if "excess_return_pct" in merged.columns:
        merged["excess_return_pct"] = pd.to_numeric(merged["excess_return_pct"], errors="coerce")
    merged = merged.dropna(subset=["score", "return_pct"]).copy()
    if merged.empty:
        return merged
    return independent_case_sample(merged, str(horizon)).sort_values("captured_date", kind="stable").reset_index(drop=True)


def performance_drift(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str) -> dict[str, Any]:
    data = _short_mature_data(recommendations, outcomes, horizon)
    if len(data) < MIN_WINDOW * 2:
        return {"Kontroll": f"Utfall {horizon}", "Status": "Vänta", "N": int(len(data)), "Detalj": f"Minst {MIN_WINDOW * 2} oberoende case krävs för att jämföra senaste period med föregående."}
    metric_col, metric_label = _outcome_basis(data)
    prior = data.iloc[-MIN_WINDOW * 2:-MIN_WINDOW].copy()
    recent = data.iloc[-MIN_WINDOW:].copy()
    p = pd.to_numeric(prior[metric_col], errors="coerce")
    r = pd.to_numeric(recent[metric_col], errors="coerce")
    med_drop = float(r.median() - p.median())
    hit_drop = float((r > 0).mean() - (p > 0).mean())
    if med_drop <= -PERFORMANCE_DROP and hit_drop <= -HIT_RATE_DROP:
        status = "Varning"
    elif med_drop <= -PERFORMANCE_DROP or hit_drop <= -HIT_RATE_DROP:
        status = "Bevaka"
    else:
        status = "OK"
    return {
        "Kontroll": f"Utfall {horizon}", "Status": status, "N": int(len(data)),
        "Detalj": f"Senaste {MIN_WINDOW}: median {r.median()*100:.1f}% mot {p.median()*100:.1f}% före; positiva {(r>0).mean()*100:.0f}% mot {(p>0).mean()*100:.0f}% ({metric_label.lower()}).",
        "median_delta": med_drop, "hit_delta": hit_drop,
    }


def calibration_drift(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str) -> dict[str, Any]:
    data = _short_mature_data(recommendations, outcomes, horizon)
    if len(data) < MIN_WINDOW * 2:
        return {"Kontroll": f"Rangordning {horizon}", "Status": "Vänta", "N": int(len(data)), "Detalj": "För lite oberoende historik för att jämföra rangordningen över tid."}
    metric_col, _ = _outcome_basis(data)
    prior = data.iloc[-MIN_WINDOW * 2:-MIN_WINDOW]
    recent = data.iloc[-MIN_WINDOW:]
    pc = _rank_corr(pd.to_numeric(prior["score"], errors="coerce"), pd.to_numeric(prior[metric_col], errors="coerce"))
    rc = _rank_corr(pd.to_numeric(recent["score"], errors="coerce"), pd.to_numeric(recent[metric_col], errors="coerce"))
    if not math.isfinite(pc) or not math.isfinite(rc):
        return {"Kontroll": f"Rangordning {horizon}", "Status": "Vänta", "N": int(len(data)), "Detalj": "Score eller utfall varierar för lite för en stabil rangkorrelation."}
    delta = rc - pc
    if rc <= -0.10 and delta <= -CORR_DROP:
        status = "Varning"
    elif delta <= -CORR_DROP:
        status = "Bevaka"
    else:
        status = "OK"
    return {"Kontroll": f"Rangordning {horizon}", "Status": status, "N": int(len(data)), "Detalj": f"Score–utfall-korrelation senaste {MIN_WINDOW}: {rc:.2f}; föregående {MIN_WINDOW}: {pc:.2f}.", "corr_delta": delta}


def data_health(recommendations: pd.DataFrame) -> dict[str, Any]:
    if recommendations is None or recommendations.empty or "snapshot_json" not in recommendations.columns:
        return {"Kontroll": "Point-in-time-data", "Status": "Vänta", "N": 0, "Detalj": "Ingen fryst rekommendationsdata finns ännu."}
    rec = recommendations.copy()
    if "horizon_type" in rec.columns:
        rec = rec[rec["horizon_type"].astype(str).str.lower().eq("short")]
    if "captured_date" in rec.columns:
        rec = rec.sort_values("captured_date", kind="stable")
    rec = rec.tail(MIN_DATA_WINDOW)
    if len(rec) < MIN_DATA_WINDOW:
        return {"Kontroll": "Point-in-time-data", "Status": "Vänta", "N": int(len(rec)), "Detalj": f"Minst {MIN_DATA_WINDOW} nya kortsiktiga snapshots krävs för en stabil datakontroll."}
    snaps = rec["snapshot_json"].map(_snapshot)
    pit = snaps.map(lambda s: bool(s.get("PIT Complete")) if s.get("PIT Complete") is not None else False)
    fields = [field for field, _ in SHORT_WEIGHTS.values()]
    complete = snaps.map(lambda s: all(math.isfinite(_num(s.get(f))) for f in fields))
    pit_rate = float(pit.mean())
    signal_rate = float(complete.mean())
    if pit_rate < DATA_FLOOR or signal_rate < DATA_FLOOR:
        status = "Varning"
    elif pit_rate < 0.96 or signal_rate < 0.96:
        status = "Bevaka"
    else:
        status = "OK"
    return {"Kontroll": "Point-in-time-data", "Status": status, "N": int(len(rec)), "Detalj": f"PIT komplett {pit_rate*100:.0f}%; komplett Short Alpha-data {signal_rate*100:.0f}% i senaste {len(rec)} snapshots.", "pit_rate": pit_rate, "signal_rate": signal_rate}


def signal_distribution_drift(recommendations: pd.DataFrame) -> dict[str, Any]:
    if recommendations is None or recommendations.empty or "snapshot_json" not in recommendations.columns:
        return {"Kontroll": "Signalbeteende", "Status": "Vänta", "N": 0, "Detalj": "Ingen fryst signalhistorik finns ännu."}
    rec = recommendations.copy()
    if "horizon_type" in rec.columns:
        rec = rec[rec["horizon_type"].astype(str).str.lower().eq("short")]
    if "captured_date" in rec.columns:
        rec = rec.sort_values("captured_date", kind="stable")
    if len(rec) < MIN_DATA_WINDOW * 2:
        return {"Kontroll": "Signalbeteende", "Status": "Vänta", "N": int(len(rec)), "Detalj": f"Minst {MIN_DATA_WINDOW*2} kortsiktiga snapshots krävs för att upptäcka distributionsskiften."}
    work = rec.tail(MIN_DATA_WINDOW * 2).copy()
    snaps = work["snapshot_json"].map(_snapshot)
    shifts = []
    for label, (field, _) in SHORT_WEIGHTS.items():
        values = snaps.map(lambda s, f=field: _num(s.get(f)))
        prior = pd.to_numeric(values.iloc[:MIN_DATA_WINDOW], errors="coerce").dropna()
        recent = pd.to_numeric(values.iloc[MIN_DATA_WINDOW:], errors="coerce").dropna()
        if len(prior) >= 10 and len(recent) >= 10:
            delta = float(recent.median() - prior.median())
            if abs(delta) >= SIGNAL_SHIFT_POINTS:
                shifts.append((label, delta))
    if len(shifts) >= 2:
        status = "Bevaka"
    else:
        status = "OK"
    if shifts:
        text = ", ".join(f"{name} {delta:+.0f}p" for name, delta in shifts[:3])
        detail = f"Tydligt medianskifte i {len(shifts)} signaler mellan två {MIN_DATA_WINDOW}-snapshotfönster: {text}. Det kan vara marknadsläge – inte modellfel."
    else:
        detail = f"Inget stort medianskifte (≥{SIGNAL_SHIFT_POINTS:.0f} poäng) i de sex Short Alpha-signalerna mellan två {MIN_DATA_WINDOW}-snapshotfönster."
    return {"Kontroll": "Signalbeteende", "Status": status, "N": int(len(work)), "Detalj": detail, "shift_count": len(shifts)}


def regime_health(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str = "1m") -> dict[str, Any]:
    data = _short_mature_data(recommendations, outcomes, horizon)
    if data.empty or "snapshot_json" not in data.columns:
        return {"Kontroll": "Marknadslägen", "Status": "Vänta", "N": int(len(data)), "Detalj": "För lite fryst marknadslägesdata."}
    snaps = data["snapshot_json"].map(_snapshot)
    data = data.copy()
    data["_regime"] = snaps.map(lambda s: str(s.get("Marknadsläge") or "").strip())
    data = data[data["_regime"].ne("")]
    if data.empty:
        return {"Kontroll": "Marknadslägen", "Status": "Vänta", "N": 0, "Detalj": "Äldre snapshots saknar marknadsläge."}
    metric_col, metric_label = _outcome_basis(data)
    mature = []
    for regime, group in data.groupby("_regime"):
        if len(group) >= MIN_REGIME_CASES:
            metric = pd.to_numeric(group[metric_col], errors="coerce").dropna()
            if len(metric) >= MIN_REGIME_CASES:
                mature.append((regime, len(metric), float(metric.median()), float((metric > 0).mean())))
    if len(mature) < 2:
        return {"Kontroll": "Marknadslägen", "Status": "Vänta", "N": int(len(data)), "Detalj": f"Minst två marknadslägen med {MIN_REGIME_CASES} oberoende case vardera krävs."}
    worst = min(mature, key=lambda x: x[2])
    if worst[2] <= -0.05 and worst[3] <= 0.35:
        status = "Varning"
    elif worst[2] <= -0.03:
        status = "Bevaka"
    else:
        status = "OK"
    return {"Kontroll": "Marknadslägen", "Status": status, "N": int(sum(x[1] for x in mature)), "Detalj": f"Svagast är {worst[0]}: median {worst[2]*100:.1f}%, positiva {worst[3]*100:.0f}% ({metric_label.lower()}); {len(mature)} lägen har moget underlag."}


def model_health_table(recommendations: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = [data_health(recommendations), signal_distribution_drift(recommendations)]
    for horizon in ("1m", "3m"):
        rows.append(performance_drift(recommendations, outcomes, horizon))
        rows.append(calibration_drift(recommendations, outcomes, horizon))
    rows.append(regime_health(recommendations, outcomes, "1m"))
    cols = ["Kontroll", "Status", "N", "Detalj"]
    return pd.DataFrame([{c: row.get(c) for c in cols} for row in rows], columns=cols)


def model_health_summary(table: pd.DataFrame) -> dict[str, Any]:
    if table is None or table.empty:
        return {"status": "Vänta", "text": "Ingen modellhälsa kan mätas ännu.", "automatic_rollback": False}
    statuses = table["Status"].astype(str)
    warnings = int((statuses == "Varning").sum())
    watches = int((statuses == "Bevaka").sum())
    evaluated = int(statuses.isin(["OK", "Bevaka", "Varning"]).sum())
    critical = table[table["Kontroll"].astype(str).str.startswith(("Utfall", "Rangordning")) & table["Status"].eq("Varning")]
    if warnings >= 2 and not critical.empty:
        status = "Granska rollback"
        text = "Champion visar flera samtidiga varningar, inklusive försämrat utfall eller rangordning. Gör en manuell root-cause- och rollbackprövning innan någon modelländring."
    elif warnings >= 1 or watches >= 2:
        status = "Bevaka noga"
        text = "Champion visar tecken som bör följas tätare, men underlaget räcker inte för rollback."
    elif evaluated == 0:
        status = "Vänta"
        text = "För lite mogen point-in-time-historik för att bedöma champion-modellens hälsa."
    else:
        status = "Stabil"
        text = "Ingen tydlig samtidig försämring syns i de kontroller som har tillräckligt underlag. Det är inte bevis på framtida modellstyrka."
    return {"status": status, "text": text, "warnings": warnings, "watches": watches, "evaluated": evaluated, "automatic_rollback": False}
