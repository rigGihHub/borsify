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
    """Fields frozen for future point-in-time audit.

    Keep raw decision inputs and provenance that were actually available when the
    finalist was analysed. Missing values stay missing; the ledger must never fill
    historical gaps with later data.
    """
    common = [
        "Ticker", "Namn", "Pris", "Valuta", "Prisdatum", "Sektor", "Bransch",
        "Datatäckning", "P/E", "Forward P/E", "P/B", "EV/EBITDA", "FCF yield",
        "ROE", "Vinstmarginal", "Skuld/eget kapital", "Risk", "Värdering", "Kvalitet", "Marknadsläge",
        "Fundamental hämtad", "_Fundamental cache",
        "Idiosynkratisk volatilitet status", "Idiosynkratisk volatilitet",
        "Idiosynkratisk volatilitet andel", "Idiosynkratisk beta", "Idiosynkratisk volatilitet sessioner",
    ]
    catalyst = [
        "Catalyst Signal", "Catalyst Support", "Catalyst Strength", "Catalyst Confidence",
        "Primary Catalyst", "Catalyst Timing", "Catalyst Effect", "Catalyst Evidence",
        "Catalyst Evidence Type", "Catalyst Source", "Catalyst Verification",
        "Catalyst Source Quality", "Catalyst Source Quality Score",
        "Catalyst Independent Support", "Catalyst Why Now", "Catalyst Warnings",
        "Why Now Status", "Why Now Summary", "Why Now Evidence Count", "Why Now Evidence Families",
        "Why Now Contradiction Count", "Why Now Warning", "Why Now Has Independent Catalyst",
        "News Impact Status", "News Impact Summary", "News Impact Fresh Count",
        "News Impact Positive Count", "News Impact Negative Count", "News Impact Underreaction Count",
        "News Impact Primary Title", "News Impact Primary Direction", "News Impact Primary Reaction",
        "News Impact Primary Drift", "News Impact Source Quality", "News Impact Warning",
        "News Flow Status", "News Flow Summary", "News Flow Unique Items 30d",
        "News Flow Recent Items 14d", "News Flow Positive 14d", "News Flow Negative 14d",
        "News Flow Independent Positive 14d", "News Flow Independent Negative 14d",
        "News Flow Early Positive 7d", "News Flow Early Negative 7d",
        "News Flow Prior Positive 15-30d", "News Flow Prior Negative 15-30d",
        "News Flow Direction Shift", "News Flow Distinct Positive Days", "News Flow Price Pattern",
        "News Flow Median Immediate Positive", "News Flow Median Five Day Positive",
        "News Flow Median Positive Drift", "News Flow Warning",
        "News Surprise Status", "News Surprise Summary", "News Surprise Fresh Count",
        "News Surprise Meaningful Count", "News Surprise Primary Title", "News Surprise Primary Type",
        "News Surprise Primary Label", "News Surprise Primary Direction", "News Surprise Strength",
        "News Surprise Immediate Reaction", "News Surprise Five Day Reaction",
        "News Surprise Directional Immediate", "News Surprise Directional Five Day",
        "News Surprise Underreaction", "News Surprise Later Confirmation", "News Surprise Adverse Reaction",
        "News Surprise Reference N", "News Surprise Reference Median Immediate",
        "News Surprise Relative Reaction Gap", "News Surprise Source Quality", "News Surprise Warning",
    ]
    inflection = [
        "Inflection Signal", "Inflection Score", "Varför nu", "Förändringskonflikt",
        "Kvartalsdata antal", "Omsättning YoY senaste kvartal", "Omsättning acceleration",
        "Marginal YoY förändring", "Marginal YoY föregående kvartal", "FCF YoY senaste kvartal", "FCF YoY föregående kvartal", "Vinst YoY senaste kvartal", "Vinst YoY föregående kvartal",
        "Fresh Change Status", "Fresh Change Summary", "Fresh Change Positive Count", "Fresh Change Negative Count",
        "Fresh Change Comparable Metrics", "Fresh Change New Positives", "Fresh Change New Negatives",
        "EPS-estimat förändring", "EPS-estimat jämförelseperiod", "EPS-revisionsbalans",
        "Senaste EPS-överraskning", "Analytiker antal", "Reviderande analytiker senaste period",
        "Analytikertäckning", "Estimat tillförlitlighetsvikt",
        "Post-report status", "Post-report why now", "Post-report datum",
        "Post-report dagar sedan", "Post-report EPS-överraskning", "Post-report reaktion",
        "Post-report fortsatt rörelse", "Post-report analytikerrespons",
        "Post-report stöd", "Post-report varning", "Post-report evidens",
    ]
    if horizon_type == "short":
        return common + [
            "Dagsförändring", "1 mån", "3 mån", "6 mån", "12–1 momentum", "12–1 momentum score", "12–1 momentum status", "Volymkvot", "RSI14",
            "Avstånd SMA200", "Omsättning MSEK/dag",
            "Short Alpha Score", "Short Alpha Gate", "Short Alpha Confidence",
            "Short Relative Strength", "Short Trend", "Short Momentum",
            "Short Recent Momentum", "Short 12–1 Momentum", "Short 12–1 Momentum Return", "Short Momentum Text",
            "Short Participation", "Short Revisions", "Short Catalyst",
            "Short Confirmation Count", "Short Why Now", "Short Counterargument",
            "Short Vetoes", "Short Cautions", "Short Data Warning",
        ] + inflection + catalyst
    return common + [
        "INVEST Score", "Growth Score", "Djupurval", "Djupurval Nyckel", "Djupurval Linser", "Djupurval Linser text",
        "Lång Score", "Livstid Score", "REVERSAL Score", "1 mån", "3 mån", "6 mån", "Avstånd SMA200",
        "Case Gate", "Case Confidence", "Case Confidence Label", "Case Evidence Count", "Case Evidence Basis",
        "Case Veto Count", "Case Supports", "Case Neutrals", "Case Vetoes",
        "Evidence Families schema", "Evidence Family Support Count", "Evidence Family Warning Count",
        "Evidence Family Covered Count", "Evidence Family Label", "Evidence Family Supports", "Evidence Family Warnings",
        "Evidence Family Pris/värdering", "Evidence Family Pris/värdering text", "Evidence Family Pris/värdering detalj",
        "Evidence Family Bolagskvalitet", "Evidence Family Bolagskvalitet text", "Evidence Family Bolagskvalitet detalj",
        "Evidence Family Förändrade förväntningar", "Evidence Family Förändrade förväntningar text", "Evidence Family Förändrade förväntningar detalj",
        "Evidence Family Kursbekräftelse", "Evidence Family Kursbekräftelse text", "Evidence Family Kursbekräftelse detalj",
        "Evidence Family Händelse/katalysator", "Evidence Family Händelse/katalysator text", "Evidence Family Händelse/katalysator detalj",
        "Evidence Family Risk/motbevis", "Evidence Family Risk/motbevis text", "Evidence Family Risk/motbevis detalj",
        "Djupkontroll", "Value Trap Risk", "Deep Confidence", "Fleråriga styrkor",
        "Fleråriga varningar", "Rapportdatum", "Historik år",
        "Fundamental Data status", "Fundamental Data senaste rapportperiod",
        "Fundamental Data rapportålder dagar", "Fundamental Data årsrapporter",
        "Fundamental Data kvartalsrapporter", "Fundamental Data stopp",
        "Fundamental Data varningar", "Fundamental Data styrkor",
        "Vinstkvalitet status", "Vinstkvalitet varningar", "Vinstkvalitet",
        "Earnings Quality schema", "Periodiseringsrisk status",
        "Accruals/tillgångar senaste", "Accruals/tillgångar median",
        "Vinst minus OCF tillväxtgap", "Positivt OCF andel", "Positivt FCF andel",
        "Investment Discipline schema", "Kapitaldisciplin status", "Kapitaldisciplin profil",
        "Kapitaldisciplin styrkor", "Kapitaldisciplin varningar", "Kapitaldisciplin evidens",
        "Tillgångstillväxt senaste", "Tillgångstillväxt CAGR",
        "Tillgångar minus omsättning tillväxtgap", "Capex/omsättning senaste",
        "Capex/omsättning trend", "Kapitalomsättning senaste", "Kapitalomsättning trend",
        "Operativ avkastning/tillgångar senaste", "Operativ avkastning/tillgångar trend",
        "Mispricing Signal", "Mispricing Confidence", "Scenario Status", "Scenario Verdict",
        "Scenario Asymmetry", "Scenario Confidence", "Scenario Risk Label", "Scenario Note",
        "Bear EPS growth", "Bear exit P/E", "Bear upside", "Base EPS growth", "Base exit P/E",
        "Base upside", "Bull EPS growth", "Bull exit P/E", "Bull upside",
        "Varför marknaden kan ha fel", "Devil's Advocate", "Deep fetch error",
    ] + inflection + catalyst


def _pit_critical_fields(horizon_type: str) -> list[str]:
    if horizon_type == "short":
        return ["Ticker", "Pris", "Prisdatum", "Short Alpha Gate", "Short Alpha Score", "Short Alpha Confidence"]
    return [
        "Ticker", "Pris", "Prisdatum", "Case Gate", "INVEST Score", "Case Confidence",
        "Fundamental Data status", "Fundamental Data senaste rapportperiod",
    ]


def point_in_time_snapshot_summary(snapshot: dict[str, Any], horizon_type: str) -> dict[str, Any]:
    """Describe ledger completeness without treating missing data as negative evidence."""
    critical = _pit_critical_fields(str(horizon_type).lower().strip())
    missing = []
    for key in critical:
        value = snapshot.get(key)
        if value is None or (isinstance(value, str) and value.strip() in {"", "—"}):
            missing.append(key)
    present = len(critical) - len(missing)
    return {
        "critical_fields": len(critical),
        "critical_present": present,
        "critical_missing": missing,
        "complete": len(missing) == 0,
    }


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

        # Freeze the actual decision state inside snapshot_json. This avoids trying
        # to reconstruct an old decision later with a newer model version.
        if horizon_type == "short":
            recommended = gate in {"Kortsiktigt toppcase", "Starkt kortsiktigt case"}
            decision_basis = "Short Alpha Gate"
        else:
            recommended = gate in {"Toppcase", "Starkt case"}
            decision_basis = "Case Gate"
        snap["Ledger Decision"] = "RECOMMENDED" if recommended else "NOT_RECOMMENDED"
        snap["Ledger Decision Basis"] = decision_basis
        snap["Ledger Rank"] = rank
        # Point-in-time envelope: provenance is frozen beside the model inputs so
        # future diagnostics never need to infer what version/date/profile was used.
        snap["PIT Schema Version"] = 2
        snap["PIT Model Version"] = str(model_version)
        snap["PIT Captured At"] = captured.isoformat()
        snap["PIT Captured Date"] = captured_date
        snap["PIT Profile"] = str(profile)
        snap["PIT Market"] = str(market)
        pit = point_in_time_snapshot_summary(snap, horizon_type)
        snap["PIT Critical Fields"] = pit["critical_fields"]
        snap["PIT Critical Present"] = pit["critical_present"]
        snap["PIT Critical Missing"] = pit["critical_missing"]
        snap["PIT Complete"] = pit["complete"]

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
