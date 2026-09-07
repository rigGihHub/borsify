from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict
from typing import Any, Iterable

import pandas as pd

from champion_challenger import (
    ChallengerSpec,
    STATUS_BETTER,
    STATUS_WORSE,
    STATUS_TIE,
    STATUS_WAIT,
    champion_challenger_table,
)
from signal_ablation import SHORT_WEIGHTS

REGISTRY_VERSION = "1"
REGISTERED_MODEL_VERSION = "3.07.0"
REGISTERED_DATE = "2026-09-06"
MIN_PROSPECTIVE_HORIZONS = 2
MIN_PROSPECTIVE_CASES_PER_HORIZON = 24
MIN_PROSPECTIVE_LARGEST_SAMPLE = 48

STATUS_REGISTERED = "Förregistrerad – väntar på nya case"
STATUS_RUNNING = "Prospektiv test pågår"
STATUS_CANDIDATE = "Kandidat för manuell promotionsgranskning"
STATUS_REJECT = "Stödjer fortsatt champion"
STATUS_MIXED = "Blandat prospektivt resultat"


@dataclass(frozen=True)
class ProspectiveChallenger:
    challenger_id: str
    name: str
    excluded_signal: str
    hypothesis: str
    registered_model_version: str = REGISTERED_MODEL_VERSION
    registered_date: str = REGISTERED_DATE
    registry_version: str = REGISTRY_VERSION


def _version_tuple(value: Any) -> tuple[int, int, int]:
    text = str(value or "").strip().lstrip("vV")
    parts = text.split(".")
    nums: list[int] = []
    for part in parts[:3]:
        digits = "".join(ch for ch in part if ch.isdigit())
        nums.append(int(digits) if digits else 0)
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])


def default_prospective_challengers() -> list[ProspectiveChallenger]:
    """Code-level pre-registration for the next untouched observations.

    IDs and hypotheses must change if the challenger definition changes. Existing
    registrations are never silently rewritten after outcomes are known.
    """
    return [
        ProspectiveChallenger(
            challenger_id=f"prospective_short_without_{i}_v1",
            name=f"Utan {label}",
            excluded_signal=label,
            hypothesis=(
                f"Förregistrerad hypotes: Short Alpha kan bli robustare utan {label.lower()}. "
                "Övriga ursprungsvikter normaliseras proportionellt; inga andra regler ändras."
            ),
        )
        for i, label in enumerate(SHORT_WEIGHTS.keys(), start=1)
    ]


def definition_fingerprint(challenger: ProspectiveChallenger) -> str:
    """Stable fingerprint of the exact pre-registered test definition."""
    payload = {
        **asdict(challenger),
        "short_weights": {k: [v[0], float(v[1])] for k, v in SHORT_WEIGHTS.items()},
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def registry_table(challengers: Iterable[ProspectiveChallenger] | None = None) -> pd.DataFrame:
    rows = []
    for spec in list(challengers or default_prospective_challengers()):
        rows.append({
            "Challenger ID": spec.challenger_id,
            "Challenger": spec.name,
            "Förregistrerad version": spec.registered_model_version,
            "Förregistrerad datum": spec.registered_date,
            "Ändring": f"Tar bort {spec.excluded_signal}",
            "Hypotes": spec.hypothesis,
            "Definition": definition_fingerprint(spec),
        })
    return pd.DataFrame(rows)


def eligible_prospective_recommendations(
    recommendations: pd.DataFrame,
    challenger: ProspectiveChallenger,
) -> pd.DataFrame:
    """Return only observations that could not have been seen at registration time."""
    if recommendations is None or recommendations.empty:
        return pd.DataFrame(columns=list(recommendations.columns) if recommendations is not None else [])
    work = recommendations.copy()
    version_col = "model_version" if "model_version" in work.columns else "PIT Model Version" if "PIT Model Version" in work.columns else None
    date_col = "captured_date" if "captured_date" in work.columns else "PIT Captured Date" if "PIT Captured Date" in work.columns else None
    if version_col is None or date_col is None:
        return work.iloc[0:0].copy()

    min_version = _version_tuple(challenger.registered_model_version)
    version_ok = work[version_col].map(_version_tuple).map(lambda v: v >= min_version)
    captured = pd.to_datetime(work[date_col], errors="coerce", utc=True)
    registered = pd.Timestamp(challenger.registered_date, tz="UTC")
    date_ok = captured.notna() & (captured >= registered)
    return work[version_ok & date_ok].copy()


def prospective_challenger_results(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizons: Iterable[str] | None = None,
    challengers: Iterable[ProspectiveChallenger] | None = None,
) -> pd.DataFrame:
    """Evaluate challengers only on observations created after pre-registration."""
    if outcomes is None or outcomes.empty:
        return pd.DataFrame()
    rows: list[pd.DataFrame] = []
    for registered in list(challengers or default_prospective_challengers()):
        eligible = eligible_prospective_recommendations(recommendations, registered)
        if eligible.empty:
            continue
        spec = ChallengerSpec(
            challenger_id=registered.challenger_id,
            name=registered.name,
            excluded_signal=registered.excluded_signal,
            rationale=registered.hypothesis,
        )
        detail = champion_challenger_table(eligible, outcomes, horizons=horizons, challengers=[spec])
        if detail.empty:
            continue
        detail["Förregistrerad version"] = registered.registered_model_version
        detail["Förregistrerad datum"] = registered.registered_date
        detail["Definition"] = definition_fingerprint(registered)
        rows.append(detail)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def prospective_governance(
    detail: pd.DataFrame,
    challengers: Iterable[ProspectiveChallenger] | None = None,
) -> pd.DataFrame:
    """Strict manual-review gate based only on prospective observations.

    No challenger is ever promoted here. A positive result merely creates a manual
    promotion-review candidate after enough untouched observations have matured.
    """
    specs = list(challengers or default_prospective_challengers())
    rows: list[dict[str, Any]] = []
    for spec in specs:
        group = detail[detail["Challenger ID"].eq(spec.challenger_id)].copy() if detail is not None and not detail.empty and "Challenger ID" in detail.columns else pd.DataFrame()
        if group.empty:
            rows.append({
                "Challenger": spec.name,
                "Status": STATUS_REGISTERED,
                "Utvärderade horisonter": 0,
                "Bättre horisonter": 0,
                "Sämre horisonter": 0,
                "Största oberoende sample": 0,
                "Förregistrerad": spec.registered_date,
                "Definition": definition_fingerprint(spec),
                "Skäl": "Registreringen är låst i kod. Endast nya v3.07+-case efter registreringsdatumet får räknas.",
            })
            continue
        evaluated = group[group["Status"].isin({STATUS_BETTER, STATUS_WORSE, STATUS_TIE})]
        better = int((evaluated["Status"] == STATUS_BETTER).sum())
        worse = int((evaluated["Status"] == STATUS_WORSE).sum())
        n_eval = int(len(evaluated))
        max_cases = int(pd.to_numeric(group.get("Oberoende case"), errors="coerce").fillna(0).max())

        if n_eval < MIN_PROSPECTIVE_HORIZONS or max_cases < MIN_PROSPECTIVE_LARGEST_SAMPLE:
            status = STATUS_RUNNING if max_cases > 0 else STATUS_REGISTERED
            reason = (
                "Prospektiv testning har startat men underlaget är ännu för litet. "
                f"Minst {MIN_PROSPECTIVE_HORIZONS} mogna horisonter och {MIN_PROSPECTIVE_LARGEST_SAMPLE} oberoende case på största horisonten krävs för promotionsgranskning."
            )
        elif better >= MIN_PROSPECTIVE_HORIZONS and worse == 0:
            status = STATUS_CANDIDATE
            reason = (
                f"Challengern är prospektivt bättre på {better} av {n_eval} mogna horisonter utan tydlig förlust. "
                "Detta öppnar endast en manuell promotionsgranskning; produktionen ändras inte automatiskt."
            )
        elif worse >= MIN_PROSPECTIVE_HORIZONS and better == 0:
            status = STATUS_REJECT
            reason = f"Champion är prospektivt bättre på {worse} av {n_eval} mogna horisonter. Challengern bör inte promoveras på detta underlag."
        else:
            status = STATUS_MIXED
            reason = f"Prospektiva resultat är blandade: {better} bättre och {worse} sämre horisonter. Behåll champion."
        rows.append({
            "Challenger": spec.name,
            "Status": status,
            "Utvärderade horisonter": n_eval,
            "Bättre horisonter": better,
            "Sämre horisonter": worse,
            "Största oberoende sample": max_cases,
            "Förregistrerad": spec.registered_date,
            "Definition": definition_fingerprint(spec),
            "Skäl": reason,
        })
    return pd.DataFrame(rows)


def prospective_summary(governance: pd.DataFrame) -> dict[str, str]:
    if governance is None or governance.empty:
        return {"status": STATUS_REGISTERED, "text": "Prospektiva challengers är registrerade men inga nya case har hunnit mogna."}
    candidates = governance[governance["Status"].eq(STATUS_CANDIDATE)]
    if not candidates.empty:
        names = ", ".join(candidates["Challenger"].head(2).astype(str))
        return {"status": STATUS_CANDIDATE, "text": f"{names} har klarat den prospektiva första grinden. Manuell promotionsgranskning krävs innan någon produktionsändring."}
    running = governance[governance["Status"].eq(STATUS_RUNNING)]
    if not running.empty:
        return {"status": STATUS_RUNNING, "text": "Prospektiv champion–challenger-testning pågår. Historiska case från före registreringen räknas inte."}
    return {"status": STATUS_REGISTERED, "text": "Challengers är förregistrerade. Borsify väntar på nya, orörda v3.07+-case och mogna utfall."}
