from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta
from typing import Any, Iterable

import numpy as np
import pandas as pd


SHORT_HORIZONS = {"1m": 21, "3m": 63, "6m": 126}
LONG_HORIZONS = {"6m": 126, "1y": 252, "2y": 504}


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _safe(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if pd.isna(value) if not isinstance(value, (str, bool)) else False:
        return None
    return value


def stable_record_id(
    symbol: str,
    horizon_type: str,
    captured_date: str,
    profile: str,
    market: str,
    model_version: str,
) -> str:
    raw = "|".join([
        str(symbol).upper().strip(),
        str(horizon_type).lower().strip(),
        str(captured_date)[:10],
        str(profile).strip(),
        str(market).strip(),
        str(model_version).strip(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:28]


def snapshot_columns(horizon_type: str) -> list[str]:
    if horizon_type == "short":
        return [
            "Ticker", "Namn", "Pris", "Valuta", "Prisdatum", "Sektor",
            "Dagsförändring", "1 mån", "3 mån", "6 mån", "Volymkvot", "RSI14",
            "Avstånd SMA200", "Omsättning MSEK/dag", "Datatäckning",
            "P/E", "Forward P/E", "P/B", "EV/EBITDA", "FCF yield",
            "ROE", "Vinstmarginal", "Skuld/eget kapital", "Risk", "Värdering", "Kvalitet",
            "Short Alpha Score", "Short Alpha Gate", "Short Alpha Confidence",
            "Short Relative Strength", "Short Trend", "Short Momentum",
            "Short Participation", "Short Revisions", "Short Catalyst",
            "Short Confirmation Count", "Short Why Now", "Short Counterargument",
            "Inflection Signal", "Inflection Score",
            "Catalyst Signal", "Primary Catalyst", "Catalyst Timing",
        ]
    return [
        "Ticker", "Namn", "Pris", "Valuta", "Prisdatum", "Sektor", "INVEST Score",
        "Kvalitet", "Risk", "Värdering", "Datatäckning",
        "1 mån", "3 mån", "6 mån", "Avstånd SMA200",
        "P/E", "Forward P/E", "P/B", "EV/EBITDA", "FCF yield",
        "ROE", "Vinstmarginal", "Skuld/eget kapital",
        "Case Gate", "Case Confidence", "Case Evidence Count", "Case Veto Count",
        "Djupkontroll", "Value Trap Risk", "Deep Confidence",
        "Inflection Signal", "Inflection Score",
        "Mispricing Signal", "Mispricing Confidence",
        "Scenario Verdict", "Scenario Asymmetry", "Scenario Confidence",
        "Catalyst Signal", "Catalyst Confidence", "Primary Catalyst", "Catalyst Timing",
        "Catalyst Why Now", "Varför marknaden kan ha fel", "Devil's Advocate",
    ]


def build_recommendation_records(
    frame: pd.DataFrame,
    horizon_type: str,
    model_version: str,
    profile: str,
    market: str,
    captured_at: datetime | pd.Timestamp | None = None,
    max_records: int = 5,
) -> list[dict[str, Any]]:
    """Freeze the actual model output before future outcomes are known.

    All finalists are stored, not only winners. This is important for calibration:
    otherwise the learning dataset would itself suffer from recommendation/survivorship bias.
    """
    if frame is None or frame.empty:
        return []
    horizon_type = str(horizon_type).lower().strip()
    if horizon_type not in {"short", "long"}:
        raise ValueError("horizon_type must be 'short' or 'long'")

    captured = pd.Timestamp(captured_at or pd.Timestamp.now(tz="UTC"))
    if captured.tzinfo is None:
        captured = captured.tz_localize("UTC")
    captured_date = captured.date().isoformat()

    records: list[dict[str, Any]] = []
    keep = snapshot_columns(horizon_type)
    for rank, (_, row) in enumerate(frame.head(max_records).iterrows(), start=1):
        symbol = str(row.get("Ticker", "")).upper().strip()
        price = _num(row.get("Pris"))
        if not symbol or not math.isfinite(price) or price <= 0:
            continue

        snap = {key: _safe(row.get(key)) for key in keep if key in row.index}
        if horizon_type == "short":
            gate = str(row.get("Short Alpha Gate", "—"))
            score = _num(row.get("Short Alpha Score"))
            confidence = _num(row.get("Short Alpha Confidence"))
            why_now = str(row.get("Short Why Now", "—"))
            evidence_count = _num(row.get("Short Confirmation Count"))
        else:
            gate = str(row.get("Case Gate", "—"))
            score = _num(row.get("INVEST Score"))
            confidence = _num(row.get("Case Confidence"))
            why_now = str(row.get("Catalyst Why Now") or row.get("Varför nu") or "—")
            evidence_count = _num(row.get("Case Evidence Count"))

        record_id = stable_record_id(
            symbol, horizon_type, captured_date, profile, market, model_version
        )
        records.append({
            "record_id": record_id,
            "symbol": symbol,
            "name": str(row.get("Namn", symbol)),
            "horizon_type": horizon_type,
            "model_version": str(model_version),
            "profile": str(profile),
            "market": str(market),
            "rank": rank,
            "entry_price": price,
            "gate": gate,
            "score": None if not math.isfinite(score) else float(score),
            "confidence": None if not math.isfinite(confidence) else float(confidence),
            "evidence_count": None if not math.isfinite(evidence_count) else int(evidence_count),
            "why_now": why_now,
            "primary_catalyst": str(row.get("Primary Catalyst", "—")),
            "captured_date": captured_date,
            "captured_at": captured.isoformat(),
            "snapshot_json": json.dumps(snap, ensure_ascii=False, sort_keys=True),
        })
    return records


def horizons_for_record(record: dict[str, Any]) -> dict[str, int]:
    return SHORT_HORIZONS.copy() if str(record.get("horizon_type")) == "short" else LONG_HORIZONS.copy()


def target_date(captured_date: str, trading_days: int) -> pd.Timestamp:
    """Calendar approximation used only to decide when an outcome is due.

    Exact outcome price is selected by trading-session count from price history below.
    """
    start = pd.Timestamp(captured_date)
    calendar_days = int(round(trading_days * 365.25 / 252))
    return start + pd.Timedelta(days=calendar_days)


def evaluate_record_from_history(
    record: dict[str, Any],
    history: pd.DataFrame,
    as_of: datetime | pd.Timestamp | None = None,
) -> list[dict[str, Any]]:
    """Evaluate due horizons using trading-session offsets after the recommendation date.

    The function never uses a price before captured_date and never substitutes today's
    price for a missed historical horizon. This keeps outcomes reproducible.
    """
    if history is None or history.empty or "Close" not in history:
        return []

    work = history[["Close"]].copy()
    work.index = pd.to_datetime(work.index)
    if getattr(work.index, "tz", None) is not None:
        work.index = work.index.tz_localize(None)
    work = work.sort_index()
    work = work[np.isfinite(pd.to_numeric(work["Close"], errors="coerce"))]
    if work.empty:
        return []

    captured = pd.Timestamp(str(record.get("captured_date"))[:10])
    asof = pd.Timestamp(as_of or pd.Timestamp.now(tz="UTC"))
    if asof.tzinfo is not None:
        asof = asof.tz_localize(None)
    entry_price = _num(record.get("entry_price"))
    if not math.isfinite(entry_price) or entry_price <= 0:
        return []

    after = work[work.index.normalize() >= captured.normalize()]
    if after.empty:
        return []

    out = []
    for label, trading_days in horizons_for_record(record).items():
        # session 0 is the first market close on/after capture date.
        if len(after) <= trading_days:
            continue
        row = after.iloc[trading_days]
        eval_date = after.index[trading_days]
        if eval_date > asof:
            continue
        price = _num(row["Close"])
        if not math.isfinite(price) or price <= 0:
            continue
        ret = price / entry_price - 1
        out.append({
            "record_id": str(record["record_id"]),
            "symbol": str(record["symbol"]),
            "horizon": label,
            "trading_days": int(trading_days),
            "evaluated_date": pd.Timestamp(eval_date).date().isoformat(),
            "evaluated_price": float(price),
            "return_pct": float(ret),
            "positive": bool(ret > 0),
            "gain_10": bool(ret >= 0.10),
            "loss_10": bool(ret <= -0.10),
            "evaluated_at": pd.Timestamp(as_of or pd.Timestamp.now(tz="UTC")).isoformat(),
        })
    return out


def outcome_summary(recommendations: pd.DataFrame, outcomes: pd.DataFrame) -> dict[str, Any]:
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return {
            "status": "För lite utfallsdata",
            "evaluated": 0,
            "message": "Borsify behöver fler mogna rekommendationer innan resultat kan bedömas.",
        }
    merged = outcomes.merge(
        recommendations[["record_id", "horizon_type", "gate", "score", "confidence", "model_version"]],
        on="record_id",
        how="left",
    )
    valid = merged.dropna(subset=["return_pct"])
    if valid.empty:
        return {
            "status": "För lite utfallsdata",
            "evaluated": 0,
            "message": "Inga rekommendationer har ännu ett mätbart utfall.",
        }
    return {
        "status": "Utfall finns – ännu inte statistiskt bevis",
        "evaluated": int(len(valid)),
        "median_return": float(valid["return_pct"].median()),
        "mean_return": float(valid["return_pct"].mean()),
        "hit_rate": float((valid["return_pct"] > 0).mean()),
        "gain_10_rate": float((valid["return_pct"] >= 0.10).mean()),
        "loss_10_rate": float((valid["return_pct"] <= -0.10).mean()),
        "message": "Deskriptiv uppföljning av frysta point-in-time-rekommendationer. Resultatet är inte riskjusterat eller ett bevis på framtida alpha.",
    }


def calibration_by_gate(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame()
    o = outcomes[outcomes["horizon"] == horizon].copy()
    if o.empty:
        return pd.DataFrame()
    merged = o.merge(
        recommendations[["record_id", "gate", "confidence", "score"]],
        on="record_id",
        how="left",
    ).dropna(subset=["return_pct"])
    if merged.empty:
        return pd.DataFrame()
    rows = []
    for gate, group in merged.groupby("gate", dropna=False):
        rows.append({
            "Gate": str(gate),
            "Antal": int(len(group)),
            "MedianReturn": float(group["return_pct"].median()),
            "MeanReturn": float(group["return_pct"].mean()),
            "HitRate": float((group["return_pct"] > 0).mean()),
            "Gain10": float((group["return_pct"] >= 0.10).mean()),
            "Loss10": float((group["return_pct"] <= -0.10).mean()),
        })
    return pd.DataFrame(rows).sort_values(["MedianReturn", "Antal"], ascending=[False, False])
