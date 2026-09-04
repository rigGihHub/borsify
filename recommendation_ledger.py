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
        "Djupurval", "Djupurval Nyckel", "Djupurval Linser", "Djupurval Linser text",
        "Lång Score", "Livstid Score", "REVERSAL Score",
        "Kvalitet", "Risk", "Värdering", "Datatäckning",
        "1 mån", "3 mån", "6 mån", "Avstånd SMA200",
        "P/E", "Forward P/E", "P/B", "EV/EBITDA", "FCF yield",
        "ROE", "Vinstmarginal", "Skuld/eget kapital",
        "Case Gate", "Case Confidence", "Case Evidence Count", "Case Veto Count",
        "Djupkontroll", "Value Trap Risk", "Deep Confidence",
        "Fundamental Data status", "Fundamental Data senaste rapportperiod",
        "Vinstkvalitet status",
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


def deep_selection_outcome_summary(
    recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str = "1y"
) -> pd.DataFrame:
    """Summarise realised outcomes by the frozen primary deep-selection path.

    This is descriptive audit data only. It must not automatically retune model
    weights; small samples are particularly easy to over-interpret.
    """
    columns = ["selection_path", "evaluated", "positive_rate", "mean_return", "median_return"]
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame(columns=columns)
    if "snapshot_json" not in recommendations.columns or "record_id" not in recommendations.columns:
        return pd.DataFrame(columns=columns)

    recs = recommendations.copy()
    def path_from_snapshot(raw: Any) -> str:
        try:
            snap = json.loads(raw) if isinstance(raw, str) else (raw or {})
            return str(snap.get("Djupurval Nyckel") or "unknown")
        except Exception:
            return "unknown"
    recs["selection_path"] = recs["snapshot_json"].map(path_from_snapshot)
    recs = recs[recs["selection_path"] != "unknown"]
    if recs.empty:
        return pd.DataFrame(columns=columns)

    outs = outcomes.copy()
    if "horizon" in outs.columns:
        outs = outs[outs["horizon"].astype(str) == str(horizon)]
    merged = outs.merge(recs[["record_id", "selection_path"]], on="record_id", how="inner")
    merged["return_pct"] = pd.to_numeric(merged.get("return_pct"), errors="coerce")
    merged = merged.dropna(subset=["return_pct"])
    if merged.empty:
        return pd.DataFrame(columns=columns)

    grouped = merged.groupby("selection_path", dropna=False)["return_pct"]
    result = grouped.agg(evaluated="size", mean_return="mean", median_return="median").reset_index()
    positive = merged.assign(_positive=merged["return_pct"] > 0).groupby("selection_path")["_positive"].mean()
    result["positive_rate"] = result["selection_path"].map(positive)
    return result[columns].sort_values(["evaluated", "mean_return"], ascending=[False, False]).reset_index(drop=True)


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
    benchmark_history: pd.DataFrame | None = None,
    benchmark_symbol: str | None = None,
    benchmark_name: str | None = None,
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

        # Path quality from recommendation date through the frozen horizon. These
        # diagnostics are descriptive: they show how quickly the thesis worked and
        # how painful the path was, without changing the original recommendation.
        path = after.iloc[:trading_days + 1].copy()
        path_prices = pd.to_numeric(path["Close"], errors="coerce")
        path_returns = path_prices / entry_price - 1
        best_return = float(path_returns.max()) if path_returns.notna().any() else np.nan
        worst_return = float(path_returns.min()) if path_returns.notna().any() else np.nan
        sessions_to_best = None
        if path_returns.notna().any():
            best_idx = path_returns.idxmax()
            try:
                sessions_to_best = int(path.index.get_loc(best_idx))
            except Exception:
                sessions_to_best = None

        benchmark_return = np.nan
        if benchmark_history is not None and not benchmark_history.empty and "Close" in benchmark_history:
            bench = benchmark_history[["Close"]].copy()
            bench.index = pd.to_datetime(bench.index)
            if getattr(bench.index, "tz", None) is not None:
                bench.index = bench.index.tz_localize(None)
            bench = bench.sort_index()
            bench["Close"] = pd.to_numeric(bench["Close"], errors="coerce")
            bench = bench.dropna(subset=["Close"])
            # Use the first benchmark close on/after capture and the last close on/before
            # the stock's evaluated date. This avoids requiring identical exchange calendars.
            b0 = bench[bench.index.normalize() >= captured.normalize()]
            b1 = bench[bench.index.normalize() <= pd.Timestamp(eval_date).normalize()]
            if not b0.empty and not b1.empty:
                b_start = _num(b0.iloc[0]["Close"])
                b_end = _num(b1.iloc[-1]["Close"])
                if math.isfinite(b_start) and b_start > 0 and math.isfinite(b_end) and b_end > 0:
                    benchmark_return = b_end / b_start - 1
        excess_return = ret - benchmark_return if math.isfinite(benchmark_return) else np.nan

        out.append({
            "record_id": str(record["record_id"]),
            "symbol": str(record["symbol"]),
            "horizon": label,
            "trading_days": int(trading_days),
            "evaluated_date": pd.Timestamp(eval_date).date().isoformat(),
            "evaluated_price": float(price),
            "return_pct": float(ret),
            "benchmark_symbol": str(benchmark_symbol or ""),
            "benchmark_name": str(benchmark_name or ""),
            "benchmark_return_pct": None if not math.isfinite(benchmark_return) else float(benchmark_return),
            "excess_return_pct": None if not math.isfinite(excess_return) else float(excess_return),
            "beat_benchmark": None if not math.isfinite(excess_return) else bool(excess_return > 0),
            "best_return_pct": None if not math.isfinite(best_return) else float(best_return),
            "worst_return_pct": None if not math.isfinite(worst_return) else float(worst_return),
            "sessions_to_best": sessions_to_best,
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
        "benchmark_evaluated": int(pd.to_numeric(valid.get("excess_return_pct"), errors="coerce").notna().sum()) if "excess_return_pct" in valid.columns else 0,
        "median_excess_return": float(pd.to_numeric(valid["excess_return_pct"], errors="coerce").dropna().median()) if "excess_return_pct" in valid.columns and pd.to_numeric(valid["excess_return_pct"], errors="coerce").notna().any() else np.nan,
        "beat_benchmark_rate": float((pd.to_numeric(valid["excess_return_pct"], errors="coerce").dropna() > 0).mean()) if "excess_return_pct" in valid.columns and pd.to_numeric(valid["excess_return_pct"], errors="coerce").notna().any() else np.nan,
        "median_sessions_to_best": float(pd.to_numeric(valid["sessions_to_best"], errors="coerce").dropna().median()) if "sessions_to_best" in valid.columns and pd.to_numeric(valid["sessions_to_best"], errors="coerce").notna().any() else np.nan,
        "message": "Deskriptiv uppföljning av frysta point-in-time-rekommendationer. Jämförelsen mot index är ungefärlig och resultatet är inte ett bevis på framtida överavkastning.",
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
