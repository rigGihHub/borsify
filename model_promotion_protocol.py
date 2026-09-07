from __future__ import annotations

import json
import math
from typing import Any, Iterable

import numpy as np
import pandas as pd

from prospective_challenger_registry import (
    ProspectiveChallenger,
    STATUS_CANDIDATE,
    default_prospective_challengers,
    eligible_prospective_recommendations,
    prospective_challenger_results,
    prospective_governance,
)
from signal_ablation import SHORT_WEIGHTS, prepare_short_ablation_data

PROTOCOL_VERSION = "1"
MIN_REGIME_CASES = 12
MIN_REGIMES = 2
MIN_PIT_COMPLETE_RATE = 0.90
MIN_SIGNAL_COMPLETE_RATE = 0.90
MAX_BAD_RANK_CORR = -0.05
MAX_BAD_REGIME_DELTA = -0.02

STATUS_WAIT = "Vänta – kraven är inte mogna"
STATUS_BLOCK = "Blockerad – champion ska behållas"
STATUS_REVIEW = "Redo för manuell promotionsprövning"

GATE_PASS = "Godkänd"
GATE_WAIT = "Väntar på data"
GATE_FAIL = "Underkänd"


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


def _weighted_score(frame: pd.DataFrame, excluded_signal: str | None = None) -> pd.Series:
    parts: list[pd.Series] = []
    total = 0.0
    for label, (field, weight) in SHORT_WEIGHTS.items():
        if label == excluded_signal:
            continue
        parts.append(pd.to_numeric(frame[field], errors="coerce") * float(weight))
        total += float(weight)
    if not parts or total <= 0:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(sum(parts) / total, errors="coerce")


def _outcome_basis(frame: pd.DataFrame) -> str:
    if "excess_return_pct" in frame.columns:
        rel = pd.to_numeric(frame["excess_return_pct"], errors="coerce")
        if rel.notna().all():
            return "excess_return_pct"
    return "return_pct"


def _top_bottom(score: pd.Series, outcome: pd.Series) -> float:
    work = pd.DataFrame({"score": score, "outcome": outcome}).dropna().sort_values("score")
    bucket = len(work) // 3
    if bucket < 4:
        return np.nan
    return float(work.tail(bucket)["outcome"].median() - work.head(bucket)["outcome"].median())


def promotion_data_coverage(
    recommendations: pd.DataFrame,
    challenger: ProspectiveChallenger,
) -> dict[str, Any]:
    """Audit whether prospective recommendations contain the frozen data needed for review."""
    eligible = eligible_prospective_recommendations(recommendations, challenger)
    if eligible.empty or "snapshot_json" not in eligible.columns:
        return {
            "status": GATE_WAIT, "eligible": int(len(eligible)), "pit_complete_rate": np.nan,
            "signal_complete_rate": np.nan, "reason": "Inga prospektiva case med komplett fryst snapshot finns ännu."
        }
    snaps = eligible["snapshot_json"].map(_snapshot)
    pit = snaps.map(lambda s: s.get("PIT Complete"))
    pit_ok = pit.map(lambda x: bool(x) if isinstance(x, (bool, np.bool_)) else str(x).strip().lower() == "true")
    signal_fields = [field for field, _ in SHORT_WEIGHTS.values()]
    signal_ok = snaps.map(lambda s: all(math.isfinite(_num(s.get(field))) for field in signal_fields))
    pit_rate = float(pit_ok.mean()) if len(pit_ok) else np.nan
    signal_rate = float(signal_ok.mean()) if len(signal_ok) else np.nan
    if pit_rate >= MIN_PIT_COMPLETE_RATE and signal_rate >= MIN_SIGNAL_COMPLETE_RATE:
        status = GATE_PASS
        reason = "Point-in-time-envelope och Short Alpha-komponenter har tillräcklig täckning."
    else:
        status = GATE_FAIL
        reason = (
            f"Datatäckningen är för låg. Krav: minst {MIN_PIT_COMPLETE_RATE:.0%} PIT-kompletta och "
            f"{MIN_SIGNAL_COMPLETE_RATE:.0%} kompletta signalfält."
        )
    return {
        "status": status, "eligible": int(len(eligible)), "pit_complete_rate": pit_rate,
        "signal_complete_rate": signal_rate, "reason": reason,
    }


def promotion_ranking_gate(detail: pd.DataFrame, challenger_id: str) -> dict[str, Any]:
    if detail is None or detail.empty or "Challenger ID" not in detail.columns:
        return {"status": GATE_WAIT, "reason": "Inga mogna prospektiva rangordningsutfall finns ännu."}
    group = detail[detail["Challenger ID"].eq(challenger_id)].copy()
    if group.empty:
        return {"status": GATE_WAIT, "reason": "Challengern saknar mogna prospektiva rangordningsutfall."}
    evaluated = group[group["Status"].isin({"Challenger bättre", "Champion bättre", "Ingen tydlig skillnad"})].copy()
    if len(evaluated) < 2:
        return {"status": GATE_WAIT, "reason": "Minst två mogna horisonter krävs för rangordningskontrollen."}
    corr = pd.to_numeric(evaluated["Challenger korrelation"], errors="coerce")
    bad = corr.dropna().le(MAX_BAD_RANK_CORR).any()
    if bad:
        return {"status": GATE_FAIL, "reason": "Challengern har tydligt negativ rangordningskorrelation på minst en mogen horisont."}
    return {"status": GATE_PASS, "reason": "Ingen mogen horisont visar tydligt negativ rangordningskorrelation för challengern."}


def prospective_regime_audit(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    challenger: ProspectiveChallenger,
    horizons: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Check whether challenger improvement survives more than one frozen market regime.

    This is a robustness gate, not a claim that regimes are causal or perfectly measured.
    Only point-in-time recommendations eligible after pre-registration are used.
    """
    eligible = eligible_prospective_recommendations(recommendations, challenger)
    if eligible.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame()
    if horizons is None:
        present = {str(x) for x in outcomes.get("horizon", pd.Series(dtype=str)).dropna().tolist()}
        horizon_list = [h for h in ["1m", "3m", "6m", "1y", "2y"] if h in present]
    else:
        horizon_list = [str(h) for h in horizons]

    rows: list[dict[str, Any]] = []
    for horizon in horizon_list:
        data = prepare_short_ablation_data(eligible, outcomes, horizon)
        if data.empty:
            continue
        snaps = data["snapshot_json"].map(_snapshot)
        data = data.copy()
        data["_regime"] = snaps.map(lambda s: str(s.get("Marknadsläge") or "Okänt").strip())
        metric_col = _outcome_basis(data)
        outcome_all = pd.to_numeric(data[metric_col], errors="coerce")
        champion_all = _weighted_score(data)
        challenger_all = _weighted_score(data, excluded_signal=challenger.excluded_signal)
        for regime, group in data.groupby("_regime", dropna=False):
            idx = group.index
            champion_spread = _top_bottom(champion_all.loc[idx], outcome_all.loc[idx])
            challenger_spread = _top_bottom(challenger_all.loc[idx], outcome_all.loc[idx])
            delta = challenger_spread - champion_spread if math.isfinite(champion_spread) and math.isfinite(challenger_spread) else np.nan
            rows.append({
                "Challenger ID": challenger.challenger_id,
                "Challenger": challenger.name,
                "Horisont": horizon,
                "Marknadsläge": str(regime),
                "Oberoende case": int(len(group)),
                "Champion topp-botten": champion_spread,
                "Challenger topp-botten": challenger_spread,
                "Förändring topp-botten": delta,
            })
    return pd.DataFrame(rows)


def promotion_regime_gate(audit: pd.DataFrame) -> dict[str, Any]:
    if audit is None or audit.empty:
        return {"status": GATE_WAIT, "reason": "Marknadslägeskontrollen saknar mogna prospektiva case."}
    mature = audit[pd.to_numeric(audit["Oberoende case"], errors="coerce").fillna(0).ge(MIN_REGIME_CASES)].copy()
    regimes = {r for r in mature["Marknadsläge"].astype(str) if r and r != "Okänt"}
    if len(regimes) < MIN_REGIMES:
        return {
            "status": GATE_WAIT,
            "reason": f"Minst {MIN_REGIMES} olika frysta marknadslägen med minst {MIN_REGIME_CASES} oberoende case vardera krävs."
        }
    delta = pd.to_numeric(mature["Förändring topp-botten"], errors="coerce")
    if delta.dropna().lt(MAX_BAD_REGIME_DELTA).any():
        return {"status": GATE_FAIL, "reason": "Challengern försämrar topp–botten-skillnaden tydligt i minst ett moget marknadsläge."}
    return {"status": GATE_PASS, "reason": "Ingen mogen marknadsregim visar en tydlig försämring mot champion."}


def rollback_plan(challenger: ProspectiveChallenger) -> dict[str, str]:
    """Static, explicit rollback contract. Promotion itself remains a manual action."""
    return {
        "status": GATE_PASS,
        "champion_backup": "Behåll föregående champion-definition, vikter och fingerprint oförändrade.",
        "rollback_trigger": "Rulla tillbaka vid dataintegritetsfel, tydlig prospektiv försämring eller trasig produktionskörning.",
        "rollback_action": f"Återaktivera föregående champion och markera {challenger.challenger_id} som pausad; skapa ny challenger vid ändrad definition.",
        "automatic": "Nej – både promotion och rollback kräver dokumenterat manuellt beslut.",
    }


def model_promotion_protocol(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    challengers: Iterable[ProspectiveChallenger] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Final manual promotion gate after prospective champion–challenger testing.

    Passing the protocol never changes production code. It only means the evidence is
    mature enough for a human to review a controlled release with a rollback plan.
    """
    specs = list(challengers or default_prospective_challengers())
    detail = prospective_challenger_results(recommendations, outcomes, challengers=specs)
    governance = prospective_governance(detail, challengers=specs)
    rows: list[dict[str, Any]] = []
    gate_rows: list[dict[str, Any]] = []

    for spec in specs:
        gov_row = governance[governance["Challenger"].eq(spec.name)] if not governance.empty else pd.DataFrame()
        prospective_status = str(gov_row.iloc[0]["Status"]) if not gov_row.empty else ""
        coverage = promotion_data_coverage(recommendations, spec)
        ranking = promotion_ranking_gate(detail, spec.challenger_id)
        regime_audit = prospective_regime_audit(recommendations, outcomes, spec)
        regime = promotion_regime_gate(regime_audit)
        rollback = rollback_plan(spec)
        prospective_gate = GATE_PASS if prospective_status == STATUS_CANDIDATE else GATE_WAIT
        prospective_reason = (
            "Challengern har klarat den förregistrerade prospektiva första grinden."
            if prospective_gate == GATE_PASS else
            "Challengern har ännu inte klarat den förregistrerade prospektiva första grinden."
        )

        gates = [
            ("Prospektivt resultat", prospective_gate, prospective_reason),
            ("Rangordning/kalibrering", ranking["status"], ranking["reason"]),
            ("Marknadslägen", regime["status"], regime["reason"]),
            ("Datatäckning", coverage["status"], coverage["reason"]),
            ("Rollback-plan", rollback["status"], "Föregående champion bevaras och explicit rollback-kontrakt finns."),
        ]
        for gate, status, reason in gates:
            gate_rows.append({"Challenger": spec.name, "Kontroll": gate, "Status": status, "Skäl": reason})

        statuses = [status for _, status, _ in gates]
        if GATE_FAIL in statuses:
            final_status = STATUS_BLOCK
            reason = "Minst en säkerhets- eller robusthetskontroll är underkänd. Champion ska behållas."
        elif all(status == GATE_PASS for status in statuses):
            final_status = STATUS_REVIEW
            reason = "Alla fördefinierade promotionskontroller är godkända. Nästa steg är ett dokumenterat manuellt releasebeslut – inte automatisk promotion."
        else:
            final_status = STATUS_WAIT
            reason = "Minst en kontroll väntar fortfarande på tillräckligt prospektivt underlag."
        rows.append({
            "Challenger": spec.name,
            "Status": final_status,
            "Godkända kontroller": int(sum(status == GATE_PASS for status in statuses)),
            "Totala kontroller": len(statuses),
            "Prospektiv status": prospective_status or "—",
            "Skäl": reason,
            "Protokoll": PROTOCOL_VERSION,
        })
    return pd.DataFrame(rows), pd.DataFrame(gate_rows)


def promotion_summary(protocol: pd.DataFrame) -> dict[str, str]:
    if protocol is None or protocol.empty:
        return {"status": STATUS_WAIT, "text": "Ingen challenger har ännu ett promotionsunderlag."}
    ready = protocol[protocol["Status"].eq(STATUS_REVIEW)]
    if not ready.empty:
        names = ", ".join(ready["Challenger"].head(2).astype(str))
        return {"status": STATUS_REVIEW, "text": f"{names} har klarat samtliga automatiska förkontroller. Ett manuellt promotions- och rollbackbeslut krävs fortfarande."}
    blocked = protocol[protocol["Status"].eq(STATUS_BLOCK)]
    if not blocked.empty:
        return {"status": STATUS_BLOCK, "text": "Minst en challenger är blockerad av robusthets- eller datakrav. Champion ska behållas."}
    return {"status": STATUS_WAIT, "text": "Ingen challenger är redo för promotion. Borsify väntar på mer prospektiv evidens och fler marknadslägen."}
