from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd


SHORT_GATE_RANK = {
    "Ej kortsiktigt toppcase": 1,
    "Svag kortsiktig signal": 2,
    "Bevaka kortsiktigt": 3,
    "Starkt kortsiktigt case": 4,
    "Kortsiktigt toppcase": 5,
}

LONG_GATE_RANK = {
    "Ej toppcase": 1,
    "Bevaka – motbevis finns": 2,
    "Bevaka": 3,
    "Värd djupanalys": 4,
    "Starkt case": 5,
    "Toppcase": 6,
}


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _snapshot(record: dict[str, Any] | pd.Series) -> dict[str, Any]:
    raw = record.get("snapshot_json", "{}")
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw or "{}"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _gate_rank(gate: str, horizon: str) -> int:
    table = SHORT_GATE_RANK if horizon == "short" else LONG_GATE_RANK
    return table.get(str(gate or "").strip(), 0)


def previous_record_for_case(
    ledger: pd.DataFrame,
    symbol: str,
    horizon: str,
    profile: str,
    market: str,
    as_of_date: str,
) -> dict[str, Any] | None:
    """Latest frozen recommendation strictly before today's recommendation.

    Same-day records are deliberately excluded so a rerun cannot compare a case with
    the snapshot that was just written a few milliseconds earlier.
    """
    if ledger is None or ledger.empty:
        return None
    work = ledger.copy()
    for col in ["symbol", "horizon_type", "profile", "market", "captured_date"]:
        if col not in work.columns:
            return None
    mask = (
        work["symbol"].astype(str).str.upper().eq(str(symbol).upper())
        & work["horizon_type"].astype(str).str.lower().eq(str(horizon).lower())
        & work["profile"].astype(str).eq(str(profile))
        & work["market"].astype(str).eq(str(market))
        & (pd.to_datetime(work["captured_date"], errors="coerce") < pd.Timestamp(as_of_date))
    )
    prior = work.loc[mask].copy()
    if prior.empty:
        return None
    prior["_captured"] = pd.to_datetime(prior["captured_at"], errors="coerce")
    prior = prior.sort_values(["_captured", "captured_date"], ascending=False)
    return prior.iloc[0].drop(labels=["_captured"], errors="ignore").to_dict()


def assess_recommendation_relevance(
    current: dict[str, Any] | pd.Series,
    prior: dict[str, Any] | pd.Series | None,
    horizon: str,
) -> dict[str, Any]:
    """Explain whether an old recommendation still resembles the current case.

    This is a deterministic case-monitor, not a new return forecast.
    """
    horizon = str(horizon).lower().strip()
    if prior is None:
        return {
            "status": "Ny rekommendation",
            "explanation": "Ingen äldre fryst rekommendation finns att jämföra med ännu.",
            "price_return": np.nan,
            "reference_price": np.nan,
            "reference_date": "",
            "score_delta": np.nan,
            "gate_delta": np.nan,
        }

    current_price = _num(current.get("Pris"))
    prior_price = _num(prior.get("entry_price"))
    price_return = (
        current_price / prior_price - 1
        if np.isfinite(current_price) and np.isfinite(prior_price) and prior_price > 0
        else np.nan
    )

    if horizon == "short":
        current_gate = str(current.get("Short Alpha Gate", ""))
        current_score = _num(current.get("Short Alpha Score"))
    else:
        current_gate = str(current.get("Case Gate", ""))
        current_score = _num(current.get("INVEST Score"))

    prior_gate = str(prior.get("gate", ""))
    prior_score = _num(prior.get("score"))
    score_delta = current_score - prior_score if np.isfinite(current_score) and np.isfinite(prior_score) else np.nan
    gate_delta = _gate_rank(current_gate, horizon) - _gate_rank(prior_gate, horizon)

    snap = _snapshot(prior)
    valuation_notes: list[str] = []
    current_fwd_pe = _num(current.get("Forward P/E"))
    prior_fwd_pe = _num(snap.get("Forward P/E"))
    if np.isfinite(current_fwd_pe) and np.isfinite(prior_fwd_pe) and prior_fwd_pe > 0:
        pe_change = current_fwd_pe / prior_fwd_pe - 1
        if pe_change >= 0.15:
            valuation_notes.append(f"Forward P/E har stigit cirka {pe_change:.0%}")
        elif pe_change <= -0.15:
            valuation_notes.append(f"Forward P/E har sjunkit cirka {abs(pe_change):.0%}")

    current_fcf = _num(current.get("FCF yield"))
    prior_fcf = _num(snap.get("FCF yield"))
    if np.isfinite(current_fcf) and np.isfinite(prior_fcf):
        fcf_delta = current_fcf - prior_fcf
        if fcf_delta <= -0.015:
            valuation_notes.append("FCF-yield har försämrats tydligt")
        elif fcf_delta >= 0.015:
            valuation_notes.append("FCF-yield har förbättrats tydligt")

    hard_weakened = False
    if horizon == "short":
        vetoes = str(current.get("Short Vetoes", "") or "")
        hard_weakened = bool(vetoes and vetoes != "—")
    else:
        vetoes = str(current.get("Case Vetoes", "") or "")
        hard_weakened = bool(vetoes and vetoes not in {"—", "inga hårda motbevis i gate-modellen"})

    ref_date = str(prior.get("captured_date", ""))[:10]
    move_text = f"Kursen är {price_return:+.1%} sedan {ref_date}." if np.isfinite(price_return) else ""
    score_text = f" Modellscore har ändrats {score_delta:+.1f} poäng." if np.isfinite(score_delta) else ""

    if hard_weakened or gate_delta <= -2 or (np.isfinite(score_delta) and score_delta <= -8):
        status = "Caset har försvagats"
        explanation = f"{move_text}{score_text} Nuvarande modellbild är tydligt svagare än vid den frysta rekommendationen."
    elif gate_delta >= 1 and np.isfinite(score_delta) and score_delta >= 4:
        status = "Caset har stärkts"
        explanation = f"{move_text}{score_text} Både bedömningsnivå och modellstöd har förbättrats."
    else:
        threshold = 0.10 if horizon == "short" else 0.18
        if (
            np.isfinite(price_return) and price_return >= threshold
            and (not np.isfinite(score_delta) or score_delta < 4)
            and gate_delta <= 0
        ):
            status = "Mindre attraktivt än vid signal"
            explanation = (
                f"{move_text}{score_text} Kursen har stigit tydligt utan motsvarande förstärkning i modellstödet. "
                "Det betyder inte automatiskt att aktien är dyr, men värderingen bör kontrolleras på nytt."
            )
        elif np.isfinite(score_delta) and score_delta <= -4:
            status = "Caset har försvagats"
            explanation = f"{move_text}{score_text} Modellstödet har försvagats sedan den frysta rekommendationen."
        else:
            status = "Fortfarande relevant"
            explanation = (
                f"{move_text}{score_text} Borsify ser ingen tillräckligt stor försämring för att kalla rekommendationen inaktuell."
            )

    if valuation_notes:
        explanation += " " + "; ".join(valuation_notes) + "."

    return {
        "status": status,
        "explanation": explanation.strip(),
        "price_return": price_return,
        "reference_price": prior_price,
        "reference_date": ref_date,
        "score_delta": score_delta,
        "gate_delta": gate_delta,
    }


def apply_recommendation_relevance(
    frame: pd.DataFrame,
    ledger: pd.DataFrame,
    horizon: str,
    profile: str,
    market: str,
    as_of_date: str,
) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    out = frame.copy()
    records: dict[Any, dict[str, Any]] = {}
    for idx, row in out.iterrows():
        prior = previous_record_for_case(
            ledger, str(row.get("Ticker", "")), horizon, profile, market, as_of_date
        )
        records[idx] = assess_recommendation_relevance(row, prior, horizon)

    assessment = pd.DataFrame.from_dict(records, orient="index")
    mapping = {
        "status": "Relevans nu",
        "explanation": "Relevans förklaring",
        "price_return": "Sedan rekommendation",
        "reference_price": "Referenskurs",
        "reference_date": "Referensdatum",
        "score_delta": "Relevans score delta",
        "gate_delta": "Relevans gate delta",
    }
    assessment = assessment.rename(columns=mapping)
    overlap = [c for c in assessment.columns if c in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    return out.join(assessment, how="left")
