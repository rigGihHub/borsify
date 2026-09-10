from __future__ import annotations

"""Prospective champion–challenger validation for Discovery Engine 2.0.

The production discovery pool is the champion. Challenger definitions are locked in
code before future outcomes are known. They never change production selection; each
snapshot only records which stocks *would* have entered under each alternative rule.
"""

from dataclasses import dataclass, asdict
import hashlib
import json
import math
from typing import Any, Iterable

import numpy as np
import pandas as pd

from discovery_engine import build_discovery_pool
from missed_winners_engine import HORIZONS

REGISTERED_VERSION = "3.50.0"
REGISTERED_DATE = "2026-09-08"
REGISTRY_VERSION = "1"
MIN_INDEPENDENT_COHORTS = 3
MIN_WINNERS = 6

STATUS_WAIT = "För lite underlag"
STATUS_BETTER = "Challenger bättre"
STATUS_CHAMPION = "Champion bättre"
STATUS_TIE = "Ingen tydlig skillnad"


@dataclass(frozen=True)
class DiscoveryChallengerSpec:
    challenger_id: str
    name: str
    pattern: str
    rule_text: str
    registered_version: str = REGISTERED_VERSION
    registered_date: str = REGISTERED_DATE
    registry_version: str = REGISTRY_VERSION


def default_discovery_challengers() -> list[DiscoveryChallengerSpec]:
    return [
        DiscoveryChallengerSpec("quality_plus_one_v1", "Kvalitetschallenger", "Hög kvalitet", "Byt in den starkaste ej valda aktien med Kvalitet ≥ 70."),
        DiscoveryChallengerSpec("expensive_quality_v1", "Dyra kvalitetsbolag-challenger", "Dyra kvalitetsbolag", "Byt in den starkaste ej valda aktien med Kvalitet ≥ 70 och Värdering < 45."),
        DiscoveryChallengerSpec("turnaround_plus_one_v1", "Vändningschallenger", "Vändningscase", "Byt in den starkaste ej valda aktien med Kvalitet < 55 och Marknadsläge ≥ 60."),
        DiscoveryChallengerSpec("valuation_tolerance_v1", "Värderingstolerans-challenger", "Svag värderingssignal", "Byt in den starkaste ej valda aktien med Värdering < 45 men Års Score ≥ 60."),
        DiscoveryChallengerSpec("early_timing_v1", "Timing-challenger", "Svagt marknadsläge", "Byt in den starkaste ej valda aktien med Kvalitet ≥ 65, Års Score ≥ 58 och Marknadsläge < 50."),
        DiscoveryChallengerSpec("risk_observation_v1", "Risk-challenger", "Hög risk", "Byt in den starkaste ej valda aktien med Risk < 50 och Års Score ≥ 60."),
        DiscoveryChallengerSpec("coverage_completion_v1", "Datatäckningschallenger", "Låg datatäckning", "Byt in den starkaste ej valda aktien med Datatäckning < 65 % och Borsify Score ≥ 60."),
    ]


def definition_fingerprint(spec: DiscoveryChallengerSpec) -> str:
    raw = json.dumps(asdict(spec), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def registry_table(specs: Iterable[DiscoveryChallengerSpec] | None = None) -> pd.DataFrame:
    return pd.DataFrame([{
        "Challenger ID": s.challenger_id,
        "Challenger": s.name,
        "Missmönster": s.pattern,
        "Förregistrerad version": s.registered_version,
        "Förregistrerad datum": s.registered_date,
        "Låst regel": s.rule_text,
        "Definition": definition_fingerprint(s),
    } for s in list(specs or default_discovery_challengers())])


def _num(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def _eligible(frame: pd.DataFrame, spec: DiscoveryChallengerSpec) -> pd.Series:
    q = _num(frame, "Kvalitet"); v = _num(frame, "Värdering"); setup = _num(frame, "Marknadsläge")
    risk = _num(frame, "Risk"); cov = _num(frame, "Datatäckning")
    year = _num(frame, "Års Score"); bs = _num(frame, "Borsify Score")
    if spec.challenger_id == "quality_plus_one_v1": return q >= 70
    if spec.challenger_id == "expensive_quality_v1": return (q >= 70) & (v < 45)
    if spec.challenger_id == "turnaround_plus_one_v1": return (q < 55) & (setup >= 60)
    if spec.challenger_id == "valuation_tolerance_v1": return (v < 45) & (year >= 60)
    if spec.challenger_id == "early_timing_v1": return (q >= 65) & (year >= 58) & (setup < 50)
    if spec.challenger_id == "risk_observation_v1": return (risk < 50) & (year >= 60)
    if spec.challenger_id == "coverage_completion_v1": return (cov < .65) & (bs >= 60)
    return pd.Series(False, index=frame.index)


def _rank_candidate(frame: pd.DataFrame, mask: pd.Series) -> Any | None:
    cand = frame[mask].copy()
    if cand.empty:
        return None
    # Exact deterministic priority locked at registration: relevant horizon, quality,
    # incumbent score, ticker. Missing evidence is never rewarded.
    for c in ["Års Score", "Kvalitet", "Borsify Score"]:
        cand[f"__{c}"] = _num(cand, c).fillna(-1e9)
    cand["__ticker"] = cand.get("Ticker", pd.Series("", index=cand.index)).astype(str)
    cand = cand.sort_values(["__Års Score", "__Kvalitet", "__Borsify Score", "__ticker"], ascending=[False, False, False, True], kind="stable")
    return cand.index[0]


def discovery_selection_flags(frame: pd.DataFrame, max_candidates: int = 24,
                              specs: Iterable[DiscoveryChallengerSpec] | None = None) -> pd.DataFrame:
    """Freeze champion and would-have-been challenger selection before outcomes exist."""
    if frame is None or frame.empty:
        return pd.DataFrame(index=frame.index if isinstance(frame, pd.DataFrame) else None)
    work = frame.copy()
    champion = build_discovery_pool(work, max_candidates=max_candidates)
    champion_idx = list(champion.index)
    champion_set = set(champion_idx)
    out = pd.DataFrame(index=work.index)
    out["discovery_champion_selected"] = [int(i in champion_set) for i in work.index]

    # Challenger keeps pool size fixed: add exactly one pre-declared archetype candidate
    # when available and replace the champion member with lowest incumbent Borsify Score.
    for spec in list(specs or default_discovery_challengers()):
        selected = set(champion_set)
        mask = _eligible(work, spec) & ~work.index.to_series().isin(champion_set)
        extra = _rank_candidate(work, mask)
        if extra is not None and selected:
            drop_df = work.loc[list(selected)].copy()
            drop_df["__score"] = _num(drop_df, "Borsify Score").fillna(-1e9)
            drop_df["__ticker"] = drop_df.get("Ticker", pd.Series("", index=drop_df.index)).astype(str)
            drop_idx = drop_df.sort_values(["__score", "__ticker"], ascending=[True, False], kind="stable").index[0]
            selected.remove(drop_idx); selected.add(extra)
        out[spec.challenger_id] = [int(i in selected) for i in work.index]
    return out


def encode_challenger_flags(flags: pd.DataFrame, idx: Any) -> str:
    if flags is None or flags.empty or idx not in flags.index:
        return "{}"
    payload = {s.challenger_id: int(flags.at[idx, s.challenger_id]) for s in default_discovery_challengers() if s.challenger_id in flags.columns}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _decode_flag(value: Any, challenger_id: str) -> float:
    try:
        data = value if isinstance(value, dict) else json.loads(str(value or "{}"))
        x = data.get(challenger_id)
        return float(x) if x in (0, 1, 0.0, 1.0) else np.nan
    except Exception:
        return np.nan


def _version_tuple(value: Any) -> tuple[int, int, int]:
    parts = str(value or "").lstrip("vV").split(".")[:3]
    vals = []
    for p in parts:
        digits = "".join(ch for ch in p if ch.isdigit())
        vals.append(int(digits) if digits else 0)
    return tuple((vals + [0, 0, 0])[:3])


def _independent_dates(values: pd.Series, gap_days: int) -> set[str]:
    dates = sorted(pd.to_datetime(values, errors="coerce").dropna().dt.normalize().unique())
    keep: list[pd.Timestamp] = []
    for raw in dates:
        d = pd.Timestamp(raw)
        if not keep or (d - keep[-1]).days >= int(gap_days):
            keep.append(d)
    return {d.date().isoformat() for d in keep}


def prospective_discovery_results(snapshots: pd.DataFrame, outcomes: pd.DataFrame,
                                  specs: Iterable[DiscoveryChallengerSpec] | None = None) -> pd.DataFrame:
    """Compare frozen selection flags only on untouched, matured post-registration cohorts."""
    cols = ["Challenger", "Challenger ID", "Horisont", "Oberoende kohorter", "Vinnare",
            "Champion fångade", "Challenger fångade", "Champion träffgrad", "Challenger träffgrad",
            "Skillnad träffgrad", "Champion median", "Challenger median", "Status", "Definition"]
    if snapshots is None or snapshots.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame(columns=cols)
    merged = outcomes.merge(snapshots, on="snapshot_id", how="inner", suffixes=("_out", ""))
    if merged.empty or "discovery_challenger_flags" not in merged.columns or "model_version" not in merged.columns:
        return pd.DataFrame(columns=cols)
    captured = pd.to_datetime(merged.get("captured_date", merged.get("captured_date_out")), errors="coerce")
    merged = merged[(captured >= pd.Timestamp(REGISTERED_DATE)) & merged["model_version"].map(lambda x: _version_tuple(x) >= _version_tuple(REGISTERED_VERSION))].copy()
    if merged.empty:
        return pd.DataFrame(columns=cols)

    rows = []
    for spec in list(specs or default_discovery_challengers()):
        for horizon, hdef in HORIZONS.items():
            h = merged[merged["horizon"].astype(str).eq(horizon)].copy()
            if h.empty: continue
            h["__challenger"] = h["discovery_challenger_flags"].map(lambda x: _decode_flag(x, spec.challenger_id))
            h["__champion"] = pd.to_numeric(h.get("discovery_champion_selected"), errors="coerce")
            h = h[h["__challenger"].isin([0, 1]) & h["__champion"].isin([0, 1])].copy()
            if h.empty: continue
            date_col = "captured_date" if "captured_date" in h.columns else "captured_date_out"
            independent = _independent_dates(h[date_col], int(hdef["min_age_days"]))
            h = h[pd.to_datetime(h[date_col], errors="coerce").dt.date.astype(str).isin(independent)].copy()
            ret = pd.to_numeric(h["return_pct"], errors="coerce")
            pct = pd.to_numeric(h["return_percentile"], errors="coerce")
            winner = (ret >= float(hdef["winner_return"])) & (pct >= .90)
            n_winners = int(winner.sum()); n_cohorts = len(independent)
            champ_capture = int((winner & h["__champion"].eq(1)).sum())
            chall_capture = int((winner & h["__challenger"].eq(1)).sum())
            champ_rate = champ_capture / n_winners if n_winners else np.nan
            chall_rate = chall_capture / n_winners if n_winners else np.nan
            champ_med = ret[h["__champion"].eq(1)].median()
            chall_med = ret[h["__challenger"].eq(1)].median()
            delta = chall_rate - champ_rate if math.isfinite(chall_rate) and math.isfinite(champ_rate) else np.nan
            dmed = chall_med - champ_med if math.isfinite(chall_med) and math.isfinite(champ_med) else np.nan
            if n_cohorts < MIN_INDEPENDENT_COHORTS or n_winners < MIN_WINNERS:
                status = STATUS_WAIT
            elif (delta >= .05 and (not math.isfinite(dmed) or dmed >= -.01)) or (math.isfinite(dmed) and dmed >= .02 and delta >= 0):
                status = STATUS_BETTER
            elif (delta <= -.05 and (not math.isfinite(dmed) or dmed <= .01)) or (math.isfinite(dmed) and dmed <= -.02 and delta <= 0):
                status = STATUS_CHAMPION
            else:
                status = STATUS_TIE
            rows.append({"Challenger": spec.name, "Challenger ID": spec.challenger_id, "Horisont": horizon,
                         "Oberoende kohorter": n_cohorts, "Vinnare": n_winners, "Champion fångade": champ_capture,
                         "Challenger fångade": chall_capture, "Champion träffgrad": champ_rate, "Challenger träffgrad": chall_rate,
                         "Skillnad träffgrad": delta, "Champion median": champ_med, "Challenger median": chall_med,
                         "Status": status, "Definition": definition_fingerprint(spec)})
    return pd.DataFrame(rows, columns=cols)


def discovery_challenger_summary(results: pd.DataFrame) -> dict[str, str]:
    if results is None or results.empty:
        return {"status": STATUS_WAIT, "text": "Discovery-challengers är förregistrerade från v3.50. Borsify väntar på nya, mogna och oberoende framtida kohorter."}
    mature = results[results["Status"].ne(STATUS_WAIT)]
    if mature.empty:
        return {"status": STATUS_WAIT, "text": "Prospektiv Discovery Champion vs Challenger pågår. Äldre case räknas inte och överlappande kohorter tunnas ut."}
    better = mature[mature["Status"].eq(STATUS_BETTER)]
    if not better.empty:
        return {"status": STATUS_BETTER, "text": "Minst en discovery-challenger fångar fler framtida vinnare utan tydligt sämre medianutfall. Detta är endast underlag för manuell granskning – produktionen ändras inte."}
    return {"status": STATUS_TIE, "text": "Mogna jämförelser finns, men ingen challenger har ännu bevisat en tydlig fördel mot nuvarande Discovery Engine."}
