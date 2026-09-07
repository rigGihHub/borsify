from __future__ import annotations

import json
import math
from typing import Any, Iterable

import pandas as pd

from interaction_diagnostics import _snapshot
from prospective_policy_registry import (
    ProspectivePolicy,
    STATUS_CANDIDATE as PROSPECTIVE_CANDIDATE,
    default_prospective_policies,
    definition_fingerprint,
    eligible_prospective_recommendations,
    prospective_policy_governance,
    prospective_policy_results,
)
from regime_selection_policy import POLICIES, regime_selection_policy_table

PROTOCOL_VERSION = "1"
GATE_PASS = "GODKÄND"
GATE_WAIT = "VÄNTA"
GATE_FAIL = "STOPP"

STATUS_WAIT = "Vänta på mer prospektiv data"
STATUS_BLOCK = "Blockerad – behåll nuvarande policy"
STATUS_REVIEW = "Redo för manuell policy-promotion"

MIN_CALIBRATION_HORIZONS = 2
MIN_REGIME_CASES = 12
MIN_REGIMES = 2
MIN_COVERAGE_CASES = 20
MIN_FIELD_COVERAGE = 0.90

_POLICY_FIELDS: dict[str, tuple[str, ...]] = {
    "policy_weak_market_momentum_fundamental_v1": (
        "Marknadsläge", "Short Momentum", "Short Catalyst", "Short Revisions",
    ),
    "policy_weak_market_catalyst_confirmation_v1": (
        "Marknadsläge", "Short Catalyst", "Short Revisions", "Short Trend", "Short Relative Strength",
    ),
    "policy_weak_market_idio_breadth_v1": (
        "Marknadsläge", "Idiosynkratisk volatilitet status", "Evidence Family Support Count",
    ),
}


def _pct(value: Any) -> float:
    text = str(value or "").strip().lower().replace("pp", "").replace("%", "").replace(",", ".")
    try:
        x = float(text)
        return x / 100.0 if math.isfinite(x) else math.nan
    except Exception:
        return math.nan


def _present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, float) and math.isnan(value):
        return False
    text = str(value).strip().lower()
    return text not in {"", "nan", "none", "null", "—", "-"}


def _policy_spec(policy: ProspectivePolicy):
    for spec in POLICIES:
        if spec.name == policy.name:
            return spec
    return None


def policy_calibration_gate(detail: pd.DataFrame, policy: ProspectivePolicy) -> dict[str, Any]:
    """Require prospective outcome gaps to be directionally coherent across horizons."""
    if detail is None or detail.empty or "Policy ID" not in detail.columns:
        return {"status": GATE_WAIT, "reason": "Ingen mogen prospektiv kalibreringshistorik finns ännu."}
    group = detail[detail["Policy ID"].eq(policy.policy_id)].copy()
    if group.empty:
        return {"status": GATE_WAIT, "reason": "Policyhypotesen saknar mogna prospektiva horisonter."}
    group["_gap"] = group.get("Skillnad", pd.Series(index=group.index, dtype=object)).map(_pct)
    group["_hit"] = group.get("Träffskillnad", pd.Series(index=group.index, dtype=object)).map(_pct)
    mature = group[group["_gap"].notna() & group["_hit"].notna()].copy()
    if len(mature) < MIN_CALIBRATION_HORIZONS:
        return {"status": GATE_WAIT, "reason": f"Minst {MIN_CALIBRATION_HORIZONS} mogna horisonter med jämförbara utfall krävs."}
    if (mature["_gap"] < -0.02).any() or (mature["_hit"] < -0.05).any():
        return {"status": GATE_FAIL, "reason": "Minst en mogen horisont visar en tydlig försämring i medianutfall eller träffgrad med det extra kravet."}
    median_gap = float(mature["_gap"].median())
    median_hit = float(mature["_hit"].median())
    if median_gap < 0.04 or median_hit < 0.05:
        return {
            "status": GATE_WAIT,
            "reason": "Effekten är ännu för liten eller ojämn: medianförbättringen måste vara minst 4 procentenheter och träffgraden minst 5 procentenheter.",
        }
    return {
        "status": GATE_PASS,
        "reason": f"Prospektiva horisonter är riktade åt samma håll (median +{median_gap*100:.1f} pp, träffgrad +{median_hit*100:.1f} pp).",
    }


def policy_data_coverage_gate(recommendations: pd.DataFrame, policy: ProspectivePolicy) -> dict[str, Any]:
    """Check that the frozen fields needed to enforce a policy are actually present."""
    eligible = eligible_prospective_recommendations(recommendations, policy)
    if eligible.empty or "snapshot_json" not in eligible.columns:
        return {"status": GATE_WAIT, "reason": "Inga prospektiva point-in-time-case med fryst snapshot finns ännu."}
    snaps = eligible["snapshot_json"].map(_snapshot)
    weak = snaps.map(lambda s: str(s.get("Marknadsläge") or "").upper().replace(" MARKNAD", "").strip() in {"SVAG", "MYCKET SVAG"})
    snaps = snaps[weak]
    if len(snaps) < MIN_COVERAGE_CASES:
        return {"status": GATE_WAIT, "reason": f"Minst {MIN_COVERAGE_CASES} prospektiva case i svag marknad krävs för datatäckningskontrollen."}
    fields = _POLICY_FIELDS.get(policy.policy_id, ())
    if not fields:
        return {"status": GATE_FAIL, "reason": "Policyn saknar ett låst datatäckningskontrakt."}
    coverages: list[tuple[str, float]] = []
    for field in fields:
        cov = float(snaps.map(lambda s: _present(s.get(field))).mean())
        coverages.append((field, cov))
    worst_field, worst_cov = min(coverages, key=lambda item: item[1])
    if worst_cov < MIN_FIELD_COVERAGE:
        return {
            "status": GATE_FAIL,
            "reason": f"Fältet {worst_field} finns bara i {worst_cov*100:.0f}% av relevanta frysta case; minst {MIN_FIELD_COVERAGE*100:.0f}% krävs.",
        }
    return {"status": GATE_PASS, "reason": f"Alla låsta policyfält har minst {worst_cov*100:.0f}% point-in-time-täckning."}


def _filter_regime(recommendations: pd.DataFrame, regime: str) -> pd.DataFrame:
    if recommendations is None or recommendations.empty or "snapshot_json" not in recommendations.columns:
        return pd.DataFrame(columns=list(recommendations.columns) if recommendations is not None else [])
    work = recommendations.copy()
    normalized = work["snapshot_json"].map(_snapshot).map(
        lambda s: str(s.get("Marknadsläge") or "").upper().replace(" MARKNAD", "").strip()
    )
    return work[normalized.eq(regime)].copy()


def policy_regime_gate(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    policy: ProspectivePolicy,
    horizons: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Require support not to depend on only one weak-market state."""
    horizons = list(horizons or ["1m", "3m", "6m"])
    eligible = eligible_prospective_recommendations(recommendations, policy)
    mature_regimes: dict[str, list[str]] = {}
    for regime in ("SVAG", "MYCKET SVAG"):
        rec = _filter_regime(eligible, regime)
        if len(rec) < MIN_REGIME_CASES:
            continue
        statuses: list[str] = []
        for horizon in horizons:
            table = regime_selection_policy_table(rec, outcomes, horizon, "short")
            if table.empty:
                continue
            row = table[table["Policyhypotes"].eq(policy.name)]
            if not row.empty:
                statuses.append(str(row.iloc[0]["Status"]))
        if statuses:
            mature_regimes[regime] = statuses
    if len(mature_regimes) < MIN_REGIMES:
        return {
            "status": GATE_WAIT,
            "reason": f"Minst {MIN_REGIMES} frysta svaga marknadslägen (SVAG och MYCKET SVAG) med moget underlag krävs före policy-promotion.",
        }
    contradicted = [r for r, statuses in mature_regimes.items() if "Motsäger högre krav" in statuses]
    if contradicted:
        return {"status": GATE_FAIL, "reason": f"Det extra kravet motsägs i moget underlag för: {', '.join(contradicted)}."}
    unsupported = [
        r for r, statuses in mature_regimes.items()
        if not any(s in {"Starkt stöd för högre krav", "Möjligt stöd för högre krav"} for s in statuses)
    ]
    if unsupported:
        return {"status": GATE_WAIT, "reason": f"Stöd saknas ännu i: {', '.join(unsupported)}."}
    return {"status": GATE_PASS, "reason": "Det extra kravet får stöd i både SVAG och MYCKET SVAG marknad utan mogen motsägelse."}


def policy_rollback_plan(policy: ProspectivePolicy) -> dict[str, str]:
    return {
        "status": GATE_PASS,
        "policy_id": policy.policy_id,
        "definition": definition_fingerprint(policy),
        "baseline": "Behåll nuvarande urvalsregler som versionslåst rollback-baseline.",
        "trigger": "Rulla tillbaka vid dataintegritetsfel, tydlig prospektiv försämring, försämrad modellhälsa eller trasig produktionskörning.",
        "action": "Återställ föregående urvalspolicy och registrera orsaken; ändrad policydefinition måste få nytt policy-ID.",
        "automatic": "Nej – både policy-promotion och rollback kräver dokumenterat manuellt beslut.",
    }


def policy_promotion_protocol(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    policies: Iterable[ProspectivePolicy] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Five-gate manual policy-promotion protocol. Never changes production rules."""
    specs = list(policies or default_prospective_policies())
    detail = prospective_policy_results(recommendations, outcomes, ["1m", "3m", "6m"], "short", specs)
    governance = prospective_policy_governance(detail, specs)
    rows: list[dict[str, Any]] = []
    gate_rows: list[dict[str, Any]] = []

    for policy in specs:
        gov = governance[governance["Policyhypotes"].eq(policy.name)] if not governance.empty else pd.DataFrame()
        gov_status = str(gov.iloc[0]["Status"]) if not gov.empty else ""
        prospective_status = GATE_PASS if gov_status == PROSPECTIVE_CANDIDATE else GATE_WAIT
        prospective_reason = (
            "Policyn har klarat den förregistrerade prospektiva första grinden."
            if prospective_status == GATE_PASS
            else "Policyn har ännu inte klarat den förregistrerade prospektiva första grinden."
        )
        calibration = policy_calibration_gate(detail, policy)
        regime = policy_regime_gate(recommendations, outcomes, policy)
        coverage = policy_data_coverage_gate(recommendations, policy)
        rollback = policy_rollback_plan(policy)

        gates = [
            ("Prospektivt stöd", prospective_status, prospective_reason),
            ("Utfall/kalibrering", calibration["status"], calibration["reason"]),
            ("Regimrobusthet", regime["status"], regime["reason"]),
            ("Datatäckning", coverage["status"], coverage["reason"]),
            ("Rollback-plan", rollback["status"], "Nuvarande policy bevaras som versionslåst baseline och rollback kräver dokumenterat manuellt beslut."),
        ]
        for gate, status, reason in gates:
            gate_rows.append({
                "Policyhypotes": policy.name,
                "Kontroll": gate,
                "Status": status,
                "Skäl": reason,
            })

        statuses = [s for _, s, _ in gates]
        if GATE_FAIL in statuses:
            final_status = STATUS_BLOCK
            reason = "Minst en säkerhets- eller robusthetskontroll är underkänd. Nuvarande urvalspolicy ska behållas."
        elif all(s == GATE_PASS for s in statuses):
            final_status = STATUS_REVIEW
            reason = "Alla fem fördefinierade kontroller är godkända. Nästa steg är ett dokumenterat manuellt releasebeslut – inte automatisk aktivering."
        else:
            final_status = STATUS_WAIT
            reason = "Minst en kontroll väntar fortfarande på tillräckligt prospektivt underlag."
        rows.append({
            "Policyhypotes": policy.name,
            "Status": final_status,
            "Godkända kontroller": int(sum(s == GATE_PASS for s in statuses)),
            "Totala kontroller": len(statuses),
            "Prospektiv status": gov_status or "—",
            "Definition": definition_fingerprint(policy),
            "Skäl": reason,
            "Protokoll": PROTOCOL_VERSION,
        })
    return pd.DataFrame(rows), pd.DataFrame(gate_rows)


def policy_promotion_summary(protocol: pd.DataFrame) -> dict[str, str]:
    if protocol is None or protocol.empty:
        return {"status": STATUS_WAIT, "text": "Ingen policy har ännu ett promotionsunderlag."}
    ready = protocol[protocol["Status"].eq(STATUS_REVIEW)]
    if not ready.empty:
        return {
            "status": STATUS_REVIEW,
            "text": f"{len(ready)} policyhypotes(er) har klarat alla fem förkontroller. Ett manuellt promotions- och rollbackbeslut krävs fortfarande.",
        }
    blocked = protocol[protocol["Status"].eq(STATUS_BLOCK)]
    if not blocked.empty:
        return {"status": STATUS_BLOCK, "text": "Minst en policy är blockerad av en säkerhets- eller robusthetskontroll. Behåll nuvarande policy."}
    return {"status": STATUS_WAIT, "text": "Policyhypoteserna väntar fortfarande på tillräckligt prospektivt underlag i någon av de fem kontrollerna."}
