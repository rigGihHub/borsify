from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

from independent_case_validation import independent_case_sample

REGISTERED_VERSION = "3.39.0"
REGISTERED_DATE = "2026-09-08"
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


def _cohort(s: dict[str, Any]) -> str | None:
    """Locked prospective cohort definition.

    Signal: explicit positive expectation surprise + strong source + small initial response,
    as frozen by News Surprise Underreaction. Control: the same class of positive surprise
    from a strong source where a small-response underreaction was *not* flagged.
    Missing/ambiguous rows are excluded rather than reconstructed later.
    """
    direction = str(s.get("News Surprise Primary Direction") or "").lower()
    strength = pd.to_numeric(pd.Series([s.get("News Surprise Strength")]), errors="coerce").iloc[0]
    source = str(s.get("News Surprise Source Quality") or "")
    if direction != "positive" or not math.isfinite(float(strength)) or float(strength) < 3 or source != "Stark källa":
        return None
    under = s.get("News Surprise Underreaction")
    if under is True or str(under).strip().lower() in {"true", "1", "yes"}:
        return "Underreaktion"
    # Only a clean positive-surprise control. Adverse/missing-response observations do not
    # become controls because they answer a different question.
    if s.get("News Surprise Adverse Reaction") is True or str(s.get("News Surprise Adverse Reaction")).lower() == "true":
        return None
    immediate = pd.to_numeric(pd.Series([s.get("News Surprise Directional Immediate")]), errors="coerce").iloc[0]
    if not math.isfinite(float(immediate)):
        return None
    return "Tydligare direkt reaktion"


def eligible_sample(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str) -> pd.DataFrame:
    """Use only untouched observations created on/after the locked v3.39 registration."""
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame()
    required_rec = {"record_id", "snapshot_json"}
    required_out = {"record_id", "horizon", "return_pct"}
    if not required_rec.issubset(recommendations.columns) or not required_out.issubset(outcomes.columns):
        return pd.DataFrame()

    recs = recommendations.copy()
    version_col = "model_version" if "model_version" in recs.columns else None
    date_col = "captured_date" if "captured_date" in recs.columns else None
    if version_col is None or date_col is None:
        return pd.DataFrame()
    version_ok = recs[version_col].map(_version_tuple).map(lambda x: x >= _version_tuple(REGISTERED_VERSION))
    dates = pd.to_datetime(recs[date_col], errors="coerce", utc=True)
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


def validate_news_underreaction(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str) -> dict[str, Any]:
    """Prospective association test. It never changes production ranking or gates."""
    sample = eligible_sample(recommendations, outcomes, horizon)
    base = {
        "Horisont": str(horizon), "Status": "Väntar på prospektiva utfall",
        "Oberoende case": 0, "Underreaktion case": 0, "Kontroll case": 0,
        "Median underreaktion": np.nan, "Median kontroll": np.nan, "Median skillnad": np.nan,
        "Träff underreaktion": np.nan, "Träff kontroll": np.nan, "Träffskillnad": np.nan,
        "Registrerad version": REGISTERED_VERSION, "Registrerad datum": REGISTERED_DATE,
        "Slutsats": "Testdefinitionen är låst. Äldre case räknas inte och historik fylls inte bakåt.",
    }
    if sample.empty:
        return base

    signal = pd.to_numeric(sample.loc[sample["_cohort"].eq("Underreaktion"), "return_pct"], errors="coerce").dropna()
    control = pd.to_numeric(sample.loc[sample["_cohort"].eq("Tydligare direkt reaktion"), "return_pct"], errors="coerce").dropna()
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
        conclusion = "Underreaktionsgruppen har hittills bättre framtida utfall än kontrollgruppen. Det är preliminärt stöd, inte bevisad alpha."
    elif math.isfinite(gap) and gap <= -MEANINGFUL_MEDIAN_GAP and (not math.isfinite(hit_gap) or hit_gap <= 0):
        status = "Signal ifrågasatt"
        conclusion = "Underreaktionsgruppen har hittills sämre framtida utfall än kontrollgruppen. Signalen bör granskas innan den får större betydelse."
    else:
        status = "Oklart"
        conclusion = "Prospektiva utfall visar ännu ingen tydlig skillnad mellan underreaktion och kontroll."

    return {
        **base,
        "Status": status, "Oberoende case": n, "Underreaktion case": int(len(signal)), "Kontroll case": int(len(control)),
        "Median underreaktion": med_s, "Median kontroll": med_c, "Median skillnad": gap,
        "Träff underreaktion": hit_s, "Träff kontroll": hit_c, "Träffskillnad": hit_gap,
        "Slutsats": conclusion,
    }


def validation_table(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizons=("1m", "3m", "6m")) -> pd.DataFrame:
    return pd.DataFrame([validate_news_underreaction(recommendations, outcomes, h) for h in horizons])


def validation_summary(table: pd.DataFrame) -> dict[str, str]:
    if table is None or table.empty:
        return {"status": "Väntar", "text": "News Underreaction-testet är förregistrerat men inga prospektiva utfall finns ännu."}
    questioned = table[table["Status"].eq("Signal ifrågasatt")]
    supported = table[table["Status"].eq("Prospektivt stöd")]
    if not questioned.empty:
        return {"status": "Granska", "text": "Minst en mogen horisont går emot underreaktionshypotesen. Ingen automatisk modelländring görs."}
    if not supported.empty:
        return {"status": "Stöd", "text": "Minst en mogen horisont ger prospektivt stöd för underreaktionshypotesen. Det är ännu inte bevisad alpha."}
    max_n = int(pd.to_numeric(table.get("Oberoende case"), errors="coerce").fillna(0).max())
    return {"status": "Väntar", "text": f"Prospektiv validering pågår. Största mogna samplet är {max_n} oberoende case."}
