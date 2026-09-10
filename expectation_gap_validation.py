from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

from independent_case_validation import independent_case_sample

REGISTERED_VERSION = "3.73.0"
REGISTERED_DATE = "2026-09-10"
MIN_TOTAL_CASES = 30
MIN_GROUP_CASES = 10
MEANINGFUL_MEDIAN_GAP = 0.03


def _snapshot(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}
    return {}


def _version_tuple(value: Any) -> tuple[int, int, int]:
    text = str(value or "").strip().lstrip("vV")
    nums: list[int] = []
    for part in text.split(".")[:3]:
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits) if digits else 0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def _yes(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in {"1", "true", "ja", "yes"}


def _cohort(snapshot: dict[str, Any]) -> str | None:
    """Locked prospective cohort definition.

    Signal: the exact v3.72 Expectation Gap candidate as frozen at recommendation time.
    Control: confirmed positive change with adequate expectation data but no favorable gap
    and no expectation warning. Warning/crowded/thin-data observations are excluded because
    they answer a different question and must never be silently converted into controls.
    """
    if _yes(snapshot.get("Expectation Gap kandidat")):
        return "Förbättring före förväntningarna"

    status = str(snapshot.get("Expectation Gap status") or "")
    confirmed = _yes(snapshot.get("Förändringsbekräftelse kandidat"))
    warning = _yes(snapshot.get("Expectation Gap varning"))
    analysts = pd.to_numeric(pd.Series([snapshot.get("Expectation Gap analytiker antal")]), errors="coerce").iloc[0]
    if not confirmed or warning or not math.isfinite(float(analysts)) or float(analysts) < 5:
        return None
    if status == "Positiv förändring – inget tydligt expectation gap":
        return "Bekräftad förändring utan tydligt gap"
    return None


def eligible_sample(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame()
    if not {"record_id", "snapshot_json", "model_version", "captured_date"}.issubset(recommendations.columns):
        return pd.DataFrame()
    if not {"record_id", "horizon", "return_pct"}.issubset(outcomes.columns):
        return pd.DataFrame()

    recs = recommendations.copy()
    version_ok = recs["model_version"].map(_version_tuple).map(lambda x: x >= _version_tuple(REGISTERED_VERSION))
    dates = pd.to_datetime(recs["captured_date"], errors="coerce", utc=True)
    date_ok = dates.notna() & (dates >= pd.Timestamp(REGISTERED_DATE, tz="UTC"))
    recs = recs[version_ok & date_ok].copy()
    if recs.empty:
        return pd.DataFrame()

    recs["_cohort"] = recs["snapshot_json"].map(lambda raw: _cohort(_snapshot(raw)))
    recs = recs[recs["_cohort"].notna()].copy()
    if recs.empty:
        return pd.DataFrame()

    outs = outcomes[outcomes["horizon"].astype(str).eq(str(horizon))].copy()
    merged = recs.merge(outs, on="record_id", how="inner", suffixes=("", "_out"))
    merged["return_pct"] = pd.to_numeric(merged["return_pct"], errors="coerce")
    merged = merged.dropna(subset=["return_pct"])
    if merged.empty:
        return merged
    return independent_case_sample(merged, str(horizon))


def validate_expectation_gap(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str) -> dict[str, Any]:
    sample = eligible_sample(recommendations, outcomes, horizon)
    base = {
        "Horisont": str(horizon),
        "Status": "Väntar på prospektiva utfall",
        "Oberoende case": 0,
        "Expectation Gap case": 0,
        "Kontroll case": 0,
        "Median gap-case": np.nan,
        "Median kontroll": np.nan,
        "Median skillnad": np.nan,
        "Träff gap-case": np.nan,
        "Träff kontroll": np.nan,
        "Träffskillnad": np.nan,
        "Registrerad version": REGISTERED_VERSION,
        "Registrerad datum": REGISTERED_DATE,
        "Slutsats": "Testdefinitionen är låst. Äldre case räknas inte och historik fylls inte bakåt.",
    }
    if sample.empty:
        return base

    signal = pd.to_numeric(sample.loc[sample["_cohort"].eq("Förbättring före förväntningarna"), "return_pct"], errors="coerce").dropna()
    control = pd.to_numeric(sample.loc[sample["_cohort"].eq("Bekräftad förändring utan tydligt gap"), "return_pct"], errors="coerce").dropna()
    n = int(len(signal) + len(control))
    med_s = float(signal.median()) if len(signal) else np.nan
    med_c = float(control.median()) if len(control) else np.nan
    gap = med_s - med_c if math.isfinite(med_s) and math.isfinite(med_c) else np.nan
    hit_s = float((signal > 0).mean()) if len(signal) else np.nan
    hit_c = float((control > 0).mean()) if len(control) else np.nan
    hit_gap = hit_s - hit_c if math.isfinite(hit_s) and math.isfinite(hit_c) else np.nan

    if n < MIN_TOTAL_CASES or min(len(signal), len(control)) < MIN_GROUP_CASES:
        status = "För lite prospektiv historik"
        conclusion = f"{n} oberoende case har mognat. Borsify väntar på minst {MIN_TOTAL_CASES} totalt och {MIN_GROUP_CASES} i vardera gruppen."
    elif math.isfinite(gap) and gap >= MEANINGFUL_MEDIAN_GAP and (not math.isfinite(hit_gap) or hit_gap >= 0):
        status = "Prospektivt stöd"
        conclusion = "Expectation Gap-gruppen har hittills bättre framtida utfall än kontrollgruppen. Det är preliminärt stöd, inte bevisad alpha."
    elif math.isfinite(gap) and gap <= -MEANINGFUL_MEDIAN_GAP and (not math.isfinite(hit_gap) or hit_gap <= 0):
        status = "Hypotes ifrågasatt"
        conclusion = "Expectation Gap-gruppen har hittills sämre framtida utfall än kontrollgruppen. Hypotesen bör granskas innan lagret får större betydelse."
    else:
        status = "Oklart"
        conclusion = "Prospektiva utfall visar ännu ingen tydlig skillnad mellan Expectation Gap och kontroll."

    return {
        **base,
        "Status": status,
        "Oberoende case": n,
        "Expectation Gap case": int(len(signal)),
        "Kontroll case": int(len(control)),
        "Median gap-case": med_s,
        "Median kontroll": med_c,
        "Median skillnad": gap,
        "Träff gap-case": hit_s,
        "Träff kontroll": hit_c,
        "Träffskillnad": hit_gap,
        "Slutsats": conclusion,
    }


def validation_table(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizons=("1m", "3m", "6m")) -> pd.DataFrame:
    return pd.DataFrame([validate_expectation_gap(recommendations, outcomes, h) for h in horizons])


def validation_summary(table: pd.DataFrame) -> dict[str, str]:
    if table is None or table.empty:
        return {"status": "Väntar", "text": "Expectation Gap-testet är förregistrerat men inga prospektiva utfall finns ännu."}
    questioned = table[table["Status"].eq("Hypotes ifrågasatt")]
    supported = table[table["Status"].eq("Prospektivt stöd")]
    if not questioned.empty:
        return {"status": "Granska", "text": "Minst en mogen horisont går emot Expectation Gap-hypotesen. Ingen automatisk modelländring görs."}
    if not supported.empty:
        return {"status": "Stöd", "text": "Minst en mogen horisont ger prospektivt stöd för Expectation Gap-hypotesen. Det är ännu inte bevisad alpha."}
    max_n = int(pd.to_numeric(table.get("Oberoende case"), errors="coerce").fillna(0).max())
    return {"status": "Väntar", "text": f"Prospektiv Expectation Gap-validering pågår. Största mogna samplet är {max_n} oberoende case."}
