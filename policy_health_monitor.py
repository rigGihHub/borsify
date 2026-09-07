from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

from independent_case_validation import independent_case_sample
from production_policy_registry import (
    DEFAULT_POLICY_ID,
    current_policy,
    policy_registry_summary,
)
from prospective_policy_registry import default_prospective_policies
from regime_selection_policy import POLICIES

MIN_TARGET = 16
MIN_GROUP = 6
MIN_COVERAGE = 0.90
WATCH_FILTER_RATE = 0.70
WARN_FILTER_RATE = 0.85
SUPPORT_GAP = 0.04
STRONG_WINNER = 0.08


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
            return "excess_return_pct", "mot index"
    return "return_pct", "rå kursutveckling"


def _active_spec(policy_id: str):
    registered = {p.policy_id: p for p in default_prospective_policies()}
    policy = registered.get(str(policy_id))
    if policy is None:
        return None, None
    by_name = {p.name: p for p in POLICIES}
    return policy, by_name.get(policy.name)


def _after_activation(recommendations: pd.DataFrame, event: dict[str, Any]) -> pd.DataFrame:
    if recommendations is None or recommendations.empty:
        return pd.DataFrame()
    work = recommendations.copy()
    if "horizon_type" in work.columns:
        work = work[work["horizon_type"].astype(str).str.lower().eq("short")]
    date_col = "captured_at" if "captured_at" in work.columns else "captured_date" if "captured_date" in work.columns else None
    if date_col is None:
        return work.iloc[0:0].copy()
    captured = pd.to_datetime(work[date_col], errors="coerce", utc=True)
    effective = pd.to_datetime(event.get("effective_at"), errors="coerce", utc=True)
    if pd.isna(effective):
        return work.iloc[0:0].copy()
    return work[captured.notna() & captured.ge(effective)].copy()


def _policy_sample(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    event: dict[str, Any],
    horizon: str,
    spec,
) -> pd.DataFrame:
    rec = _after_activation(recommendations, event)
    if rec.empty or outcomes is None or outcomes.empty or "record_id" not in rec.columns:
        return pd.DataFrame()
    out = outcomes[outcomes.get("horizon", pd.Series(dtype=str)).astype(str).eq(str(horizon))].copy()
    if out.empty or "record_id" not in out.columns or "return_pct" not in out.columns:
        return pd.DataFrame()
    keep = [c for c in ["record_id", "symbol", "captured_date", "captured_at", "snapshot_json", "gate", "market"] if c in rec.columns]
    merged = rec[keep].merge(out, on="record_id", how="inner", suffixes=("", "_out"))
    merged["return_pct"] = pd.to_numeric(merged["return_pct"], errors="coerce")
    if "excess_return_pct" in merged.columns:
        merged["excess_return_pct"] = pd.to_numeric(merged["excess_return_pct"], errors="coerce")
    merged = merged.dropna(subset=["return_pct"]).copy()
    if merged.empty:
        return merged
    merged = independent_case_sample(merged, str(horizon)).copy()
    merged["_snap"] = merged["snapshot_json"].map(_snapshot) if "snapshot_json" in merged.columns else [{} for _ in range(len(merged))]
    merged["_target"] = merged["_snap"].map(spec.target).astype(bool)
    merged["_requirement"] = merged["_snap"].map(spec.requirement).astype(bool)
    return merged


def _row(control: str, status: str, n: int, detail: str, **extra: Any) -> dict[str, Any]:
    return {"Kontroll": control, "Status": status, "N": int(n), "Detalj": detail, **extra}


def runtime_integrity(db_path: str, app_version: str) -> dict[str, Any]:
    summary = policy_registry_summary(db_path, app_version)
    if not summary.get("definition_matches_runtime"):
        return _row(
            "Runtime-integritet", "Varning", 1,
            "Registrerad produktionspolicy och körd release har olika fingerprint. Utfall ska inte tolkas som ett rent policytest innan detta är löst.",
            severe=True,
        )
    return _row("Runtime-integritet", "OK", 1, "Körd policydefinition matchar produktionsregistret.", severe=False)


def policy_effect_health(sample: pd.DataFrame, horizon: str) -> dict[str, Any]:
    target = sample[sample.get("_target", False)].copy() if sample is not None and not sample.empty else pd.DataFrame()
    if len(target) < MIN_TARGET:
        return _row(f"Policyutfall {horizon}", "Vänta", len(target), f"Minst {MIN_TARGET} oberoende target-case efter aktivering krävs.")
    metric, label = _outcome_basis(target)
    ok = pd.to_numeric(target.loc[target["_requirement"], metric], errors="coerce").dropna()
    filtered = pd.to_numeric(target.loc[~target["_requirement"], metric], errors="coerce").dropna()
    if len(ok) < MIN_GROUP or len(filtered) < MIN_GROUP:
        return _row(f"Policyutfall {horizon}", "Vänta", len(target), f"Minst {MIN_GROUP} case med respektive utan det extra kravet krävs.")
    gap = float(ok.median() - filtered.median())
    hit_gap = float((ok > 0).mean() - (filtered > 0).mean())
    if gap <= -SUPPORT_GAP:
        status = "Varning"
    elif gap < 0 or hit_gap <= -0.10:
        status = "Bevaka"
    else:
        status = "OK"
    return _row(
        f"Policyutfall {horizon}", status, len(target),
        f"Case som klarade kravet: median {ok.median()*100:.1f}%; filtrerade target-case: {filtered.median()*100:.1f}% ({label}). Skillnad {gap*100:+.1f} pp.",
        gap=gap, hit_gap=hit_gap,
    )


def opportunity_cost_health(sample: pd.DataFrame, horizon: str) -> dict[str, Any]:
    target = sample[sample.get("_target", False)].copy() if sample is not None and not sample.empty else pd.DataFrame()
    filtered = target[~target.get("_requirement", False)].copy() if not target.empty else pd.DataFrame()
    if len(filtered) < MIN_GROUP:
        return _row(f"Missade vinnare {horizon}", "Vänta", len(filtered), f"Minst {MIN_GROUP} filtrerade target-case med moget utfall krävs.")
    metric, label = _outcome_basis(filtered)
    values = pd.to_numeric(filtered[metric], errors="coerce").dropna()
    if len(values) < MIN_GROUP:
        return _row(f"Missade vinnare {horizon}", "Vänta", len(values), "För få kompletta utfall bland filtrerade case.")
    winner_rate = float((values >= STRONG_WINNER).mean())
    median = float(values.median())
    if winner_rate >= 0.40 and median > 0:
        status = "Varning"
    elif winner_rate >= 0.25 or median >= 0.03:
        status = "Bevaka"
    else:
        status = "OK"
    return _row(
        f"Missade vinnare {horizon}", status, len(values),
        f"Av target-case som policyn skulle filtrera bort nådde {winner_rate*100:.0f}% minst +{STRONG_WINNER*100:.0f}% ({label}); median {median*100:.1f}%. Detta mäter alternativkostnad, inte bevisad felklassning.",
        winner_rate=winner_rate, median=median,
    )


def selectivity_health(recommendations: pd.DataFrame, event: dict[str, Any], spec) -> dict[str, Any]:
    rec = _after_activation(recommendations, event)
    if rec.empty or "snapshot_json" not in rec.columns:
        return _row("Urvalsgrad", "Vänta", 0, "Inga policyrelevanta snapshots efter aktiveringen ännu.")
    snaps = rec["snapshot_json"].map(_snapshot)
    target = snaps.map(spec.target).astype(bool)
    n_target = int(target.sum())
    if n_target < MIN_TARGET:
        return _row("Urvalsgrad", "Vänta", n_target, f"Minst {MIN_TARGET} target-case krävs för att bedöma hur hårt policyn filtrerar.")
    target_snaps = snaps[target]
    keep = target_snaps.map(spec.requirement).astype(bool)
    filter_rate = float((~keep).mean())
    if filter_rate >= WARN_FILTER_RATE:
        status = "Varning"
    elif filter_rate >= WATCH_FILTER_RATE:
        status = "Bevaka"
    else:
        status = "OK"
    return _row("Urvalsgrad", status, n_target, f"Det extra kravet skulle filtrera {filter_rate*100:.0f}% av relevanta target-case efter aktivering.", filter_rate=filter_rate)


def data_coverage_health(recommendations: pd.DataFrame, event: dict[str, Any], spec) -> dict[str, Any]:
    rec = _after_activation(recommendations, event)
    if rec.empty or "snapshot_json" not in rec.columns:
        return _row("Policydata", "Vänta", 0, "Ingen fryst policydata efter aktiveringen ännu.")
    snaps = rec["snapshot_json"].map(_snapshot)
    # A policy is evaluable only when target/requirement functions return a stable bool;
    # additionally require PIT Complete to avoid interpreting missing fields as a real negative.
    target_flags = snaps.map(spec.target).astype(bool)
    target_snaps = snaps[target_flags]
    if len(target_snaps) < MIN_TARGET:
        return _row("Policydata", "Vänta", len(target_snaps), f"Minst {MIN_TARGET} target-case krävs för datatäckningskontroll.")
    pit = target_snaps.map(lambda s: bool(s.get("PIT Complete")) if s.get("PIT Complete") is not None else False)
    rate = float(pit.mean())
    status = "Varning" if rate < MIN_COVERAGE else "Bevaka" if rate < 0.96 else "OK"
    return _row("Policydata", status, len(target_snaps), f"PIT-komplett underlag i {rate*100:.0f}% av target-casen efter aktivering.", coverage=rate)


def regime_health(sample: pd.DataFrame, horizon: str) -> dict[str, Any]:
    target = sample[sample.get("_target", False)].copy() if sample is not None and not sample.empty else pd.DataFrame()
    if target.empty:
        return _row(f"Regimrobusthet {horizon}", "Vänta", 0, "Inga mogna target-case efter aktivering.")
    target["_regime"] = target["_snap"].map(lambda s: str(s.get("Marknadsläge") or "").upper().replace(" MARKNAD", "").strip())
    metric, _ = _outcome_basis(target)
    evaluated = []
    for regime, group in target.groupby("_regime"):
        ok = pd.to_numeric(group.loc[group["_requirement"], metric], errors="coerce").dropna()
        no = pd.to_numeric(group.loc[~group["_requirement"], metric], errors="coerce").dropna()
        if len(ok) >= 4 and len(no) >= 4:
            evaluated.append((regime, len(group), float(ok.median() - no.median())))
    if len(evaluated) < 2:
        return _row(f"Regimrobusthet {horizon}", "Vänta", len(target), "Minst två policyrelevanta frysta marknadslägen med 4+4 case vardera krävs.")
    worst = min(evaluated, key=lambda x: x[2])
    status = "Varning" if worst[2] <= -SUPPORT_GAP else "Bevaka" if worst[2] < 0 else "OK"
    return _row(f"Regimrobusthet {horizon}", status, sum(x[1] for x in evaluated), f"Svagaste mogna regim är {worst[0]}: policygap {worst[2]*100:+.1f} pp. {len(evaluated)} regimer kan jämföras.", worst_gap=worst[2])


def policy_health_table(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    db_path: str,
    app_version: str,
) -> pd.DataFrame:
    integrity = runtime_integrity(db_path, app_version)
    event = current_policy(db_path)
    rows = [integrity]
    if not event:
        rows.append(_row("Aktiv policy", "Vänta", 0, "Ingen produktionspolicy är registrerad ännu."))
    elif str(event.get("policy_id")) == DEFAULT_POLICY_ID:
        rows.append(_row("Aktiv policy", "OK", 0, "Baseline-policyn är aktiv. Det finns ännu inget extra urvalskrav att mäta efter driftsättning."))
    else:
        _, spec = _active_spec(str(event.get("policy_id")))
        if spec is None:
            rows.append(_row("Aktiv policy", "Varning", 0, "Den aktiva policydefinitionen kan inte kopplas till en låst policyhypotes. Hälsomätningen blockeras."))
        else:
            rows.append(selectivity_health(recommendations, event, spec))
            rows.append(data_coverage_health(recommendations, event, spec))
            for horizon in ("1m", "3m"):
                sample = _policy_sample(recommendations, outcomes, event, horizon, spec)
                rows.append(policy_effect_health(sample, horizon))
                rows.append(opportunity_cost_health(sample, horizon))
            rows.append(regime_health(_policy_sample(recommendations, outcomes, event, "1m", spec), "1m"))
    cols = ["Kontroll", "Status", "N", "Detalj"]
    return pd.DataFrame([{c: r.get(c) for c in cols} for r in rows], columns=cols)


def policy_health_summary(table: pd.DataFrame) -> dict[str, Any]:
    if table is None or table.empty:
        return {"status": "Vänta", "text": "Ingen policyhälsa kan mätas ännu.", "automatic_rollback": False}
    statuses = table["Status"].astype(str)
    runtime_bad = bool(((table["Kontroll"] == "Runtime-integritet") & (statuses == "Varning")).any())
    warnings = int((statuses == "Varning").sum())
    watches = int((statuses == "Bevaka").sum())
    outcome_warning = bool(table["Kontroll"].astype(str).str.startswith(("Policyutfall", "Missade vinnare")).where(statuses.eq("Varning"), False).any())
    baseline = bool(((table["Kontroll"] == "Aktiv policy") & table["Detalj"].astype(str).str.contains("Baseline", case=False, na=False)).any())
    if runtime_bad:
        status = "Granska release"
        text = "Policyregistret och den körda releasen matchar inte. Lös definitionsavvikelsen innan policyutfall används för beslut."
    elif warnings >= 2 and outcome_warning:
        status = "Granska rollback"
        text = "Den aktiva policyn visar flera samtidiga varningar, inklusive utfall eller missade vinnare. Gör en manuell rollback- och rotorsaksprövning."
    elif warnings >= 1 or watches >= 2:
        status = "Bevaka noga"
        text = "Den aktiva policyn visar tecken som bör följas tätare, men underlaget räcker inte för automatisk eller omedelbar rollback."
    elif baseline:
        status = "Baseline"
        text = "Nuvarande baseline-policy är registrerad och matchar runtime. Ingen ny extra policy är driftsatt att utvärdera ännu."
    elif int(statuses.isin(["OK", "Bevaka", "Varning"]).sum()) <= 1:
        status = "Vänta"
        text = "För lite mogen post-activation-historik för att bedöma policyhälsan."
    else:
        status = "Stabil"
        text = "Ingen tydlig samtidig försämring syns i den aktiva policyns mogna kontroller. Det är inte bevis på framtida effekt."
    return {"status": status, "text": text, "warnings": warnings, "watches": watches, "automatic_rollback": False}
