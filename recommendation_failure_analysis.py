from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _snapshot(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw or "{}"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _failure_metric(row: pd.Series) -> tuple[float, str]:
    excess = _num(row.get("excess_return_pct"))
    if np.isfinite(excess):
        return excess, "Mot index"
    return _num(row.get("return_pct")), "Rå kursutveckling"


def warning_signal_states(snapshot: dict[str, Any], horizon_type: str) -> dict[str, tuple[str, bool | None]]:
    """Return frozen warning signals as tri-state values.

    True means the warning was present, False means the stored field clearly shows it
    was not present, and None means the old snapshot does not contain enough
    information to judge. Missing historical fields must never be treated as a clean
    bill of health.
    """
    signals: dict[str, tuple[str, bool | None]] = {}

    def add(key: str, label: str, state: bool | None) -> None:
        signals[key] = (label, state)

    if horizon_type == "long":
        trap = _num(snapshot.get("Value Trap Risk"))
        add("value_trap", "Hög risk för värdefälla", bool(trap >= 50) if np.isfinite(trap) else None)

        deep = str(snapshot.get("Djupkontroll") or "")
        add("deep_check", "Djupkontrollen var inte ren", (deep not in {"Klarar djupkontroll", "Neutral djupkontroll"}) if deep else None)

        evidence = _num(snapshot.get("Case Evidence Count"))
        add("few_evidence", "Få oberoende stöd", bool(evidence <= 3) if np.isfinite(evidence) else None)

        veto = _num(snapshot.get("Case Veto Count"))
        add("veto", "Tydlig invändning/veto", bool(veto > 0) if np.isfinite(veto) else None)

        fstatus = str(snapshot.get("Fundamental Data status") or "")
        add("fundamental_data", "Svag fundamentaldatakvalitet", fstatus in {"STOPP", "ANVÄNDBART MED VARNING"} if fstatus else None)

        eq = str(snapshot.get("Vinstkvalitet status") or "")
        add("earnings_quality", "Svag vinstkvalitet", ("SVAG" in eq.upper()) if eq else None)

        catalyst = str(snapshot.get("Catalyst Signal") or "")
        add("weak_catalyst", "Svagt eller overifierat varför nu", catalyst in {"Ingen tydlig katalysator verifierad", "Närliggande kontrollpunkt"} if catalyst else None)

        mispricing = str(snapshot.get("Mispricing Signal") or "")
        add("uncertain_mispricing", "Osäker felprissättning", ("rimlig" in mispricing.lower() or "svag" in mispricing.lower()) if mispricing else None)
    else:
        confirmations = _num(snapshot.get("Short Confirmation Count"))
        add("few_confirmations", "Få kortsiktiga bekräftelser", bool(confirmations <= 2) if np.isfinite(confirmations) else None)

        catalyst = _num(snapshot.get("Short Catalyst"))
        add("weak_short_catalyst", "Svag kortsiktig katalysator", bool(catalyst < 50) if np.isfinite(catalyst) else None)

        relative = _num(snapshot.get("Short Relative Strength"))
        add("weak_relative_strength", "Svag relativ styrka", bool(relative < 50) if np.isfinite(relative) else None)

        trend = _num(snapshot.get("Short Trend"))
        add("weak_trend", "Svag trend", bool(trend < 50) if np.isfinite(trend) else None)

        participation = _num(snapshot.get("Short Participation"))
        add("weak_participation", "Svagt handelsdeltagande/volymstöd", bool(participation < 45) if np.isfinite(participation) else None)

        counter = str(snapshot.get("Short Counterargument") or "")
        add("counterargument", "Tydligt motargument", (counter != "—") if counter else None)

    return signals


def _weaknesses(snapshot: dict[str, Any], horizon_type: str) -> list[str]:
    """Human-readable warnings frozen at recommendation time."""
    states = warning_signal_states(snapshot, horizon_type)
    return [label for label, state in states.values() if state is True]


def failure_pattern_analysis(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
    *,
    raw_failure_threshold: float = -0.10,
    relative_failure_threshold: float = -0.05,
    min_exposed: int = 5,
    min_unexposed: int = 5,
) -> pd.DataFrame:
    """Compare failure frequency with vs without each frozen warning signal.

    This deliberately uses one outcome basis for the whole selected cohort. If every
    observation has benchmark-relative data, excess return is used. Otherwise raw
    return is used for everyone. This avoids mixing definitions inside the same
    pattern comparison. Missing snapshot fields are excluded signal-by-signal rather
    than counted as absence.
    """
    cols = [
        "Signal", "Exponerade", "Misslyckade med signal", "Misslyckandegrad med signal",
        "Utan signal", "Misslyckandegrad utan signal", "Skillnad procentenheter",
        "Medianutfall med signal", "Medianutfall utan signal", "Mätning", "Status",
    ]
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame(columns=cols)
    required_rec = {"record_id", "horizon_type", "snapshot_json"}
    required_out = {"record_id", "horizon", "return_pct"}
    if not required_rec.issubset(recommendations.columns) or not required_out.issubset(outcomes.columns):
        return pd.DataFrame(columns=cols)

    outs = outcomes[outcomes["horizon"].astype(str).eq(str(horizon))].copy()
    if outs.empty:
        return pd.DataFrame(columns=cols)
    merged = outs.merge(recommendations[["record_id", "horizon_type", "snapshot_json"]], on="record_id", how="inner")
    if merged.empty:
        return pd.DataFrame(columns=cols)
    raw = pd.to_numeric(merged["return_pct"], errors="coerce")
    rel = pd.to_numeric(merged.get("excess_return_pct"), errors="coerce") if "excess_return_pct" in merged.columns else pd.Series(np.nan, index=merged.index)
    use_relative = bool(rel.notna().all())
    metric = rel if use_relative else raw
    merged = merged.assign(_metric=metric).dropna(subset=["_metric"]).copy()
    if merged.empty:
        return pd.DataFrame(columns=cols)
    threshold = relative_failure_threshold if use_relative else raw_failure_threshold
    merged["_failed"] = merged["_metric"] <= threshold

    all_keys: dict[str, str] = {}
    per_row: list[dict[str, tuple[str, bool | None]]] = []
    for _, row in merged.iterrows():
        states = warning_signal_states(_snapshot(row.get("snapshot_json")), str(row.get("horizon_type") or ""))
        per_row.append(states)
        for key, (label, _) in states.items():
            all_keys[key] = label

    rows: list[dict[str, Any]] = []
    for key, label in all_keys.items():
        states = [d.get(key, (label, None))[1] for d in per_row]
        work = merged[["_metric", "_failed"]].copy()
        work["_state"] = states
        work = work[work["_state"].notna()].copy()
        if work.empty:
            continue
        exposed = work[work["_state"] == True]
        clean = work[work["_state"] == False]
        n_exp, n_clean = len(exposed), len(clean)
        exp_rate = float(exposed["_failed"].mean()) if n_exp else np.nan
        clean_rate = float(clean["_failed"].mean()) if n_clean else np.nan
        diff_pp = (exp_rate - clean_rate) * 100 if np.isfinite(exp_rate) and np.isfinite(clean_rate) else np.nan
        enough = n_exp >= min_exposed and n_clean >= min_unexposed
        pattern = enough and int(exposed["_failed"].sum()) >= 3 and diff_pp >= 15
        status = "Möjligt återkommande mönster" if pattern else ("Kan följas" if enough else "För lite underlag")
        rows.append({
            "Signal": label,
            "Exponerade": int(n_exp),
            "Misslyckade med signal": int(exposed["_failed"].sum()) if n_exp else 0,
            "Misslyckandegrad med signal": exp_rate,
            "Utan signal": int(n_clean),
            "Misslyckandegrad utan signal": clean_rate,
            "Skillnad procentenheter": diff_pp,
            "Medianutfall med signal": float(exposed["_metric"].median()) if n_exp else np.nan,
            "Medianutfall utan signal": float(clean["_metric"].median()) if n_clean else np.nan,
            "Mätning": "Mot index" if use_relative else "Rå kursutveckling",
            "Status": status,
        })
    if not rows:
        return pd.DataFrame(columns=cols)
    result = pd.DataFrame(rows, columns=cols)
    rank = {"Möjligt återkommande mönster": 0, "Kan följas": 1, "För lite underlag": 2}
    result["_rank"] = result["Status"].map(rank).fillna(3)
    result["_diff"] = pd.to_numeric(result["Skillnad procentenheter"], errors="coerce").fillna(-999)
    return result.sort_values(["_rank", "_diff", "Exponerade"], ascending=[True, False, False]).drop(columns=["_rank", "_diff"]).reset_index(drop=True)


def failure_pattern_overview(patterns: pd.DataFrame) -> dict[str, Any]:
    if patterns is None or patterns.empty:
        return {"status": "För lite historik", "count": 0, "text": "Det finns ännu inte tillräckligt med jämförbara historiska signaler."}
    usable = patterns[patterns["Status"].isin(["Möjligt återkommande mönster", "Kan följas"])]
    flagged = patterns[patterns["Status"] == "Möjligt återkommande mönster"]
    if not flagged.empty:
        top = flagged.iloc[0]
        return {
            "status": "Möjligt återkommande mönster",
            "count": int(len(flagged)),
            "text": (f"{len(flagged)} varningssignal(er) återkommer oftare i tydligt svaga utfall än i jämförelsegruppen. "
                     f"Störst skillnad just nu gäller '{top['Signal']}'. Detta är en historisk association, inte bevis på orsak."),
        }
    if not usable.empty:
        return {"status": "Historik finns – inget tydligt mönster ännu", "count": int(len(usable)),
                "text": "Det finns jämförbara grupper, men ingen varningssignal skiljer sig tillräckligt tydligt ännu."}
    return {"status": "För lite historik", "count": 0,
            "text": "Varningssignaler finns i historiken, men för få case med och utan respektive signal för en rimlig jämförelse."}

def failed_recommendation_analysis(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
    *,
    raw_failure_threshold: float = -0.10,
    relative_failure_threshold: float = -0.05,
) -> pd.DataFrame:
    """Return diagnostic rows for materially weak historical outcomes.

    When benchmark-relative data exists for an observation, a case is considered weak
    when it underperformed the benchmark by at least 5 percentage points. Otherwise the
    fallback is a raw loss of at least 10%. The thresholds are intentionally descriptive,
    not model gates.
    """
    cols = [
        "Ticker", "Bolag", "Datum", "Utfall", "Mätning", "Svagaste signaler",
        "Diagnosstatus", "Version",
    ]
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame(columns=cols)
    required_rec = {"record_id", "symbol", "name", "captured_date", "horizon_type", "model_version", "snapshot_json"}
    required_out = {"record_id", "horizon", "return_pct"}
    if not required_rec.issubset(recommendations.columns) or not required_out.issubset(outcomes.columns):
        return pd.DataFrame(columns=cols)

    outs = outcomes[outcomes["horizon"].astype(str).eq(str(horizon))].copy()
    if outs.empty:
        return pd.DataFrame(columns=cols)
    merged = outs.merge(
        recommendations[list(required_rec)], on="record_id", how="inner"
    )
    rows: list[dict[str, Any]] = []
    for _, row in merged.iterrows():
        metric, basis = _failure_metric(row)
        if not np.isfinite(metric):
            continue
        threshold = relative_failure_threshold if basis == "Mot index" else raw_failure_threshold
        if metric > threshold:
            continue
        snap = _snapshot(row.get("snapshot_json"))
        reasons = _weaknesses(snap, str(row.get("horizon_type") or ""))
        if reasons:
            reason_text = " · ".join(reasons[:3])
            status = "Möjliga svagheter fanns redan"
        else:
            reason_text = "Ingen tydlig förvarning finns i den frysta data som sparades då"
            status = "Orsak kan inte utläsas"
        rows.append({
            "Ticker": str(row.get("symbol") or ""),
            "Bolag": str(row.get("name") or row.get("symbol") or ""),
            "Datum": str(row.get("captured_date") or "")[:10],
            "Utfall": float(metric),
            "Mätning": basis,
            "Svagaste signaler": reason_text,
            "Diagnosstatus": status,
            "Version": str(row.get("model_version") or ""),
        })
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows, columns=cols).sort_values("Utfall", ascending=True).reset_index(drop=True)


def failure_pattern_summary(failures: pd.DataFrame) -> dict[str, Any]:
    if failures is None or failures.empty:
        return {
            "status": "Inga tydliga misslyckanden i vald period",
            "count": 0,
            "text": "Det finns inga mogna utfall som passerar Borsifys försiktiga gräns för ett tydligt svagt case.",
        }
    count = int(len(failures))
    diagnosable = int((failures["Diagnosstatus"] == "Möjliga svagheter fanns redan").sum())
    return {
        "status": "Diagnostik finns",
        "count": count,
        "diagnosable": diagnosable,
        "text": (
            f"{count} tydligt svaga utfall finns i den valda perioden. I {diagnosable} av dem "
            "fanns minst en varningssignal redan i den frysta rekommendationsdatan. "
            "Det visar möjliga missar i beslutsunderlaget, inte bevis på vad som orsakade kursutfallet."
        ),
    }
