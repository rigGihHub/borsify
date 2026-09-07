from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from independent_case_validation import independent_case_sample

MIN_SIGNAL_CASES = 24
MIN_GROUP_CASES = 8
MEANINGFUL_SPREAD = 0.05


@dataclass(frozen=True)
class SignalSpec:
    name: str
    model: str
    rationale: str
    classifier: Callable[[dict[str, Any]], int]


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


def _txt(value: Any) -> str:
    return str(value or "").strip().upper()


def _post_report(s: dict[str, Any]) -> int:
    status = _txt(s.get("Post-report status"))
    if status == "POSITIV RAPPORTDRIFT":
        return 1
    if status in {"BRA RAPPORT MEN STYRKAN HAR VÄNT", "NEGATIV RAPPORTDRIFT"}:
        return -1
    return 0


def _earnings_quality(s: dict[str, Any]) -> int:
    accrual = _txt(s.get("Periodiseringsrisk status"))
    quality = _txt(s.get("Vinstkvalitet status"))
    if accrual == "FÖRHÖJD RISK" or quality == "SVAG VINSTKVALITET":
        return -1
    if accrual == "STARKT KASSASTÖD" or quality == "STARK VINSTKVALITET":
        return 1
    return 0


def _investment_discipline(s: dict[str, Any]) -> int:
    status = _txt(s.get("Kapitaldisciplin status"))
    if status == "EFFEKTIV KAPITALANVÄNDNING":
        return 1
    if status == "KAPITALBINDNING ÖKAR":
        return -1
    return 0


def _evidence_families(s: dict[str, Any]) -> int:
    support = _num(s.get("Evidence Family Support Count"))
    warnings = _num(s.get("Evidence Family Warning Count"))
    if not np.isfinite(support):
        return 0
    warnings = warnings if np.isfinite(warnings) else 0.0
    if support >= 4 and warnings == 0:
        return 1
    if support <= 1 or warnings >= 2:
        return -1
    return 0


def _momentum_12_1(s: dict[str, Any]) -> int:
    score = _num(s.get("12–1 momentum score"))
    if not np.isfinite(score):
        score = _num(s.get("Short 12–1 Momentum"))
    if not np.isfinite(score):
        return 0
    if score >= 65:
        return 1
    if score <= 35:
        return -1
    return 0


def _idio_vol(s: dict[str, Any]) -> int:
    status = _txt(s.get("Idiosynkratisk volatilitet status"))
    if status == "INGEN TYDLIG EXTRA RISK":
        return 1
    if status in {"HÖG BOLAGSSPECIFIK RISK", "MYCKET HÖG BOLAGSSPECIFIK RISK"}:
        return -1
    return 0


SIGNALS: tuple[SignalSpec, ...] = (
    SignalSpec("Post-Report Drift", "long", "Färsk rapportdrift ska följas av bättre utfall än tydligt negativ/vänd rapportdrift.", _post_report),
    SignalSpec("Earnings Quality 2.0", "long", "Starkt kassastöd ska följas av bättre utfall än förhöjd periodiseringsrisk/svag vinstkvalitet.", _earnings_quality),
    SignalSpec("Investment Discipline", "long", "Effektiv kapitalanvändning ska följas av bättre utfall än tydligt ökande kapitalbindning.", _investment_discipline),
    SignalSpec("Evidence Families", "long", "Brett oberoende stöd utan varningar ska följas av bättre utfall än smalt eller varningsdominerat stöd.", _evidence_families),
    SignalSpec("12–1 Momentum", "short", "Etablerat längre momentum ska följas av bättre utfall än tydligt svagt 12–1 momentum.", _momentum_12_1),
    SignalSpec("Bolagsspecifik volatilitet", "long", "Avsaknad av tydlig extra bolagsspecifik risk ska följas av bättre utfall än hög idiosynkratisk volatilitet.", _idio_vol),
)


def _outcome_basis(frame: pd.DataFrame) -> tuple[str, str]:
    if frame is not None and not frame.empty and "excess_return_pct" in frame.columns:
        rel = pd.to_numeric(frame["excess_return_pct"], errors="coerce")
        if rel.notna().all():
            return "excess_return_pct", "Mot index"
    return "return_pct", "Rå kursutveckling"


def prepare_signal_sample(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
    spec: SignalSpec,
) -> pd.DataFrame:
    """Return independent point-in-time observations with explicit favorable/adverse states.

    Neutral and missing states are excluded. Historical gaps are never reconstructed from
    current data. This intentionally validates only observations saved after each signal
    existed in the production ledger.
    """
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame()
    if not {"record_id", "horizon_type", "snapshot_json"}.issubset(recommendations.columns):
        return pd.DataFrame()
    if not {"record_id", "horizon", "return_pct"}.issubset(outcomes.columns):
        return pd.DataFrame()

    outs = outcomes[outcomes["horizon"].astype(str).eq(str(horizon))].copy()
    if outs.empty:
        return pd.DataFrame()
    keep = [c for c in ["record_id", "symbol", "captured_date", "horizon_type", "snapshot_json", "model_version"] if c in recommendations.columns]
    merged = recommendations[keep].merge(outs, on="record_id", how="inner", suffixes=("", "_out"))
    merged = merged[merged["horizon_type"].astype(str).str.lower().eq(spec.model)].copy()
    if merged.empty:
        return merged

    merged["_signal_state"] = merged["snapshot_json"].map(lambda raw: spec.classifier(_snapshot(raw)))
    merged = merged[merged["_signal_state"].isin({-1, 1})].copy()
    merged["return_pct"] = pd.to_numeric(merged["return_pct"], errors="coerce")
    merged = merged.dropna(subset=["return_pct"])
    if merged.empty:
        return merged
    return independent_case_sample(merged, str(horizon))


def _status(n_total: int, n_good: int, n_bad: int, spread: float, hit_diff: float) -> str:
    if n_total < MIN_SIGNAL_CASES or min(n_good, n_bad) < MIN_GROUP_CASES:
        return "För lite historik"
    if math.isfinite(spread) and spread >= MEANINGFUL_SPREAD and (not math.isfinite(hit_diff) or hit_diff >= 0):
        return "Lovande"
    if math.isfinite(spread) and spread <= -MEANINGFUL_SPREAD and (not math.isfinite(hit_diff) or hit_diff <= 0):
        return "Ifrågasatt"
    return "Oklart"


def validate_literature_signals(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str,
) -> pd.DataFrame:
    """Validate the newly added literature-inspired signals against frozen future outcomes.

    This is association testing, not causal proof and not a backfilled backtest. Each signal
    is judged only on records where its state was frozen at decision time. The function never
    changes production weights, thresholds or gates.
    """
    rows: list[dict[str, Any]] = []
    for spec in SIGNALS:
        sample = prepare_signal_sample(recommendations, outcomes, horizon, spec)
        if sample.empty:
            rows.append({
                "Signal": spec.name, "Modell": "Lång" if spec.model == "long" else "Kort",
                "Oberoende case": 0, "Positiva signalcase": 0, "Varningscase": 0,
                "Median positiv": np.nan, "Median varning": np.nan, "Skillnad": np.nan,
                "Träff positiv": np.nan, "Träff varning": np.nan, "Träffskillnad": np.nan,
                "Mätning": "—", "Status": "För lite historik", "Hypotes": spec.rationale,
            })
            continue

        metric_col, metric_label = _outcome_basis(sample)
        metric = pd.to_numeric(sample[metric_col], errors="coerce")
        state = pd.to_numeric(sample["_signal_state"], errors="coerce")
        valid = metric.notna() & state.isin({-1, 1})
        work = sample.loc[valid].copy()
        work["_metric"] = metric.loc[valid]
        good = work[work["_signal_state"].eq(1)]["_metric"]
        bad = work[work["_signal_state"].eq(-1)]["_metric"]
        med_good = float(good.median()) if len(good) else np.nan
        med_bad = float(bad.median()) if len(bad) else np.nan
        spread = med_good - med_bad if math.isfinite(med_good) and math.isfinite(med_bad) else np.nan
        hit_good = float((good > 0).mean()) if len(good) else np.nan
        hit_bad = float((bad > 0).mean()) if len(bad) else np.nan
        hit_diff = hit_good - hit_bad if math.isfinite(hit_good) and math.isfinite(hit_bad) else np.nan
        status = _status(len(work), len(good), len(bad), spread, hit_diff)
        rows.append({
            "Signal": spec.name,
            "Modell": "Lång" if spec.model == "long" else "Kort",
            "Oberoende case": int(len(work)),
            "Positiva signalcase": int(len(good)),
            "Varningscase": int(len(bad)),
            "Median positiv": med_good,
            "Median varning": med_bad,
            "Skillnad": spread,
            "Träff positiv": hit_good,
            "Träff varning": hit_bad,
            "Träffskillnad": hit_diff,
            "Mätning": metric_label,
            "Status": status,
            "Hypotes": spec.rationale,
        })

    result = pd.DataFrame(rows)
    order = {"Ifrågasatt": 0, "Lovande": 1, "Oklart": 2, "För lite historik": 3}
    result["_order"] = result["Status"].map(order).fillna(9)
    return result.sort_values(["_order", "Signal"], kind="stable").drop(columns="_order").reset_index(drop=True)


def literature_signal_summary(table: pd.DataFrame) -> dict[str, Any]:
    if table is None or table.empty:
        return {"status": "För lite historik", "text": "Det finns ännu inga mogna point-in-time-utfall för de nya litteratursignalerna."}
    questioned = table[table["Status"].eq("Ifrågasatt")]
    promising = table[table["Status"].eq("Lovande")]
    evaluated = table[table["Status"].isin({"Ifrågasatt", "Lovande", "Oklart"})]
    if not questioned.empty:
        names = ", ".join(questioned["Signal"].head(2).astype(str))
        return {
            "status": "Signal bör granskas",
            "text": f"{names} går hittills åt fel håll i Borsifys egen historik. Det är skäl att granska signalen, inte automatiskt ta bort den.",
        }
    if not promising.empty:
        names = ", ".join(promising["Signal"].head(2).astype(str))
        return {
            "status": "Lovande signaler",
            "text": f"{names} visar hittills rätt riktning i Borsifys egna oberoende case. Det är preliminär evidens, inte bevisad alpha.",
        }
    if evaluated.empty:
        max_n = int(pd.to_numeric(table.get("Oberoende case", pd.Series(dtype=float)), errors="coerce").fillna(0).max()) if len(table) else 0
        return {
            "status": "För lite historik",
            "text": f"De nya signalerna är ännu för unga. Största användbara samplet är {max_n} oberoende case; Borsify väntar på fler mogna utfall i stället för att fylla bakåt med dagens data.",
        }
    return {
        "status": "Oklart",
        "text": "Några signaler har tillräckligt underlag för jämförelse, men skillnaden är ännu inte tydlig nog för en praktisk slutsats.",
    }
