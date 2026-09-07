from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from independent_case_validation import independent_case_sample

MIN_TOTAL = 24
MIN_BOTH = 5
MIN_SINGLE = 6
POSSIBLE_GAP = 0.04
STRONG_GAP = 0.08
MIN_HIT_DELTA = 0.10


@dataclass(frozen=True)
class ArchetypeSpec:
    name: str
    model: str
    thesis: str
    leg_a_name: str
    leg_b_name: str
    leg_a: Callable[[dict[str, Any]], bool]
    leg_b: Callable[[dict[str, Any]], bool]
    expected: int  # +1 = combination should help, -1 = combination should hurt


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


def _family_is(s: dict[str, Any], name: str, state: str) -> bool:
    return _txt(s.get(f"Evidence Family {name}")) == state.upper()


def _high_idio(s: dict[str, Any]) -> bool:
    return _txt(s.get("Idiosynkratisk volatilitet status")) in {
        "HÖG BOLAGSSPECIFIK RISK", "MYCKET HÖG BOLAGSSPECIFIK RISK"
    }


def _good_earnings_quality(s: dict[str, Any]) -> bool:
    return _txt(s.get("Vinstkvalitet status")) == "STARK VINSTKVALITET" or _txt(s.get("Periodiseringsrisk status")) == "STARKT KASSASTÖD"


def _good_capital_discipline(s: dict[str, Any]) -> bool:
    return _txt(s.get("Kapitaldisciplin status")) == "EFFEKTIV KAPITALANVÄNDNING"


def _poor_earnings_quality(s: dict[str, Any]) -> bool:
    return _txt(s.get("Vinstkvalitet status")) in {"SVAG VINSTKVALITET", "KRÄVER KONTROLL"} or _txt(s.get("Periodiseringsrisk status")) == "FÖRHÖJD RISK"


def _outcome_basis(frame: pd.DataFrame) -> tuple[str, str]:
    if "excess_return_pct" in frame.columns:
        s = pd.to_numeric(frame["excess_return_pct"], errors="coerce")
        if len(s) and s.notna().all():
            return "excess_return_pct", "Mot index"
    return "return_pct", "Rå kursutveckling"


ARCHETYPES: tuple[ArchetypeSpec, ...] = (
    ArchetypeSpec(
        "Längre momentum + relativ styrka", "short",
        "Etablerat 12–1 momentum blir mer intressant när aktien samtidigt går bättre än jämförelsegruppen.",
        "12–1 momentum", "Relativ styrka",
        lambda s: _num(s.get("Short 12–1 Momentum")) >= 65 or _num(s.get("12–1 momentum score")) >= 65,
        lambda s: _num(s.get("Short Relative Strength")) >= 60,
        +1,
    ),
    ArchetypeSpec(
        "Katalysator + kursbekräftelse", "short",
        "En konkret förändring bör vara mer användbar när marknaden också börjar bekräfta den.",
        "Katalysator/förväntningar", "Kursbekräftelse",
        lambda s: max(_num(s.get("Short Catalyst")), _num(s.get("Short Revisions"))) >= 65,
        lambda s: max(_num(s.get("Short Trend")), _num(s.get("Short Relative Strength"))) >= 60,
        +1,
    ),
    ArchetypeSpec(
        "Rapportstöd + fortsatt kursbekräftelse", "short",
        "Positiv rapportinformation bör vara starkare när efterföljande kursbeteende fortsätter bekräfta caset.",
        "Rapportstöd", "Kursbekräftelse",
        lambda s: bool(s.get("Post-report stöd")) and not bool(s.get("Post-report varning")),
        lambda s: max(_num(s.get("Short Trend")), _num(s.get("Short Relative Strength"))) >= 60,
        +1,
    ),
    ArchetypeSpec(
        "Momentum + hög bolagsspecifik risk", "short",
        "Momentum kan vara mindre robust när en stor del av rörelsen är bolagsspecifik och volatil.",
        "Momentum", "Bolagsspecifik risk",
        lambda s: _num(s.get("Short Momentum")) >= 65,
        _high_idio,
        -1,
    ),
    ArchetypeSpec(
        "Billigt + förbättrade förväntningar", "long",
        "Låg prissättning är mer intressant när förväntningarna samtidigt förbättras.",
        "Pris/värdering", "Förbättrade förväntningar",
        lambda s: _family_is(s, "Pris/värdering", "STÖD") or _num(s.get("Värdering")) >= 65,
        lambda s: _family_is(s, "Förändrade förväntningar", "STÖD"),
        +1,
    ),
    ArchetypeSpec(
        "Kvalitet + effektiv kapitalanvändning", "long",
        "Stark vinstkvalitet bör vara mer värdefull när tillväxten samtidigt använder kapital effektivt.",
        "Vinstkvalitet", "Kapitaldisciplin",
        _good_earnings_quality,
        _good_capital_discipline,
        +1,
    ),
    ArchetypeSpec(
        "Dyrt + momentum", "long",
        "Starkt momentum kan bli mindre attraktivt när värderingen redan kräver mycket.",
        "Svag värdering", "Momentum",
        lambda s: _num(s.get("Värdering")) < 40,
        lambda s: _num(s.get("3 mån")) >= 15,
        -1,
    ),
    ArchetypeSpec(
        "Högt score + svag vinstkvalitet", "long",
        "Ett högt totalbetyg bör ifrågasättas om vinsten inte stöds av kassaflödet.",
        "Högt INVEST Score", "Svag vinstkvalitet",
        lambda s: _num(s.get("INVEST Score")) >= 70,
        _poor_earnings_quality,
        -1,
    ),
)


def prepare_interaction_sample(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str = "1m",
    horizon_type: str = "short",
) -> pd.DataFrame:
    """Return independent, point-in-time observations for pre-defined interaction tests."""
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame()
    if not {"record_id", "horizon_type", "snapshot_json"}.issubset(recommendations.columns):
        return pd.DataFrame()
    if not {"record_id", "horizon", "return_pct"}.issubset(outcomes.columns):
        return pd.DataFrame()
    kind = str(horizon_type).strip().lower()
    rec = recommendations[recommendations["horizon_type"].astype(str).str.lower().eq(kind)].copy()
    out = outcomes[outcomes["horizon"].astype(str).eq(str(horizon))].copy()
    keep = [c for c in ["record_id", "symbol", "captured_date", "market", "score", "snapshot_json", "model_version"] if c in rec.columns]
    merged = rec[keep].merge(out, on="record_id", how="inner", suffixes=("", "_out"))
    if merged.empty:
        return merged
    merged["return_pct"] = pd.to_numeric(merged["return_pct"], errors="coerce")
    if "excess_return_pct" in merged.columns:
        merged["excess_return_pct"] = pd.to_numeric(merged["excess_return_pct"], errors="coerce")
    merged = merged.dropna(subset=["return_pct"]).copy()
    if merged.empty:
        return merged
    merged["_snap"] = merged["snapshot_json"].map(_snapshot)
    return independent_case_sample(merged, str(horizon)).sort_values("captured_date", kind="stable").reset_index(drop=True)


def interaction_archetype_table(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str = "1m",
    horizon_type: str = "short",
) -> pd.DataFrame:
    """Test whether two-signal combinations add information beyond either leg alone.

    The comparison group is *exactly one* of the two legs, not the entire universe.
    This makes the diagnostic closer to an interaction check and less likely to merely
    rediscover that each individual signal is useful. It remains descriptive, not causal.
    """
    cols = ["Arketyp", "Riktning", "Status", "Båda signaler", "En signal", "Median båda", "Median en", "Interaktionsgap", "Träffskillnad", "Tolkning"]
    data = prepare_interaction_sample(recommendations, outcomes, horizon, horizon_type)
    if len(data) < MIN_TOTAL:
        return pd.DataFrame(columns=cols)
    metric, metric_label = _outcome_basis(data)
    specs = [s for s in ARCHETYPES if s.model == str(horizon_type).strip().lower()]
    rows: list[dict[str, Any]] = []
    for spec in specs:
        a = data["_snap"].map(spec.leg_a).astype(bool)
        b = data["_snap"].map(spec.leg_b).astype(bool)
        both = a & b
        single = a ^ b
        both_vals = pd.to_numeric(data.loc[both, metric], errors="coerce").dropna()
        single_vals = pd.to_numeric(data.loc[single, metric], errors="coerce").dropna()
        if len(both_vals) < MIN_BOTH or len(single_vals) < MIN_SINGLE:
            continue
        med_both = float(both_vals.median())
        med_single = float(single_vals.median())
        raw_gap = med_both - med_single
        oriented_gap = raw_gap * spec.expected
        hit_both = float((both_vals > 0).mean())
        hit_single = float((single_vals > 0).mean())
        raw_hit_delta = hit_both - hit_single
        oriented_hit_delta = raw_hit_delta * spec.expected
        status = "Ingen tydlig interaction"
        if oriented_gap >= STRONG_GAP and oriented_hit_delta >= MIN_HIT_DELTA:
            status = "Stark möjlig interaction"
        elif oriented_gap >= POSSIBLE_GAP and oriented_hit_delta >= 0:
            status = "Möjlig interaction"
        elif oriented_gap <= -POSSIBLE_GAP:
            status = "Motsäger hypotesen"
        if status == "Ingen tydlig interaction":
            continue
        direction = "Positiv kombination" if spec.expected > 0 else "Riskkombination"
        rows.append({
            "Arketyp": spec.name,
            "Riktning": direction,
            "Status": status,
            "Båda signaler": int(len(both_vals)),
            "En signal": int(len(single_vals)),
            "Median båda": f"{med_both*100:.1f}%",
            "Median en": f"{med_single*100:.1f}%",
            "Interaktionsgap": f"{raw_gap*100:.1f} pp",
            "Träffskillnad": f"{raw_hit_delta*100:.1f} pp",
            "Tolkning": f"{spec.thesis} Jämför båda signalerna mot case med exakt en av dem. Utfall: {metric_label.lower()}. Association, inte kausalitet.",
            "_priority": 0 if status.startswith("Stark") else (1 if status == "Möjlig interaction" else 2),
            "_strength": oriented_gap,
        })
    if not rows:
        return pd.DataFrame(columns=cols)
    return (pd.DataFrame(rows).sort_values(["_priority", "_strength"], ascending=[True, False], kind="stable")
            .drop(columns=["_priority", "_strength"]).reset_index(drop=True))


def interaction_archetype_summary(table: pd.DataFrame, sample_size: int) -> dict[str, str]:
    if sample_size < MIN_TOTAL:
        return {"status": "Vänta", "text": f"För lite oberoende historik för interaction-test ({sample_size}/{MIN_TOTAL} case)."}
    if table is None or table.empty:
        return {"status": "Ingen tydlig interaction", "text": "Ingen fördefinierad tvåsignalskombination tillför tydlig extra information ännu."}
    strong = int(table["Status"].astype(str).str.startswith("Stark").sum())
    contradicted = int((table["Status"] == "Motsäger hypotesen").sum())
    if strong:
        return {"status": "Interactions hittade", "text": f"{strong} stark möjlig signalinteraction står ut. Granska råa case och andra horisonter innan modelländring."}
    if contradicted:
        return {"status": "Hypoteser ifrågasatta", "text": f"{contradicted} fördefinierad kombinationshypotes motsägs av nuvarande historik. Det är en granskningssignal, inte ett automatiskt beslut."}
    return {"status": "Möjliga interactions", "text": f"{len(table)} möjlig(a) kombinationseffekt(er) står ut, men underlaget är fortfarande deskriptivt."}
