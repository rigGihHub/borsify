from __future__ import annotations

import json
import math
from typing import Any, Callable

import numpy as np
import pandas as pd

from independent_case_validation import independent_case_sample

WINDOW = 12
MIN_COHORT = 4
MIN_TOTAL = WINDOW * 2
STRONG_GAP = 0.08
POSSIBLE_GAP = 0.04


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


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_warning(value: Any) -> bool:
    t = _text(value)
    return any(k in t for k in ("varning", "svag", "hög", "mycket hög", "kräver kontroll", "kapitalbindning ökar"))


def _is_positive(value: Any) -> bool:
    t = _text(value)
    return any(k in t for k in ("positiv", "stark", "stöd", "effektiv", "bra")) and not _is_warning(value)


def _outcome_basis(frame: pd.DataFrame) -> tuple[str, str]:
    if "excess_return_pct" in frame.columns:
        s = pd.to_numeric(frame["excess_return_pct"], errors="coerce")
        if len(s) and s.notna().all():
            return "excess_return_pct", "Mot index"
    return "return_pct", "Rå kursutveckling"


def prepare_failure_cohort_sample(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str = "1m",
    horizon_type: str = "short",
) -> pd.DataFrame:
    """Build a point-in-time independent sample for failure-cohort attribution."""
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame()
    if not {"record_id", "horizon_type", "snapshot_json"}.issubset(recommendations.columns):
        return pd.DataFrame()
    if not {"record_id", "horizon", "return_pct"}.issubset(outcomes.columns):
        return pd.DataFrame()
    kind = str(horizon_type).lower().strip()
    rec = recommendations[recommendations["horizon_type"].astype(str).str.lower().eq(kind)].copy()
    out = outcomes[outcomes["horizon"].astype(str).eq(str(horizon))].copy()
    keep = [c for c in ["record_id", "symbol", "captured_date", "market", "score", "snapshot_json", "model_version"] if c in rec.columns]
    merged = rec[keep].merge(out, on="record_id", how="inner", suffixes=("", "_out"))
    if merged.empty:
        return merged
    merged["return_pct"] = pd.to_numeric(merged["return_pct"], errors="coerce")
    if "excess_return_pct" in merged.columns:
        merged["excess_return_pct"] = pd.to_numeric(merged["excess_return_pct"], errors="coerce")
    merged = merged.dropna(subset=["return_pct"]).copy()
    if merged.empty:
        return merged
    merged["_snap"] = merged["snapshot_json"].map(_snapshot)
    return independent_case_sample(merged, str(horizon)).sort_values("captured_date", kind="stable").reset_index(drop=True)


def _short_cohorts() -> list[tuple[str, str, Callable[[dict[str, Any]], bool]]]:
    return [
        (
            "Högt score + svag kursbekräftelse",
            "Hög Short Alpha-score trots svag trend eller relativ styrka.",
            lambda s: _num(s.get("Short Alpha Score")) >= 70 and min(_num(s.get("Short Trend")), _num(s.get("Short Relative Strength"))) < 45,
        ),
        (
            "Starkt momentum + svag handelsaktivitet",
            "Momentum finns men deltagande/handelsaktivitet är svagt.",
            lambda s: _num(s.get("Short Momentum")) >= 65 and _num(s.get("Short Participation")) < 45,
        ),
        (
            "Förväntningar/katalysator utan kursstöd",
            "Revideringar eller katalysator är starka men prisbekräftelsen är svag.",
            lambda s: max(_num(s.get("Short Revisions")), _num(s.get("Short Catalyst"))) >= 65 and max(_num(s.get("Short Trend")), _num(s.get("Short Relative Strength"))) < 50,
        ),
        (
            "Positiv rapport utan fortsatt drift",
            "Rapporten gav stöd men den efterföljande kursdriften bekräftade inte caset.",
            lambda s: bool(s.get("Post-report stöd")) and (bool(s.get("Post-report varning")) or _num(s.get("Post-report fortsatt rörelse")) <= 0),
        ),
        (
            "Hög bolagsspecifik volatilitet",
            "Caset hade hög eller mycket hög idiosynkratisk volatilitet.",
            lambda s: "hög" in _text(s.get("Idiosynkratisk volatilitet status")),
        ),
        (
            "Låg handelsaktivitet",
            "Short Participation var svag i det frysta caset.",
            lambda s: _num(s.get("Short Participation")) < 40,
        ),
    ]


def _long_cohorts() -> list[tuple[str, str, Callable[[dict[str, Any]], bool]]]:
    return [
        (
            "Högt score + svag vinstkvalitet",
            "Högt INVEST Score trots varning i kassaflöde/accrual-kvalitet.",
            lambda s: _num(s.get("INVEST Score")) >= 70 and (_is_warning(s.get("Vinstkvalitet status")) or _is_warning(s.get("Periodiseringsrisk status"))),
        ),
        (
            "Högt score + svag kapitaldisciplin",
            "Högt INVEST Score trots att kapitalbindning/investeringseffektivitet varnade.",
            lambda s: _num(s.get("INVEST Score")) >= 70 and _is_warning(s.get("Kapitaldisciplin status")),
        ),
        (
            "Få oberoende stöd",
            "Caset hade få stödjande Evidence Families eller flera varningsfamiljer.",
            lambda s: _num(s.get("Evidence Family Support Count")) <= 1 or _num(s.get("Evidence Family Warning Count")) >= 2,
        ),
        (
            "Positiv rapport utan fortsatt drift",
            "Rapportstöd fanns men efterföljande prisdrift bekräftade inte caset.",
            lambda s: bool(s.get("Post-report stöd")) and (bool(s.get("Post-report varning")) or _num(s.get("Post-report fortsatt rörelse")) <= 0),
        ),
        (
            "Dyrt + starkt momentum",
            "Svag värderingsscore samtidigt som 3-månaderskursen var stark – möjligt överbetalt kvalitets/momentumcase.",
            lambda s: _num(s.get("Värdering")) < 40 and _num(s.get("3 mån")) >= 15,
        ),
        (
            "Hög bolagsspecifik volatilitet",
            "Caset hade hög eller mycket hög idiosynkratisk volatilitet.",
            lambda s: "hög" in _text(s.get("Idiosynkratisk volatilitet status")),
        ),
    ]


def failure_cohort_table(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str = "1m",
    horizon_type: str = "short",
) -> pd.DataFrame:
    cols = ["Cohort", "Status", "Andel senaste", "Case senaste", "Median cohort", "Median övriga", "Gap", "Förändring mot tidigare", "Tolkning"]
    data = prepare_failure_cohort_sample(recommendations, outcomes, horizon, horizon_type)
    if len(data) < MIN_TOTAL:
        return pd.DataFrame(columns=cols)
    prior = data.iloc[-WINDOW * 2:-WINDOW].copy()
    recent = data.iloc[-WINDOW:].copy()
    metric, metric_label = _outcome_basis(data)
    cohort_defs = _short_cohorts() if str(horizon_type).lower() == "short" else _long_cohorts()
    rows: list[dict[str, Any]] = []
    for name, description, fn in cohort_defs:
        rmask = recent["_snap"].map(fn)
        pmask = prior["_snap"].map(fn)
        rg = pd.to_numeric(recent.loc[rmask, metric], errors="coerce").dropna()
        ro = pd.to_numeric(recent.loc[~rmask, metric], errors="coerce").dropna()
        pg = pd.to_numeric(prior.loc[pmask, metric], errors="coerce").dropna()
        if len(rg) < MIN_COHORT or len(ro) < MIN_COHORT:
            continue
        rmed = float(rg.median()); omed = float(ro.median()); gap = rmed - omed
        pmed = float(pg.median()) if len(pg) >= MIN_COHORT else np.nan
        change = rmed - pmed if math.isfinite(pmed) else np.nan
        share = float(rmask.mean())
        status = "Ingen tydlig"
        if gap <= -STRONG_GAP and share >= .25 and (not math.isfinite(change) or change <= -POSSIBLE_GAP):
            status = "Stark failure cohort"
        elif gap <= -POSSIBLE_GAP:
            status = "Möjlig failure cohort"
        if status == "Ingen tydlig":
            continue
        rows.append({
            "Cohort": name,
            "Status": status,
            "Andel senaste": f"{share*100:.0f}%",
            "Case senaste": int(len(rg)),
            "Median cohort": f"{rmed*100:.1f}%",
            "Median övriga": f"{omed*100:.1f}%",
            "Gap": f"{gap*100:.1f} pp",
            "Förändring mot tidigare": f"{change*100:.1f} pp" if math.isfinite(change) else "—",
            "Tolkning": f"{description} Utfallet mäts som {metric_label.lower()}. Samvariation, inte bevisad orsak.",
            "_priority": 0 if status.startswith("Stark") else 1,
            "_gap": gap,
        })
    if not rows:
        return pd.DataFrame(columns=cols)
    return (pd.DataFrame(rows).sort_values(["_priority", "_gap"], kind="stable")
            .drop(columns=["_priority", "_gap"]).reset_index(drop=True))


def failure_cohort_summary(table: pd.DataFrame, sample_size: int) -> dict[str, str]:
    if sample_size < MIN_TOTAL:
        return {"status": "Vänta", "text": f"För lite oberoende historik för cohortanalys ({sample_size}/{MIN_TOTAL} case)."}
    if table is None or table.empty:
        return {"status": "Ingen tydlig cohort", "text": "Ingen fördefinierad typ av case står ut som tydlig förklaring i senaste fönstret."}
    strong = int((table["Status"] == "Stark failure cohort").sum())
    if strong:
        return {"status": "Failure cohorts hittade", "text": f"{strong} stark failure cohort(s) står ut. Granska råa case innan någon modelländring."}
    return {"status": "Möjliga cohorts", "text": f"{len(table)} möjlig(a) failure cohort(s) står ut, men sambandet är inte kausalt bevis."}
