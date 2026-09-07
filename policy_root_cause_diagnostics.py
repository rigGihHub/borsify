from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

from policy_health_monitor import _active_spec, _after_activation, _policy_sample
from production_policy_registry import DEFAULT_POLICY_ID, current_policy, policy_registry_summary

MIN_FILTERED = 6
MIN_REGIME = 5
MIN_COHORT = 4
STRONG_WINNER = 0.08
HIGH_MISS_RATE = 0.40
POSSIBLE_MISS_RATE = 0.25
MIN_PIT_COVERAGE = 0.90


def _snapshot(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        val = json.loads(str(raw or "{}"))
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _metric(frame: pd.DataFrame) -> tuple[str, str]:
    if frame is not None and not frame.empty and "excess_return_pct" in frame.columns:
        x = pd.to_numeric(frame["excess_return_pct"], errors="coerce")
        if x.notna().all():
            return "excess_return_pct", "mot index"
    return "return_pct", "rå kursutveckling"


def _row(category: str, candidate: str, status: str, n: int, detail: str, priority: int = 0) -> dict[str, Any]:
    return {"Område": category, "Diagnostisk kandidat": candidate, "Status": status, "N": int(n), "Detalj": detail, "_priority": int(priority)}


def strictness_diagnostic(sample: pd.DataFrame) -> dict[str, Any]:
    if sample is None or sample.empty or "_target" not in sample.columns or "_requirement" not in sample.columns:
        return _row("Urvalsgrad", "För hård policy generellt", "För lite historik", 0, "Inga mogna target-case efter policyaktivering.")
    target = sample[sample["_target"]].copy()
    if len(target) < 12:
        return _row("Urvalsgrad", "För hård policy generellt", "För lite historik", len(target), "Minst 12 mogna target-case krävs för denna diagnostik.")
    rate = float((~target["_requirement"].astype(bool)).mean())
    if rate >= 0.85:
        return _row("Urvalsgrad", "För hård policy generellt", "Stark kandidat", len(target), f"Policyn filtrerar {rate*100:.0f}% av mogna target-case. Det kan vara ett tecken på att extra kravet är för brett eller för hårt.", 3)
    if rate >= 0.70:
        return _row("Urvalsgrad", "För hård policy generellt", "Möjlig", len(target), f"Policyn filtrerar {rate*100:.0f}% av mogna target-case. Följ alternativkostnaden innan någon regel ändras.", 2)
    return _row("Urvalsgrad", "För hård policy generellt", "Ingen tydlig signal", len(target), f"Policyn filtrerar {rate*100:.0f}% av mogna target-case.")


def filtered_winner_diagnostic(sample: pd.DataFrame) -> dict[str, Any]:
    if sample is None or sample.empty:
        return _row("Alternativkostnad", "Bra case filtreras bort", "För lite historik", 0, "Inga mogna policycase.")
    target = sample[sample.get("_target", False)].copy()
    filtered = target[~target.get("_requirement", False).astype(bool)].copy() if not target.empty else pd.DataFrame()
    if len(filtered) < MIN_FILTERED:
        return _row("Alternativkostnad", "Bra case filtreras bort", "För lite historik", len(filtered), f"Minst {MIN_FILTERED} filtrerade case krävs.")
    metric, label = _metric(filtered)
    vals = pd.to_numeric(filtered[metric], errors="coerce").dropna()
    if len(vals) < MIN_FILTERED:
        return _row("Alternativkostnad", "Bra case filtreras bort", "För lite historik", len(vals), "För få kompletta utfall.")
    rate = float((vals >= STRONG_WINNER).mean())
    med = float(vals.median())
    if rate >= HIGH_MISS_RATE and med > 0:
        status, p = "Stark kandidat", 3
    elif rate >= POSSIBLE_MISS_RATE or med >= 0.03:
        status, p = "Möjlig", 2
    else:
        status, p = "Ingen tydlig signal", 0
    return _row("Alternativkostnad", "Bra case filtreras bort", status, len(vals), f"{rate*100:.0f}% av filtrerade case blev starka vinnare och nådde minst +{STRONG_WINNER*100:.0f}% ({label}); median {med*100:.1f}%. Association, inte bevisad felklassning.", p)


def regime_miss_diagnostics(sample: pd.DataFrame) -> list[dict[str, Any]]:
    if sample is None or sample.empty or "_snap" not in sample.columns:
        return []
    target = sample[sample.get("_target", False)].copy()
    if target.empty:
        return []
    target["_regime"] = target["_snap"].map(lambda s: str((s or {}).get("Marknadsläge") or "OKÄND").upper())
    metric, label = _metric(target)
    rows: list[dict[str, Any]] = []
    for regime, group in target.groupby("_regime"):
        filtered = group[~group["_requirement"].astype(bool)].copy()
        if len(filtered) < MIN_REGIME:
            continue
        vals = pd.to_numeric(filtered[metric], errors="coerce").dropna()
        if len(vals) < MIN_REGIME:
            continue
        miss = float((vals >= STRONG_WINNER).mean())
        median = float(vals.median())
        if miss >= HIGH_MISS_RATE and median > 0:
            status, p = "Stark kandidat", 3
        elif miss >= POSSIBLE_MISS_RATE or median >= 0.03:
            status, p = "Möjlig", 2
        else:
            status, p = "Ingen tydlig signal", 0
        rows.append(_row("Marknadsläge", f"Filtreringsproblem i {regime}", status, len(vals), f"Bland filtrerade target-case i {regime} blev {miss*100:.0f}% starka vinnare; median {median*100:.1f}% ({label}).", p))
    return rows


def failure_cohort_diagnostics(sample: pd.DataFrame) -> list[dict[str, Any]]:
    if sample is None or sample.empty or "_snap" not in sample.columns:
        return []
    target = sample[sample.get("_target", False)].copy()
    filtered = target[~target.get("_requirement", False).astype(bool)].copy() if not target.empty else pd.DataFrame()
    if len(filtered) < MIN_FILTERED:
        return []
    metric, label = _metric(filtered)
    defs = [
        ("Starkt momentum", lambda s: _num(s.get("Short Momentum")) >= 70),
        ("Stark katalysator/revision", lambda s: max(_num(s.get("Short Catalyst")), _num(s.get("Short Revisions"))) >= 65),
        ("Stark kursbekräftelse", lambda s: max(_num(s.get("Short Trend")), _num(s.get("Short Relative Strength"))) >= 65),
        ("Brett oberoende stöd", lambda s: _num(s.get("Evidence Family Support Count")) >= 3),
    ]
    rows: list[dict[str, Any]] = []
    for name, fn in defs:
        mask = filtered["_snap"].map(fn).astype(bool)
        group = pd.to_numeric(filtered.loc[mask, metric], errors="coerce").dropna()
        if len(group) < MIN_COHORT:
            continue
        win = float((group >= STRONG_WINNER).mean())
        med = float(group.median())
        if win >= 0.50 and med > 0:
            status, p = "Stark kandidat", 3
        elif win >= 0.30 or med >= 0.03:
            status, p = "Möjlig", 2
        else:
            status, p = "Ingen tydlig signal", 0
        rows.append(_row("Case-typ", f"Policyn filtrerar bort {name.lower()}", status, len(group), f"I denna filtrerade case-typ blev {win*100:.0f}% starka vinnare; median {med*100:.1f}% ({label}).", p))
    return rows


def data_diagnostic(recommendations: pd.DataFrame, event: dict[str, Any], spec) -> dict[str, Any]:
    rec = _after_activation(recommendations, event)
    if rec.empty or "snapshot_json" not in rec.columns:
        return _row("Data", "Databrist misstolkas som policyeffekt", "För lite historik", 0, "Ingen fryst policydata efter aktiveringen.")
    snaps = rec["snapshot_json"].map(_snapshot)
    target = snaps[snaps.map(spec.target).astype(bool)]
    if len(target) < 12:
        return _row("Data", "Databrist misstolkas som policyeffekt", "För lite historik", len(target), "Minst 12 target-case krävs.")
    coverage = float(target.map(lambda s: bool(s.get("PIT Complete"))).mean())
    if coverage < MIN_PIT_COVERAGE:
        return _row("Data", "Databrist misstolkas som policyeffekt", "Stark kandidat", len(target), f"Bara {coverage*100:.0f}% av target-casen har komplett PIT-underlag. Fixa data före policyändring.", 3)
    if coverage < 0.96:
        return _row("Data", "Databrist misstolkas som policyeffekt", "Möjlig", len(target), f"PIT-täckningen är {coverage*100:.0f}%. Databrist kan påverka policyutvärderingen.", 2)
    return _row("Data", "Databrist misstolkas som policyeffekt", "Ingen tydlig signal", len(target), f"PIT-täckningen är {coverage*100:.0f}%.")


def policy_root_cause_table(recommendations: pd.DataFrame, outcomes: pd.DataFrame, db_path: str, app_version: str, horizon: str = "1m") -> pd.DataFrame:
    cols = ["Område", "Diagnostisk kandidat", "Status", "N", "Detalj"]
    registry = policy_registry_summary(db_path, app_version)
    event = current_policy(db_path)
    if event is None:
        return pd.DataFrame([_row("Policy", "Ingen aktiv policy", "För lite historik", 0, "Policyregistret är tomt.")])[cols]
    if not registry.get("definition_matches_runtime"):
        return pd.DataFrame([_row("Release", "Policydefinition matchar inte runtime", "Stark kandidat", 1, "Lös fingerprint-avvikelsen innan rotorsaksanalys av policyutfall görs.", 3)])[cols]
    if str(event.get("policy_id")) == DEFAULT_POLICY_ID:
        return pd.DataFrame([_row("Policy", "Baseline aktiv", "Ingen aktiv avvikelse", 0, "Ingen skärpt policy är driftsatt ännu; därför finns ingen policyspecifik rotorsak att diagnostisera.")])[cols]
    _, spec = _active_spec(str(event.get("policy_id")))
    if spec is None:
        return pd.DataFrame([_row("Policy", "Okänd policydefinition", "Stark kandidat", 1, "Aktiv policy kan inte kopplas till en låst förregistrerad definition.", 3)])[cols]
    sample = _policy_sample(recommendations, outcomes, event, horizon, spec)
    rows = [strictness_diagnostic(sample), filtered_winner_diagnostic(sample), data_diagnostic(recommendations, event, spec)]
    rows.extend(regime_miss_diagnostics(sample))
    rows.extend(failure_cohort_diagnostics(sample))
    rows = sorted(rows, key=lambda r: (-int(r.get("_priority", 0)), str(r.get("Område", "")), str(r.get("Diagnostisk kandidat", ""))))
    return pd.DataFrame([{c: r.get(c) for c in cols} for r in rows], columns=cols)


def policy_root_cause_summary(table: pd.DataFrame) -> dict[str, Any]:
    if table is None or table.empty:
        return {"status": "Vänta", "text": "Ingen policyspecifik rotorsak kan bedömas ännu.", "automatic_change": False}
    statuses = table["Status"].astype(str)
    strong = int((statuses == "Stark kandidat").sum())
    possible = int((statuses == "Möjlig").sum())
    baseline = bool((statuses == "Ingen aktiv avvikelse").any())
    if strong:
        status = "Stark kandidat hittad"
        text = f"{strong} stark diagnostisk kandidat hittades. Kontrollera den före rollback eller policyändring; detta är association, inte kausalitet."
    elif possible:
        status = "Möjlig förklaring"
        text = f"{possible} möjlig diagnostisk förklaring hittades, men underlaget räcker inte för att ändra policyn."
    elif baseline:
        status = "Baseline"
        text = "Ingen skärpt policy är aktiv ännu, så policyspecifik rotorsaksdiagnostik väntar."
    elif (statuses == "För lite historik").all():
        status = "Vänta"
        text = "För lite mogen post-activation-historik för att isolera en policyspecifik rotorsak."
    else:
        status = "Ingen tydlig rotorsak"
        text = "Ingen tydlig koncentrerad policyspecifik rotorsak syns i nuvarande mogna underlag."
    return {"status": status, "text": text, "strong": strong, "possible": possible, "automatic_change": False}
