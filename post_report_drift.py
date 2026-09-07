from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _latest_report_date(earnings_history: pd.DataFrame | None) -> pd.Timestamp | None:
    if earnings_history is None or not isinstance(earnings_history, pd.DataFrame) or earnings_history.empty:
        return None
    try:
        idx = pd.to_datetime(earnings_history.index, errors="coerce", utc=True)
        valid = idx[idx.notna()]
        if len(valid) == 0:
            return None
        return pd.Timestamp(valid.max())
    except Exception:
        return None


def _close_series(price_history: pd.DataFrame | None) -> pd.Series:
    if price_history is None or not isinstance(price_history, pd.DataFrame) or price_history.empty:
        return pd.Series(dtype=float)
    col = "Close" if "Close" in price_history.columns else ("Adj Close" if "Adj Close" in price_history.columns else None)
    if col is None:
        return pd.Series(dtype=float)
    s = pd.to_numeric(price_history[col], errors="coerce").dropna()
    if s.empty:
        return s
    try:
        idx = pd.to_datetime(s.index, errors="coerce", utc=True)
        keep = idx.notna()
        s = s.loc[keep]
        s.index = idx[keep]
        return s.sort_index()
    except Exception:
        return pd.Series(dtype=float)


def _latest_surprise(earnings_history: pd.DataFrame | None) -> float:
    if earnings_history is None or not isinstance(earnings_history, pd.DataFrame) or earnings_history.empty:
        return np.nan
    lookup = {str(c).strip().lower(): c for c in earnings_history.columns}
    col = next((lookup[k] for k in ("surprisepercent", "surprise%", "surprise") if k in lookup), None)
    if col is None:
        return np.nan
    frame = earnings_history.copy()
    try:
        idx = pd.to_datetime(frame.index, errors="coerce", utc=True)
        frame = frame.loc[idx.notna()].copy()
        frame.index = idx[idx.notna()]
        frame = frame.sort_index(ascending=False)
    except Exception:
        pass
    s = pd.to_numeric(frame[col], errors="coerce").dropna()
    if s.empty:
        return np.nan
    value = _num(s.iloc[0])
    if np.isfinite(value) and abs(value) > 2:
        value /= 100.0
    return value


def build_post_report_drift(
    earnings_history: pd.DataFrame | None,
    price_history: pd.DataFrame | None,
    inflection_metrics: dict[str, Any] | None = None,
    now: pd.Timestamp | None = None,
) -> dict[str, Any]:
    """Describe the market's behaviour after the latest reported earnings event.

    This is an event-context diagnostic, not a standalone buy score. It uses a two-session
    reaction window to reduce ambiguity around whether a report was released before or after
    the market close, then measures the move after that reaction window. Analyst revisions are
    supporting context only and are never inferred when coverage is weak.
    """
    metrics = inflection_metrics or {}
    event = _latest_report_date(earnings_history)
    surprise = _latest_surprise(earnings_history)
    closes = _close_series(price_history)
    now = now or pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")

    base = {
        "Post-report status": "För lite data",
        "Post-report why now": "Borsify kan inte verifiera kursutvecklingen efter senaste rapporten.",
        "Post-report datum": event.date().isoformat() if event is not None else "—",
        "Post-report dagar sedan": np.nan,
        "Post-report EPS-överraskning": surprise,
        "Post-report reaktion": np.nan,
        "Post-report fortsatt rörelse": np.nan,
        "Post-report analytikerrespons": "För lite verifierbar analytikerdata",
        "Post-report stöd": False,
        "Post-report varning": False,
        "Post-report evidens": 0,
    }
    if event is None:
        return base

    days = int((now.normalize() - event.normalize()).days)
    base["Post-report dagar sedan"] = days
    if days < 0:
        base["Post-report status"] = "Rapportdatum ligger i framtiden"
        base["Post-report why now"] = "Senaste verifierbara rapporthändelse kan inte behandlas som genomförd ännu."
        return base
    if days > 90:
        base["Post-report status"] = "Rapporten är för gammal för varför-nu"
        base["Post-report why now"] = f"Senaste verifierbara rapporten är {days} dagar gammal och räknas inte som en färsk drivkraft."
        return base

    eps_change = _num(metrics.get("EPS-estimat förändring"))
    rev_balance = _num(metrics.get("EPS-revisionsbalans"))
    est_weight = _num(metrics.get("Estimat tillförlitlighetsvikt"))
    if not np.isfinite(est_weight):
        est_weight = 0.0
    analyst_dir = 0
    if est_weight >= .4:
        positive = (np.isfinite(eps_change) and eps_change >= .02) or (np.isfinite(rev_balance) and rev_balance >= .35)
        negative = (np.isfinite(eps_change) and eps_change <= -.02) or (np.isfinite(rev_balance) and rev_balance <= -.35)
        analyst_dir = 1 if positive and not negative else (-1 if negative and not positive else 0)
        base["Post-report analytikerrespons"] = (
            "Analytikerna har blivit mer positiva" if analyst_dir > 0 else
            "Analytikerna har blivit mer negativa" if analyst_dir < 0 else
            "Ingen tydlig verifierad analytikerförändring"
        )

    if closes.empty:
        return base
    prev = closes[closes.index.normalize() < event.normalize()]
    after = closes[closes.index.normalize() >= event.normalize()]
    if prev.empty or after.empty:
        return base

    # Use up to two sessions after the report to capture the initial market reaction.
    reaction_pos = min(1, len(after) - 1)
    reaction_close = _num(after.iloc[reaction_pos])
    prior_close = _num(prev.iloc[-1])
    latest_close = _num(closes.iloc[-1])
    if not (np.isfinite(reaction_close) and np.isfinite(prior_close) and prior_close > 0):
        return base
    reaction = reaction_close / prior_close - 1
    drift = latest_close / reaction_close - 1 if np.isfinite(latest_close) and reaction_close > 0 else np.nan
    base["Post-report reaktion"] = reaction
    base["Post-report fortsatt rörelse"] = drift

    evidence = int(np.isfinite(surprise)) + int(np.isfinite(reaction)) + int(np.isfinite(drift)) + int(est_weight >= .4)
    base["Post-report evidens"] = evidence

    fresh = 1 <= days <= 45
    pos_surprise = np.isfinite(surprise) and surprise >= .05
    neg_surprise = np.isfinite(surprise) and surprise <= -.05
    pos_reaction = reaction >= .02
    neg_reaction = reaction <= -.02
    pos_drift = np.isfinite(drift) and drift >= .01
    neg_drift = np.isfinite(drift) and drift <= -.03

    if fresh and pos_surprise and pos_reaction and pos_drift and analyst_dir >= 0:
        base.update({
            "Post-report status": "Positiv rapportdrift",
            "Post-report why now": "Rapporten slog förväntningarna, kursen reagerade positivt och styrkan har fortsatt efter den första reaktionen.",
            "Post-report stöd": True,
        })
    elif fresh and pos_surprise and pos_reaction and neg_drift:
        base.update({
            "Post-report status": "Bra rapport men styrkan har vänt",
            "Post-report why now": "Rapporten slog förväntningarna och kursen steg först, men utvecklingen efter reaktionen har vänt ned. Kontrollera om marknaden redan prisat in förbättringen eller om ny information tillkommit.",
            "Post-report varning": True,
        })
    elif fresh and neg_surprise and neg_reaction and (not np.isfinite(drift) or drift <= -.01):
        base.update({
            "Post-report status": "Negativ rapportdrift",
            "Post-report why now": "Rapporten missade förväntningarna och kursreaktionen har varit svag. Det talar emot ett färskt köpcase tills utvecklingen stabiliseras.",
            "Post-report varning": True,
        })
    elif fresh and pos_surprise and pos_reaction:
        base.update({
            "Post-report status": "Positiv rapportreaktion – fortsatt drift ej tydlig",
            "Post-report why now": "Rapporten slog förväntningarna och marknaden reagerade positivt, men Borsify kan ännu inte verifiera fortsatt styrka efter den första reaktionen.",
        })
    elif fresh and abs(reaction) >= .08 and (not np.isfinite(drift) or drift <= .01):
        base.update({
            "Post-report status": "Stor första reaktion – begränsad fortsatt bekräftelse",
            "Post-report why now": "Marknaden gjorde en stor rörelse direkt efter rapporten. Den fortsatta kursutvecklingen ger ännu inte tydlig extra bekräftelse.",
        })
    elif fresh:
        base.update({
            "Post-report status": "Ingen tydlig rapportdrift",
            "Post-report why now": "Senaste rapporten är färsk, men kursreaktion och efterföljande utveckling ger ingen tydlig gemensam signal.",
        })
    else:
        base.update({
            "Post-report status": "Rapporten är inte längre färsk",
            "Post-report why now": f"Senaste rapporten är {days} dagar gammal. Utfallet sparas som kontext men räknas inte som en stark varför-nu-signal.",
        })
    return base
