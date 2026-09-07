from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any, Iterable

import pandas as pd

from regime_selection_policy import POLICIES, regime_selection_policy_table

REGISTRY_VERSION = "1"
REGISTERED_MODEL_VERSION = "3.16.0"
REGISTERED_DATE = "2026-09-06"

MIN_EVALUATED_HORIZONS = 2
MIN_LARGEST_TARGET_SAMPLE = 32

STATUS_REGISTERED = "Förregistrerad – väntar på nya case"
STATUS_RUNNING = "Prospektiv policytest pågår"
STATUS_CANDIDATE = "Kandidat för manuell policygranskning"
STATUS_KEEP = "Stödjer oförändrad policy"
STATUS_MIXED = "Blandat prospektivt resultat"

SUPPORT_STATUSES = {"Starkt stöd för högre krav", "Möjligt stöd för högre krav"}
STRONG_STATUS = "Starkt stöd för högre krav"
CONTRADICT_STATUS = "Motsäger högre krav"


@dataclass(frozen=True)
class ProspectivePolicy:
    policy_id: str
    name: str
    thesis: str
    target_definition: str
    requirement_definition: str
    registered_model_version: str = REGISTERED_MODEL_VERSION
    registered_date: str = REGISTERED_DATE
    registry_version: str = REGISTRY_VERSION


def _version_tuple(value: Any) -> tuple[int, int, int]:
    text = str(value or "").strip().lstrip("vV")
    nums: list[int] = []
    for part in text.split(".")[:3]:
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits) if digits else 0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def default_prospective_policies() -> list[ProspectivePolicy]:
    """Freeze the three v3.15 policy hypotheses before future outcomes exist.

    The text definitions are part of the registration contract. If a future release
    changes target/requirement logic, it must receive a new policy_id/registry entry;
    old prospective evidence must not be silently reinterpreted.
    """
    definitions = {
        "Momentum i svag marknad · kräv extra fundamental trigger": (
            "policy_weak_market_momentum_fundamental_v1",
            "Marknadsläge in {SVAG, MYCKET SVAG} AND Short Momentum >= 65",
            "max(Short Catalyst, Short Revisions) >= 60",
        ),
        "Katalysator i svag marknad · kräv kursbekräftelse": (
            "policy_weak_market_catalyst_confirmation_v1",
            "Marknadsläge in {SVAG, MYCKET SVAG} AND max(Short Catalyst, Short Revisions) >= 65",
            "max(Short Trend, Short Relative Strength) >= 60",
        ),
        "Bolagsspecifik risk i svag marknad · kräv bredare stöd": (
            "policy_weak_market_idio_breadth_v1",
            "Marknadsläge in {SVAG, MYCKET SVAG} AND high idiosyncratic volatility",
            "Evidence Family Support Count >= 3",
        ),
    }
    out: list[ProspectivePolicy] = []
    for spec in POLICIES:
        if spec.name not in definitions:
            continue
        policy_id, target_definition, requirement_definition = definitions[spec.name]
        out.append(ProspectivePolicy(
            policy_id=policy_id,
            name=spec.name,
            thesis=spec.thesis,
            target_definition=target_definition,
            requirement_definition=requirement_definition,
        ))
    return out


def definition_fingerprint(policy: ProspectivePolicy) -> str:
    payload = asdict(policy)
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def registry_table(policies: Iterable[ProspectivePolicy] | None = None) -> pd.DataFrame:
    rows = []
    for p in list(policies or default_prospective_policies()):
        rows.append({
            "Policy ID": p.policy_id,
            "Policyhypotes": p.name,
            "Förregistrerad version": p.registered_model_version,
            "Förregistrerad datum": p.registered_date,
            "Target": p.target_definition,
            "Extra krav": p.requirement_definition,
            "Definition": definition_fingerprint(p),
        })
    return pd.DataFrame(rows)


def eligible_prospective_recommendations(
    recommendations: pd.DataFrame,
    policy: ProspectivePolicy,
) -> pd.DataFrame:
    """Only observations created after the policy was pre-registered may count."""
    if recommendations is None or recommendations.empty:
        return pd.DataFrame(columns=list(recommendations.columns) if recommendations is not None else [])
    work = recommendations.copy()
    version_col = "model_version" if "model_version" in work.columns else "PIT Model Version" if "PIT Model Version" in work.columns else None
    date_col = "captured_date" if "captured_date" in work.columns else "PIT Captured Date" if "PIT Captured Date" in work.columns else None
    if version_col is None or date_col is None:
        return work.iloc[0:0].copy()

    min_version = _version_tuple(policy.registered_model_version)
    version_ok = work[version_col].map(_version_tuple).map(lambda v: v >= min_version)
    captured = pd.to_datetime(work[date_col], errors="coerce", utc=True)
    registered = pd.Timestamp(policy.registered_date, tz="UTC")
    date_ok = captured.notna() & (captured >= registered)
    return work[version_ok & date_ok].copy()


def prospective_policy_results(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizons: Iterable[str] | None = None,
    horizon_type: str = "short",
    policies: Iterable[ProspectivePolicy] | None = None,
) -> pd.DataFrame:
    """Evaluate locked policy hypotheses only on untouched post-registration cases."""
    if outcomes is None or outcomes.empty:
        return pd.DataFrame()
    horizons = list(horizons or ["1m", "3m", "6m"])
    specs = list(policies or default_prospective_policies())
    rows: list[dict[str, Any]] = []
    for p in specs:
        eligible = eligible_prospective_recommendations(recommendations, p)
        if eligible.empty:
            continue
        for horizon in horizons:
            detail = regime_selection_policy_table(eligible, outcomes, horizon, horizon_type)
            if detail.empty:
                continue
            match = detail[detail["Policyhypotes"].eq(p.name)]
            if match.empty:
                continue
            row = match.iloc[0].to_dict()
            row.update({
                "Policy ID": p.policy_id,
                "Horisont": horizon,
                "Förregistrerad version": p.registered_model_version,
                "Förregistrerad datum": p.registered_date,
                "Definition": definition_fingerprint(p),
            })
            rows.append(row)
    return pd.DataFrame(rows)


def prospective_policy_governance(
    detail: pd.DataFrame,
    policies: Iterable[ProspectivePolicy] | None = None,
) -> pd.DataFrame:
    """Strict manual-review gate. Never changes production selection policy."""
    rows: list[dict[str, Any]] = []
    for p in list(policies or default_prospective_policies()):
        group = detail[detail["Policy ID"].eq(p.policy_id)].copy() if detail is not None and not detail.empty and "Policy ID" in detail.columns else pd.DataFrame()
        if group.empty:
            rows.append({
                "Policyhypotes": p.name,
                "Status": STATUS_REGISTERED,
                "Utvärderade horisonter": 0,
                "Stödjande horisonter": 0,
                "Starka horisonter": 0,
                "Motsägande horisonter": 0,
                "Största target-sample": 0,
                "Förregistrerad": p.registered_date,
                "Definition": definition_fingerprint(p),
                "Skäl": "Registreringen är låst. Endast case från v3.16.0 eller senare efter registreringsdatumet får räknas.",
            })
            continue

        evaluated = group[group["Status"].isin(SUPPORT_STATUSES | {CONTRADICT_STATUS, "Ingen tydlig skillnad"})]
        support = int(evaluated["Status"].isin(SUPPORT_STATUSES).sum())
        strong = int((evaluated["Status"] == STRONG_STATUS).sum())
        contradict = int((evaluated["Status"] == CONTRADICT_STATUS).sum())
        n_eval = int(len(evaluated))
        max_target = int(pd.to_numeric(group.get("Target-case"), errors="coerce").fillna(0).max())

        if n_eval < MIN_EVALUATED_HORIZONS or max_target < MIN_LARGEST_TARGET_SAMPLE:
            status = STATUS_RUNNING if max_target > 0 else STATUS_REGISTERED
            reason = (
                f"Prospektiv testning har startat men minst {MIN_EVALUATED_HORIZONS} mogna horisonter och "
                f"{MIN_LARGEST_TARGET_SAMPLE} target-case på största horisonten krävs före manuell policygranskning."
            )
        elif support >= MIN_EVALUATED_HORIZONS and strong >= 1 and contradict == 0:
            status = STATUS_CANDIDATE
            reason = (
                f"Det extra kravet får prospektivt stöd på {support} av {n_eval} mogna horisonter, inklusive {strong} stark. "
                "Det öppnar bara en manuell policygranskning; produktionen ändras inte automatiskt."
            )
        elif contradict >= MIN_EVALUATED_HORIZONS and support == 0:
            status = STATUS_KEEP
            reason = f"Det föreslagna extra kravet motsägs på {contradict} av {n_eval} mogna horisonter. Behåll nuvarande policy."
        else:
            status = STATUS_MIXED
            reason = f"Prospektiva resultat är blandade: {support} stödjande och {contradict} motsägande horisonter. Behåll nuvarande policy tills mer data finns."

        rows.append({
            "Policyhypotes": p.name,
            "Status": status,
            "Utvärderade horisonter": n_eval,
            "Stödjande horisonter": support,
            "Starka horisonter": strong,
            "Motsägande horisonter": contradict,
            "Största target-sample": max_target,
            "Förregistrerad": p.registered_date,
            "Definition": definition_fingerprint(p),
            "Skäl": reason,
        })
    return pd.DataFrame(rows)


def prospective_policy_summary(governance: pd.DataFrame) -> dict[str, str]:
    if governance is None or governance.empty:
        return {"status": STATUS_REGISTERED, "text": "Policyhypoteserna är förregistrerade men inga nya case har hunnit mogna."}
    candidates = governance[governance["Status"].eq(STATUS_CANDIDATE)]
    if not candidates.empty:
        return {
            "status": STATUS_CANDIDATE,
            "text": f"{len(candidates)} policyhypotes(er) har klarat den prospektiva första grinden. Manuell policygranskning krävs innan någon produktionsändring.",
        }
    running = governance[governance["Status"].eq(STATUS_RUNNING)]
    if not running.empty:
        return {"status": STATUS_RUNNING, "text": "Prospektiv policytestning pågår. Historiska case från före v3.16.0 räknas inte."}
    keep = governance[governance["Status"].eq(STATUS_KEEP)]
    if not keep.empty:
        return {"status": STATUS_KEEP, "text": "Minst en förregistrerad policyhypotes stöder att nuvarande urvalsregel behålls."}
    return {"status": STATUS_MIXED, "text": "Prospektiva policyresultat är blandade. Nuvarande urvalsregler ligger kvar."}
