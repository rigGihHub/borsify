from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd

from independent_case_validation import independent_case_sample
from signal_ablation import SHORT_WEIGHTS

WINDOW = 12
MIN_GROUP = 4
MIN_SIGNAL_OBS = 8
SIGNAL_CORR_DROP = 0.25
SIGNAL_SHIFT = 15.0
GROUP_MEDIAN_GAP = 0.05
DATA_DROP = 0.08


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


def _rank_corr(a: pd.Series, b: pd.Series) -> float:
    work = pd.DataFrame({"a": pd.to_numeric(a, errors="coerce"), "b": pd.to_numeric(b, errors="coerce")}).dropna()
    if len(work) < MIN_SIGNAL_OBS or work["a"].nunique() < 2 or work["b"].nunique() < 2:
        return np.nan
    return float(work["a"].rank(method="average").corr(work["b"].rank(method="average")))


def _outcome_basis(frame: pd.DataFrame) -> tuple[str, str]:
    if frame is not None and not frame.empty and "excess_return_pct" in frame.columns:
        rel = pd.to_numeric(frame["excess_return_pct"], errors="coerce")
        if rel.notna().all():
            return "excess_return_pct", "Mot index"
    return "return_pct", "Rå kursutveckling"


def prepare_root_cause_sample(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str = "1m") -> pd.DataFrame:
    """Return a point-in-time, independent sample for diagnosis.

    Diagnostics deliberately use only fields frozen with each recommendation. They never
    backfill old records with current market, sector, signal or fundamental information.
    """
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame()
    req_r = {"record_id", "horizon_type", "snapshot_json"}
    req_o = {"record_id", "horizon", "return_pct"}
    if not req_r.issubset(recommendations.columns) or not req_o.issubset(outcomes.columns):
        return pd.DataFrame()
    rec = recommendations[recommendations["horizon_type"].astype(str).str.lower().eq("short")].copy()
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
    snaps = merged["snapshot_json"].map(_snapshot)
    merged["_sector"] = snaps.map(lambda s: str(s.get("Sektor") or "").strip())
    merged["_industry"] = snaps.map(lambda s: str(s.get("Bransch") or "").strip())
    merged["_regime"] = snaps.map(lambda s: str(s.get("Marknadsläge") or "").strip())
    merged["_pit"] = snaps.map(lambda s: bool(s.get("PIT Complete")) if s.get("PIT Complete") is not None else False)
    merged["_fundamental_source"] = snaps.map(lambda s: str(s.get("_Fundamental cache") or s.get("Fundamental hämtad") or "").strip())
    for label, (field, _) in SHORT_WEIGHTS.items():
        merged[f"_sig_{label}"] = snaps.map(lambda s, f=field: _num(s.get(f)))
    return independent_case_sample(merged, str(horizon)).sort_values("captured_date", kind="stable").reset_index(drop=True)


def _window_pair(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if data is None or len(data) < WINDOW * 2:
        return pd.DataFrame(), pd.DataFrame()
    return data.iloc[-WINDOW * 2:-WINDOW].copy(), data.iloc[-WINDOW:].copy()


def signal_root_causes(data: pd.DataFrame) -> list[dict[str, Any]]:
    prior, recent = _window_pair(data)
    if prior.empty:
        return []
    metric, _ = _outcome_basis(data)
    rows: list[dict[str, Any]] = []
    for label in SHORT_WEIGHTS:
        col = f"_sig_{label}"
        pc = _rank_corr(prior[col], prior[metric]) if col in prior.columns else np.nan
        rc = _rank_corr(recent[col], recent[metric]) if col in recent.columns else np.nan
        pmed = pd.to_numeric(prior.get(col), errors="coerce").median() if col in prior.columns else np.nan
        rmed = pd.to_numeric(recent.get(col), errors="coerce").median() if col in recent.columns else np.nan
        corr_delta = rc - pc if math.isfinite(pc) and math.isfinite(rc) else np.nan
        shift = rmed - pmed if math.isfinite(pmed) and math.isfinite(rmed) else np.nan
        status = "Ingen tydlig"
        if math.isfinite(corr_delta) and corr_delta <= -SIGNAL_CORR_DROP and math.isfinite(rc) and rc <= 0:
            status = "Stark kandidat"
        elif (math.isfinite(corr_delta) and corr_delta <= -0.15) or (math.isfinite(shift) and abs(shift) >= SIGNAL_SHIFT):
            status = "Möjlig"
        if status != "Ingen tydlig":
            rows.append({
                "Område": "Signal", "Kandidat": label, "Styrka": status,
                "Förklaring": (
                    f"Signal–utfall-korrelation {pc:.2f} → {rc:.2f}" if math.isfinite(pc) and math.isfinite(rc) else "För lite data för stabil korrelation"
                ) + (f"; median {pmed:.0f} → {rmed:.0f}." if math.isfinite(pmed) and math.isfinite(rmed) else "."),
                "Prioritet": 0 if status == "Stark kandidat" else 1,
            })
    return rows


def _dimension_root_causes(data: pd.DataFrame, col: str, label: str) -> list[dict[str, Any]]:
    prior, recent = _window_pair(data)
    if prior.empty or col not in data.columns:
        return []
    metric, metric_label = _outcome_basis(data)
    global_recent = pd.to_numeric(recent[metric], errors="coerce").median()
    rows: list[dict[str, Any]] = []
    for value, rg in recent.groupby(col, dropna=False):
        name = str(value or "").strip()
        if not name or len(rg) < MIN_GROUP:
            continue
        pg = prior[prior[col].astype(str).eq(name)]
        r = pd.to_numeric(rg[metric], errors="coerce").dropna()
        p = pd.to_numeric(pg[metric], errors="coerce").dropna()
        if len(r) < MIN_GROUP:
            continue
        rmed = float(r.median())
        pmed = float(p.median()) if len(p) >= MIN_GROUP else np.nan
        gap = rmed - float(global_recent) if math.isfinite(global_recent) else np.nan
        status = "Ingen tydlig"
        if math.isfinite(pmed) and rmed <= pmed - GROUP_MEDIAN_GAP and rmed <= global_recent - 0.02:
            status = "Stark kandidat"
        elif not math.isfinite(pmed) and len(r) >= MIN_GROUP and rmed <= -GROUP_MEDIAN_GAP:
            # A newly concentrated group can still be diagnostically relevant even when
            # it did not exist in the prior window. Treat it as possible, never causal.
            status = "Möjlig"
        elif rmed <= global_recent - GROUP_MEDIAN_GAP:
            status = "Möjlig"
        if status != "Ingen tydlig":
            before = f", tidigare {pmed*100:.1f}%" if math.isfinite(pmed) else ""
            rows.append({
                "Område": label, "Kandidat": name, "Styrka": status,
                "Förklaring": f"Senaste {len(r)} case: median {rmed*100:.1f}% {metric_label.lower()}{before}; senaste fönstret totalt {global_recent*100:.1f}%.",
                "Prioritet": 0 if status == "Stark kandidat" else 1,
            })
    return rows


def data_root_causes(data: pd.DataFrame) -> list[dict[str, Any]]:
    prior, recent = _window_pair(data)
    if prior.empty:
        return []
    rows: list[dict[str, Any]] = []
    p_pit = float(prior["_pit"].mean()) if "_pit" in prior.columns else np.nan
    r_pit = float(recent["_pit"].mean()) if "_pit" in recent.columns else np.nan
    sig_cols = [f"_sig_{label}" for label in SHORT_WEIGHTS]
    p_complete = float(prior[sig_cols].notna().all(axis=1).mean()) if all(c in prior.columns for c in sig_cols) else np.nan
    r_complete = float(recent[sig_cols].notna().all(axis=1).mean()) if all(c in recent.columns for c in sig_cols) else np.nan
    if math.isfinite(p_pit) and math.isfinite(r_pit) and r_pit <= p_pit - DATA_DROP:
        rows.append({"Område": "Data", "Kandidat": "PIT-kompletthet", "Styrka": "Stark kandidat" if r_pit < .90 else "Möjlig", "Förklaring": f"PIT-kompletthet har fallit från {p_pit*100:.0f}% till {r_pit*100:.0f}%.", "Prioritet": 0 if r_pit < .90 else 1})
    if math.isfinite(p_complete) and math.isfinite(r_complete) and r_complete <= p_complete - DATA_DROP:
        rows.append({"Område": "Data", "Kandidat": "Short Alpha-datatäckning", "Styrka": "Stark kandidat" if r_complete < .90 else "Möjlig", "Förklaring": f"Komplett signaldata har fallit från {p_complete*100:.0f}% till {r_complete*100:.0f}%.", "Prioritet": 0 if r_complete < .90 else 1})
    return rows


def root_cause_table(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str = "1m") -> pd.DataFrame:
    columns = ["Område", "Kandidat", "Styrka", "Förklaring"]
    data = prepare_root_cause_sample(recommendations, outcomes, horizon)
    if len(data) < WINDOW * 2:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    rows.extend(data_root_causes(data))
    rows.extend(signal_root_causes(data))
    rows.extend(_dimension_root_causes(data, "market", "Marknad"))
    rows.extend(_dimension_root_causes(data, "_sector", "Sektor"))
    rows.extend(_dimension_root_causes(data, "_regime", "Marknadsläge"))
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).sort_values(["Prioritet", "Område", "Kandidat"], kind="stable").drop(columns="Prioritet").reset_index(drop=True)


def root_cause_summary(table: pd.DataFrame, sample_n: int = 0) -> dict[str, Any]:
    if sample_n < WINDOW * 2:
        return {"status": "Vänta", "text": f"Minst {WINDOW*2} oberoende mogna case krävs innan Borsify försöker förklara en förändring."}
    if table is None or table.empty:
        return {"status": "Ingen tydlig rotorsak", "text": "Ingen enskild signal, marknad, sektor, regim eller datakvalitetsförändring sticker ut med de fasta diagnostikreglerna. Det betyder inte att modellen är frisk – bara att orsaken inte kan isoleras här."}
    strong = table[table["Styrka"].eq("Stark kandidat")]
    if not strong.empty:
        names = ", ".join((strong["Område"].astype(str) + ": " + strong["Kandidat"].astype(str)).head(3))
        return {"status": "Rotorsakskandidater hittade", "text": f"Starkast diagnostiskt avvikande just nu: {names}. Detta är associationsdiagnostik, inte bevis på orsak."}
    names = ", ".join((table["Område"].astype(str) + ": " + table["Kandidat"].astype(str)).head(3))
    return {"status": "Möjliga orsaker", "text": f"Några områden avviker och bör granskas: {names}. Underlaget räcker inte för att kalla dem rotorsaker."}
