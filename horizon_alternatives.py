"""Current ranked alternatives, kept separate from approved purchase decisions."""
from __future__ import annotations

import math

import pandas as pd

from purchase_consistency import purchase_blockers

from anti_chase_gate import anti_chase_decision
from buy_quality_gate import BUY_THRESHOLDS, apply_buy_gate
from case_readiness import add_case_readiness
from entry_timing import add_entry_timing
from horizon_rankings import add_horizon_scores
from horizon_signals import add_action_signals
from liquidity_guard import add_liquidity_guard
from market_regime import add_market_regime
from near_buy import assess_overextension
from relative_strength import add_relative_strength
from user_score import add_user_scores


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def _blocks(row, horizon: str, gate_horizon: str) -> list[str]:
    reasons = purchase_blockers(row, horizon)
    if _num(row.get("Borsify slutbetyg")) < BUY_THRESHOLDS[gate_horizon]:
        reasons.append("slutbetyget når inte köpkravet")
    if not row.get("Köpfilter godkänd", False):
        for reason in str(row.get("Köpfilter stopp", "")).split(";"):
            reason = reason.strip()
            if reason.startswith("horisontscore under"):
                reason = "stödet för den här tidshorisonten är för svagt"
            if reason:
                reasons.append(reason)
    if not row.get("Köp nu efter rusning", False):
        reasons.append(str(row.get("Köp nu efter rusning skäl", "kursen har redan rusat")))
    if not row.get("Marknadskrav godkänd", False):
        reasons.append("marknadsläget kräver starkare stöd för köp")
    if gate_horizon == "medium" and not row.get("Likviditet godkänd", False):
        reasons.append(str(row.get("Likviditet förklaring", "handelsaktiviteten kan inte verifieras")))
    if not row.get("Case Readiness godkänd", False):
        reasons.append(str(row.get("Case Readiness stopp") or row.get("Case Readiness luckor") or "för svagt verifierat underlag"))
    if gate_horizon == "medium" and row.get("För långt gången", False):
        reasons.append(str(row.get("Köplägesvarningar", "kursen har gått för långt")))
    if row.get("Ingångsläge nivå") == "red" or (horizon == "medium" and row.get("Ingångsläge nivå") == "orange"):
        reasons.append(str(row.get("Ingångsläge skäl") or "vänta på ett lugnare ingångsläge"))
    buy_actions = {"KÖP NU", "KÖP", "KÖP / ÄG", "BYGG POSITION", "KÖP / ÄG LÅNGSIKTIGT", "BYGG LÅNGSIKTIGT"}
    if row.get("Signal") not in buy_actions:
        reasons.append("underlaget eller köpläget räcker inte för en tydlig köpsignal")
    return list(dict.fromkeys(reasons)) or ["genomför fördjupad kandidatgranskning för ett verifierat köpbeslut"]


def _interest(row) -> str:
    coverage = _num(row.get("Datatäckning"))
    if not math.isfinite(coverage) or coverage < .40:
        return "Högt rankad i ditt urval, men bolagsunderlaget är för osäkert för en tydlig slutsats."
    positives = []
    for field, threshold, text in [
        ("Kvalitet", 65, "hög bolagskvalitet enligt tillgängliga uppgifter"),
        ("Värdering", 60, "värderingen får stöd av tillgängliga nyckeltal"),
        ("Risk", 68, "relativt robust riskprofil"),
        ("Omsättningstillväxt", 0, "positiv omsättningstillväxt"),
    ]:
        number = _num(row.get(field))
        if math.isfinite(number) and number > threshold:
            positives.append(text)
    return "; ".join(positives[:3]) or "Tillhör de bäst rankade aktierna i ditt nuvarande urval."


def rank_horizon_alternatives(frame: pd.DataFrame, horizon: str, limit: int = 3, evidence_fn=None) -> pd.DataFrame:
    """Rank without relaxing purchase gates or emitting any purchase decision.

    All diagnostics use current observations and the existing controls. No new
    aggregate score, evidence bonus, persistence or external fetch is introduced.
    """
    score_col = {"medium": "Mellan Score", "year": "Års Score", "lifetime": "Livstid Score"}[horizon]
    if frame is None or frame.empty or limit <= 0 or "Ticker" not in frame:
        return pd.DataFrame()
    gate_horizon = "long" if horizon == "year" else horizon
    derived = ["Daytrade Score", "Mellan Score", "Års Score", "Lång Score", "Livstid Score"]
    out = add_user_scores(add_horizon_scores(frame.drop(columns=derived, errors="ignore")))
    if "Borsify slutbetyg" not in out:
        return pd.DataFrame()
    # No neutral score is fabricated for an unscored company.
    tickers = out["Ticker"].fillna("").astype(str).str.strip().str.upper()
    valid = tickers.ne("") & tickers.ne("NAN") & pd.to_numeric(out["Borsify slutbetyg"], errors="coerce").notna()
    out = out.loc[valid].copy()
    out["Ticker"] = tickers.loc[valid]
    out = out.drop_duplicates("Ticker")
    if out.empty:
        return out
    # Market/peer context still uses the full current universe, as in top_ranked.
    out = add_relative_strength(out)
    out = add_market_regime(out, gate_horizon)
    out = apply_buy_gate(out, gate_horizon)
    out = add_liquidity_guard(out, gate_horizon)
    out = add_case_readiness(out, gate_horizon)
    extensions = pd.DataFrame([assess_overextension(row, gate_horizon) for _, row in out.iterrows()], index=out.index)
    for column in extensions:
        out[column] = extensions[column]
    anti = pd.DataFrame([anti_chase_decision(row, "year" if horizon == "year" else horizon) for _, row in out.iterrows()], index=out.index)
    for column in anti:
        out[column] = anti[column]
    out = add_entry_timing(out, horizon)
    out = add_action_signals(out, horizon)
    sort_cols = ["Borsify slutbetyg", score_col]
    if "Datatäckning" in out:
        sort_cols.append("Datatäckning")
    out = out.sort_values(sort_cols + ["Ticker"], ascending=[False] * len(sort_cols) + [True], na_position="last").head(limit).copy()
    if evidence_fn is not None:
        out = evidence_fn(out, horizon)
    out["Alternativ varför"] = [_interest(row) for _, row in out.iterrows()]
    out["Alternativ hinder"] = [_blocks(row, horizon, gate_horizon) for _, row in out.iterrows()]
    out["Alternativ köpstopp"] = out["Alternativ hinder"].map("; ".join)
    # Presentation is explicitly observational, even for otherwise strong rows.
    out["Signal"] = ["AVVAKTA" if not row["Köp nu efter rusning"] or row.get("Ingångsläge nivå") == "red" else "BEVAKA" for _, row in out.iterrows()]
    out["Signal kort"] = "Rankat alternativ – inget köpbeslut"
    out["Signal förklaring"] = out["Alternativ köpstopp"]
    return out
