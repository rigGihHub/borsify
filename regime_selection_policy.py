from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from interaction_diagnostics import prepare_interaction_sample, _num, _txt, _high_idio, _outcome_basis

MIN_TARGET_TOTAL = 16
MIN_POLICY_OK = 6
MIN_POLICY_WEAK = 6
POSSIBLE_GAP = 0.04
STRONG_GAP = 0.08
MIN_HIT_DELTA = 0.10


def _regime(value: Any) -> str:
    text = str(value or "").upper().replace(" MARKNAD", "").strip()
    return text


def _weak_regime(s: dict[str, Any]) -> bool:
    return _regime(s.get("Marknadsläge")) in {"SVAG", "MYCKET SVAG"}


def _support_count(s: dict[str, Any]) -> float:
    return _num(s.get("Evidence Family Support Count"))


@dataclass(frozen=True)
class PolicyHypothesis:
    name: str
    thesis: str
    target: Callable[[dict[str, Any]], bool]
    requirement: Callable[[dict[str, Any]], bool]


POLICIES: tuple[PolicyHypothesis, ...] = (
    PolicyHypothesis(
        "Momentum i svag marknad · kräv extra fundamental trigger",
        "När marknaden är svag bör starkt momentum ha stöd från katalysator eller förbättrade förväntningar.",
        lambda s: _weak_regime(s) and _num(s.get("Short Momentum")) >= 65,
        lambda s: max(_num(s.get("Short Catalyst")), _num(s.get("Short Revisions"))) >= 60,
    ),
    PolicyHypothesis(
        "Katalysator i svag marknad · kräv kursbekräftelse",
        "När marknaden är svag bör en stark katalysator eller revisionssignal också synas i trend eller relativ styrka.",
        lambda s: _weak_regime(s) and max(_num(s.get("Short Catalyst")), _num(s.get("Short Revisions"))) >= 65,
        lambda s: max(_num(s.get("Short Trend")), _num(s.get("Short Relative Strength"))) >= 60,
    ),
    PolicyHypothesis(
        "Bolagsspecifik risk i svag marknad · kräv bredare stöd",
        "När bolagsspecifik volatilitet är hög i svag marknad bör caset ha stöd från flera oberoende evidensfamiljer.",
        lambda s: _weak_regime(s) and _high_idio(s),
        lambda s: _support_count(s) >= 3,
    ),
)


def regime_selection_policy_table(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str = "1m",
    horizon_type: str = "short",
) -> pd.DataFrame:
    """Test locked selection-policy hypotheses without changing production rules.

    Each test stays inside the risky target cohort and compares observations that satisfy
    the proposed extra requirement with observations that do not. Only frozen point-in-time
    fields are used. The result is diagnostic evidence, never an automatic gate change.
    """
    cols = [
        "Policyhypotes", "Status", "Target-case", "Krav uppfyllt", "Krav ej uppfyllt",
        "Median med krav", "Median utan krav", "Skillnad", "Träffskillnad", "Utfallsmått", "Tolkning",
    ]
    data = prepare_interaction_sample(recommendations, outcomes, horizon, horizon_type)
    if data.empty or "_snap" not in data.columns:
        return pd.DataFrame(columns=cols)
    metric, metric_label = _outcome_basis(data)
    rows: list[dict[str, Any]] = []
    for spec in POLICIES:
        target_mask = data["_snap"].map(spec.target).astype(bool)
        target = data.loc[target_mask].copy()
        if len(target) < MIN_TARGET_TOTAL:
            continue
        ok_mask = target["_snap"].map(spec.requirement).astype(bool)
        ok = pd.to_numeric(target.loc[ok_mask, metric], errors="coerce").dropna()
        weak = pd.to_numeric(target.loc[~ok_mask, metric], errors="coerce").dropna()
        if len(ok) < MIN_POLICY_OK or len(weak) < MIN_POLICY_WEAK:
            continue
        med_ok, med_weak = float(ok.median()), float(weak.median())
        gap = med_ok - med_weak
        hit_delta = float((ok > 0).mean() - (weak > 0).mean())
        if gap >= STRONG_GAP and hit_delta >= MIN_HIT_DELTA:
            status = "Starkt stöd för högre krav"
        elif gap >= POSSIBLE_GAP and hit_delta >= 0:
            status = "Möjligt stöd för högre krav"
        elif gap <= -POSSIBLE_GAP:
            status = "Motsäger högre krav"
        else:
            status = "Ingen tydlig skillnad"
        rows.append({
            "Policyhypotes": spec.name,
            "Status": status,
            "Target-case": int(len(target)),
            "Krav uppfyllt": int(len(ok)),
            "Krav ej uppfyllt": int(len(weak)),
            "Median med krav": f"{med_ok*100:.1f}%",
            "Median utan krav": f"{med_weak*100:.1f}%",
            "Skillnad": f"{gap*100:.1f} pp",
            "Träffskillnad": f"{hit_delta*100:.1f} pp",
            "Utfallsmått": metric_label,
            "Tolkning": spec.thesis + " Testet jämför endast liknande target-case i samma svaga marknadsläge. Association, inte kausalitet.",
        })
    return pd.DataFrame(rows, columns=cols)


def regime_selection_policy_summary(table: pd.DataFrame) -> dict[str, str]:
    if table is None or table.empty:
        return {"status": "Vänta", "text": "För lite mogen point-in-time-historik för att pröva högre urvalskrav i svag marknad."}
    strong = int((table["Status"] == "Starkt stöd för högre krav").sum())
    possible = int((table["Status"] == "Möjligt stöd för högre krav").sum())
    contradicted = int((table["Status"] == "Motsäger högre krav").sum())
    if strong:
        return {"status": "Kravhypoteser får stöd", "text": f"{strong} policyhypotes(er) har starkt historiskt stöd. Detta motiverar fortsatt prospektiv testning, inte automatisk regeländring."}
    if contradicted:
        return {"status": "Kravhypoteser ifrågasatta", "text": f"{contradicted} policyhypotes(er) ser sämre ut med det föreslagna extra kravet. Ändra inte modellen utan mer evidens."}
    if possible:
        return {"status": "Möjligt stöd", "text": f"{possible} policyhypotes(er) visar möjligt stöd för högre beviskrav i svag marknad. Fortsatt validering krävs."}
    return {"status": "Ingen tydlig skillnad", "text": "Moget underlag finns, men inget föreslaget extra krav förbättrar target-casen tydligt ännu."}
