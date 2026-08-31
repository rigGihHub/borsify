from __future__ import annotations

import math
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import Any
from urllib.parse import quote

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

try:
    from supabase import Client, create_client
except Exception:
    Client = Any  # type: ignore
    create_client = None

APP_VERSION = "2.0.0"
APP_NAME = "Borsiq"
APP_DOMAIN = "borsiq.se"
APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "borsiq.db"
UNIVERSE_PATH = APP_DIR / "universe.csv"

OMXS30_TICKERS = [
    "ABB.ST", "ADDT-B.ST", "ALFA.ST", "ASSA-B.ST", "AZN.ST", "ATCO-A.ST",
    "BOL.ST", "EPI-A.ST", "EQT.ST", "ERIC-B.ST", "ESSITY-B.ST", "EVO.ST",
    "HM-B.ST", "HEXA-B.ST", "INDU-C.ST", "INVE-B.ST", "LIFCO-B.ST", "NIBE-B.ST",
    "NDA-SE.ST", "SAAB-B.ST", "SAND.ST", "SCA-B.ST", "SEB-A.ST", "SHB-A.ST",
    "SKF-B.ST", "SWED-A.ST", "TEL2-B.ST", "TELIA.ST", "VOLV-B.ST", "SKA-B.ST",
]

# Bred svensk bevakningslista. Detta är ett kuraterat urval av likvida svenska
# stor- och medelstora bolag, inte en officiell eller komplett Nasdaq-lista.
SWEDEN_BROAD_TICKERS = list(dict.fromkeys(OMXS30_TICKERS + [
    "AAK.ST", "AFRY.ST", "ALLEI.ST", "ARJO-B.ST", "AXFO.ST", "BALD-B.ST",
    "BEIJ-B.ST", "BETS-B.ST", "BILL.ST", "BIOT.ST", "BUFAB.ST",
    "CAST.ST", "CAT-B.ST", "CINT.ST", "DOM.ST", "ELAN-B.ST", "ELUX-B.ST",
    "EMBRAC-B.ST", "ENGCON-B.ST", "FABG.ST", "GETI-B.ST",
    "HOLM-B.ST", "HUSQ-B.ST", "INDT.ST", "KINV-B.ST", "LATO-B.ST",
    "LUG.ST", "LAGR-B.ST", "MEKO.ST", "MTRS.ST", "MYCR.ST", "NCC-B.ST", "NOBI.ST", "NOLA-B.ST",
    "NP3.ST", "NYF.ST", "PEAB-B.ST", "RATO-B.ST", "SDIP-B.ST", "SECT-B.ST",
    "SINCH.ST", "SOBI.ST", "SSAB-A.ST", "SWECO-B.ST", "HEXPOL-B.ST",
    "SYNSAM.ST", "THULE.ST", "TREL-B.ST", "VIT-B.ST",
    "WALL-B.ST", "WIHL.ST"
]))

PROFILE_WEIGHTS = {
    "Balanserad": {"valuation": .34, "quality": .28, "setup": .18, "income": .08, "risk": .12},
    "Värde": {"valuation": .50, "quality": .22, "setup": .10, "income": .08, "risk": .10},
    "Kvalitet": {"valuation": .20, "quality": .46, "setup": .10, "income": .08, "risk": .16},
    "Utdelning": {"valuation": .20, "quality": .22, "setup": .08, "income": .38, "risk": .12},
    "Turnaround": {"valuation": .27, "quality": .12, "setup": .43, "income": .03, "risk": .15},
}

SIGNAL_KINDS = [
    "Ny i topp 10",
    "Score lyfter",
    "Scoregräns passerad",
    "Målkurs nådd",
    "Kraftigt dagsfall",
    "Score faller",
]

@dataclass
class ScanConfig:
    min_market_cap_bsek: float
    min_turnover_msek: float
    require_positive_earnings: bool
    top_n: int
    profile: str


def _num(value: Any) -> float:
    try:
        if value is None:
            return np.nan
        val = float(value)
        return val if math.isfinite(val) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _pct_change(series: pd.Series, periods: int) -> float:
    s = series.dropna()
    if len(s) <= periods:
        return np.nan
    old, new = _num(s.iloc[-periods - 1]), _num(s.iloc[-1])
    return new / old - 1 if np.isfinite(old) and old != 0 and np.isfinite(new) else np.nan


def _rsi(close: pd.Series, period: int = 14) -> float:
    s = close.dropna().astype(float)
    if len(s) < period + 2:
        return np.nan
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return _num((100 - 100 / (1 + rs)).iloc[-1])


def _safe_info(ticker: yf.Ticker) -> dict[str, Any]:
    try:
        info = ticker.get_info()
        return info if isinstance(info, dict) else {}
    except Exception:
        try:
            info = ticker.info
            return info if isinstance(info, dict) else {}
        except Exception:
            return {}


@st.cache_data(ttl=21600, show_spinner=False)
def fetch_fundamentals(symbol: str) -> dict[str, Any]:
    """Fetch slower fundamental fields separately from price history.

    Fundamentals change much less often than prices, so they are cached for six
    hours. This cuts Yahoo requests significantly when users rerun the radar.
    """
    t = yf.Ticker(symbol)
    info = _safe_info(t)
    market_cap, fcf, target = _num(info.get("marketCap")), _num(info.get("freeCashflow")), _num(info.get("targetMeanPrice"))
    return {
        "Namn": info.get("shortName") or info.get("longName") or symbol,
        "Sektor": info.get("sector") or "Okänd",
        "Bransch": info.get("industry") or "Okänd",
        "Valuta": info.get("currency") or "SEK",
        "Börsvärde BSEK": market_cap / 1e9 if np.isfinite(market_cap) else np.nan,
        "P/E": _num(info.get("trailingPE")), "Forward P/E": _num(info.get("forwardPE")),
        "P/B": _num(info.get("priceToBook")), "EV/EBITDA": _num(info.get("enterpriseToEbitda")),
        "FCF-yield": fcf / market_cap if np.isfinite(fcf) and np.isfinite(market_cap) and market_cap > 0 else np.nan,
        "ROE": _num(info.get("returnOnEquity")), "Vinstmarginal": _num(info.get("profitMargins")),
        "Skuld/eget kapital": _num(info.get("debtToEquity")), "Omsättningstillväxt": _num(info.get("revenueGrowth")),
        "Vinsttillväxt": _num(info.get("earningsGrowth")), "Direktavkastning": _num(info.get("dividendYield")),
        "Utdelningsandel": _num(info.get("payoutRatio")),
        "Analytikermål": target,
        "Rekommendation": info.get("recommendationKey") or "",
        "Antal analytiker": _num(info.get("numberOfAnalystOpinions")),
        "Fundamental hämtad": datetime.now().isoformat(timespec="seconds"),
    }


@st.cache_data(ttl=900, show_spinner=False)
def fetch_bulk_price_history(symbols: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    """Download price history for the whole universe in one Yahoo request."""
    if not symbols:
        return {}
    try:
        data = yf.download(
            tickers=list(symbols), period="1y", interval="1d", auto_adjust=True,
            actions=False, group_by="ticker", threads=True, progress=False,
        )
    except Exception:
        return {}
    result: dict[str, pd.DataFrame] = {}
    if data is None or data.empty:
        return result
    if len(symbols) == 1:
        frame = data.copy()
        if isinstance(frame.columns, pd.MultiIndex):
            # Depending on yfinance version the ticker can be either level.
            try:
                frame = frame.xs(symbols[0], axis=1, level=0, drop_level=True)
            except Exception:
                try: frame = frame.xs(symbols[0], axis=1, level=1, drop_level=True)
                except Exception: pass
        result[symbols[0]] = frame
        return result
    if not isinstance(data.columns, pd.MultiIndex):
        return result
    level0 = set(map(str, data.columns.get_level_values(0)))
    level1 = set(map(str, data.columns.get_level_values(1)))
    for sym in symbols:
        try:
            if sym in level0:
                frame = data[sym].copy()
            elif sym in level1:
                frame = data.xs(sym, axis=1, level=1, drop_level=True).copy()
            else:
                continue
            result[sym] = frame
        except Exception:
            continue
    return result


@st.cache_data(ttl=900, show_spinner=False)
def fetch_single_price_history(symbol: str) -> pd.DataFrame:
    """Fallback only for symbols missing from the bulk response."""
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="1y", interval="1d", auto_adjust=True, actions=False)
        return hist if isinstance(hist, pd.DataFrame) else pd.DataFrame()
    except Exception:
        return pd.DataFrame()


def _price_snapshot(symbol: str, hist: pd.DataFrame, fundamentals: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"Ticker": symbol}
    if hist is None or hist.empty or "Close" not in hist.columns:
        row["error"] = "Ingen kurshistorik"
        return row
    hist = hist.dropna(subset=["Close"]).copy()
    if hist.empty:
        row["error"] = "Ingen kurshistorik"
        return row
    close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
    if close.empty:
        row["error"] = "Ingen giltig stängningskurs"
        return row
    price = _num(close.iloc[-1]); prev = _num(close.iloc[-2]) if len(close) >= 2 else np.nan
    high_52, low_52 = _num(close.max()), _num(close.min())
    sma50 = _num(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else np.nan
    sma200 = _num(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else np.nan
    avg20_volume = last_volume = np.nan
    if "Volume" in hist.columns:
        volume = pd.to_numeric(hist["Volume"], errors="coerce")
        avg20_volume, last_volume = _num(volume.tail(20).mean()), _num(volume.iloc[-1])
    market_cap = _num(fundamentals.get("Börsvärde BSEK"))
    target = _num(fundamentals.get("Analytikermål"))
    last_ts = pd.to_datetime(close.index[-1], errors="coerce")
    price_date = last_ts.date().isoformat() if not pd.isna(last_ts) else "—"
    row.update(fundamentals)
    row.update({
        "Pris": price, "Prisdatum": price_date,
        "Dagsförändring": price / prev - 1 if np.isfinite(prev) and prev != 0 else np.nan,
        "1 mån": _pct_change(close, 21), "3 mån": _pct_change(close, 63), "6 mån": _pct_change(close, 126),
        "1 år": _pct_change(close, min(251, max(len(close) - 1, 1))),
        "52v från topp": price / high_52 - 1 if np.isfinite(high_52) and high_52 else np.nan,
        "52v från botten": price / low_52 - 1 if np.isfinite(low_52) and low_52 else np.nan,
        "SMA50": sma50, "SMA200": sma200,
        "Avstånd SMA200": price / sma200 - 1 if np.isfinite(sma200) and sma200 else np.nan,
        "RSI14": _rsi(close),
        "Volymkvot": last_volume / avg20_volume if np.isfinite(avg20_volume) and avg20_volume > 0 else np.nan,
        "Omsättning MSEK/dag": avg20_volume * price / 1e6 if np.isfinite(avg20_volume) and np.isfinite(price) else np.nan,
        "Analytikerpotential": target / price - 1 if np.isfinite(target) and np.isfinite(price) and price > 0 else np.nan,
        "Yahoo": f"https://finance.yahoo.com/quote/{quote(symbol)}", "_history": hist.tail(260),
    })
    return row


@st.cache_data(ttl=900, show_spinner=False)
def fetch_index_snapshot() -> dict[str, float]:
    try:
        hist = yf.Ticker("^OMXS30").history(period="1mo", interval="1d", auto_adjust=True, actions=False)
        if hist is None or hist.empty:
            return {}
        close = hist["Close"].dropna().astype(float)
        return {"index": _num(close.iloc[-1]), "daily": _pct_change(close, 1), "month": _pct_change(close, min(21, max(len(close)-1, 1)))}
    except Exception:
        return {}


def _percentile_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    valid = s.notna()
    out = pd.Series(50.0, index=s.index, dtype=float)
    if valid.sum() >= 2:
        pct = s[valid].rank(pct=True, method="average") * 100
        if not higher_is_better:
            pct = 100 - pct + (100 / valid.sum())
        out.loc[valid] = pct.clip(0, 100)
    return out


def _sector_percentile_score(df: pd.DataFrame, column: str, higher_is_better: bool = True) -> pd.Series:
    """Compare valuation mainly inside sector; fall back to whole universe when sector sample is tiny."""
    result = _percentile_score(df[column], higher_is_better)
    sectors = df["Sektor"].fillna("Okänd")
    for sector, idx in sectors.groupby(sectors).groups.items():
        if sector == "Okänd" or len(idx) < 3:
            continue
        local = _percentile_score(df.loc[idx, column], higher_is_better)
        result.loc[idx] = local
    return result


def _mean_scores(parts: list[pd.Series]) -> pd.Series:
    return pd.concat(parts, axis=1).mean(axis=1) if parts else pd.Series(dtype=float)


def _risk_score(out: pd.DataFrame) -> pd.Series:
    risk = pd.Series(75.0, index=out.index)
    debt = pd.to_numeric(out["Skuld/eget kapital"], errors="coerce")
    roe = pd.to_numeric(out["ROE"], errors="coerce")
    margin = pd.to_numeric(out["Vinstmarginal"], errors="coerce")
    draw = pd.to_numeric(out["52v från topp"], errors="coerce")
    dist = pd.to_numeric(out["Avstånd SMA200"], errors="coerce")
    m3 = pd.to_numeric(out["3 mån"], errors="coerce")
    risk -= np.where(debt > 300, 25, np.where(debt > 200, 15, 0))
    risk -= np.where(roe < 0, 18, 0)
    risk -= np.where(margin < 0, 18, 0)
    risk -= np.where(draw < -.50, 16, np.where(draw < -.35, 8, 0))
    risk -= np.where((dist < -.10) & (m3 < -.15), 18, 0)
    return risk.clip(0, 100)


def add_scores(df: pd.DataFrame, profile: str) -> pd.DataFrame:
    out = df.copy()
    pe = out["P/E"].where(out["P/E"].between(2, 100))
    fpe = out["Forward P/E"].where(out["Forward P/E"].between(2, 100))
    pb = out["P/B"].where(out["P/B"].between(.1, 30))
    ev = out["EV/EBITDA"].where(out["EV/EBITDA"].between(0, 80))
    fcfy = out["FCF-yield"].where(out["FCF-yield"].between(-.5, .5))
    temp = out.assign(**{"P/E": pe, "Forward P/E": fpe, "P/B": pb, "EV/EBITDA": ev, "FCF-yield": fcfy})

    valuation = _mean_scores([
        _sector_percentile_score(temp, "P/E", False), _sector_percentile_score(temp, "Forward P/E", False),
        _sector_percentile_score(temp, "P/B", False), _sector_percentile_score(temp, "EV/EBITDA", False),
        _sector_percentile_score(temp, "FCF-yield", True), _percentile_score(out["Analytikerpotential"].clip(-.5, 1.5), True),
    ])
    debt = out["Skuld/eget kapital"].where(out["Skuld/eget kapital"].between(0, 1000))
    quality = _mean_scores([
        _percentile_score(out["ROE"].clip(-1, 2), True), _percentile_score(out["Vinstmarginal"].clip(-1, 1), True),
        _percentile_score(out["Omsättningstillväxt"].clip(-1, 2), True), _percentile_score(out["Vinsttillväxt"].clip(-1, 3), True),
        _percentile_score(debt, False),
    ])

    drawdown = pd.to_numeric(out["52v från topp"], errors="coerce")
    dip_score = pd.Series(100 * np.exp(-((drawdown + .18) / .18) ** 2), index=out.index).where(drawdown.notna(), 50).clip(0, 100)
    rsi = pd.to_numeric(out["RSI14"], errors="coerce")
    rsi_score = pd.Series(100 * np.exp(-((rsi - 43) / 18) ** 2), index=out.index).where(rsi.notna(), 50).clip(0, 100)
    momentum = _percentile_score(out["3 mån"].clip(-.8, 1.5), True)
    trend = pd.Series(50.0, index=out.index)
    dist200 = pd.to_numeric(out["Avstånd SMA200"], errors="coerce")
    trend.loc[dist200 >= 0] = 70; trend.loc[(dist200 < 0) & (dist200 >= -.10)] = 50
    trend.loc[(dist200 < -.10) & (dist200 >= -.25)] = 30; trend.loc[dist200 < -.25] = 10
    setup = .35 * dip_score + .25 * rsi_score + .25 * momentum + .15 * trend

    dy = out["Direktavkastning"].where(out["Direktavkastning"].between(0, .15))
    payout = out["Utdelningsandel"].where(out["Utdelningsandel"].between(0, 2))
    payout_quality = pd.Series(50.0, index=out.index)
    payout_quality.loc[payout.between(.25, .75)] = 85
    payout_quality.loc[payout.between(.75, 1.0)] = 65
    payout_quality.loc[payout > 1.0] = 25
    income = .70 * _percentile_score(dy, True) + .30 * payout_quality
    risk = _risk_score(out)

    out["Värdering"] = valuation.round(1); out["Kvalitet"] = quality.round(1); out["Marknadsläge"] = setup.round(1)
    out["Utdelning"] = income.round(1); out["Risk"] = risk.round(1)
    w = PROFILE_WEIGHTS[profile]
    base = sum(out[name] * w[key] for name, key in [("Värdering","valuation"),("Kvalitet","quality"),("Marknadsläge","setup"),("Utdelning","income"),("Risk","risk")])
    coverage_cols = ["P/E", "Forward P/E", "EV/EBITDA", "FCF-yield", "ROE", "Vinstmarginal", "Omsättningstillväxt", "Skuld/eget kapital"]
    coverage = out[coverage_cols].notna().mean(axis=1)
    out["Datatäckning"] = coverage
    out["Borsiq Score"] = (base * (.80 + .20 * coverage)).round(1).clip(0, 100)
    out["Riskflaggor"] = out.apply(_risk_flags, axis=1)
    out["Signal"] = out.apply(_signal_label, axis=1)
    out["Varför"] = out.apply(_why_text, axis=1)
    return out.sort_values(["Borsiq Score", "Datatäckning"], ascending=[False, False])


def _risk_flags(row: pd.Series) -> str:
    flags: list[str] = []
    pe, roe, debt, margin = map(_num, [row.get("P/E"), row.get("ROE"), row.get("Skuld/eget kapital"), row.get("Vinstmarginal")])
    draw, dist, m3, cov = map(_num, [row.get("52v från topp"), row.get("Avstånd SMA200"), row.get("3 mån"), row.get("Datatäckning")])
    if not np.isfinite(pe) or pe <= 0: flags.append("svag/okänd vinstvärdering")
    if np.isfinite(roe) and roe < 0: flags.append("negativ ROE")
    if np.isfinite(margin) and margin < 0: flags.append("negativ marginal")
    if np.isfinite(debt) and debt > 200: flags.append("hög skuldsättning")
    if np.isfinite(draw) and draw < -.45: flags.append(">45 % från 52v-topp")
    if np.isfinite(dist) and dist < -.10 and np.isfinite(m3) and m3 < -.15: flags.append("fallande lång trend")
    if np.isfinite(cov) and cov < .50: flags.append("begränsad fundamentaldata")
    return ", ".join(flags) if flags else "—"


def _signal_label(row: pd.Series) -> str:
    score = _num(row.get("Borsiq Score")); flags = str(row.get("Riskflaggor", ""))
    severe = any(x in flags for x in ["negativ ROE", "negativ marginal", "hög skuldsättning", "fallande lång trend"])
    if score >= 78 and not severe: return "Starkt fyndläge"
    if score >= 68: return "Intressant"
    if score >= 58: return "Bevaka"
    return "Svag signal"


def _why_text(row: pd.Series) -> str:
    reasons: list[str] = []
    if _num(row.get("Värdering")) >= 70: reasons.append("billig värdering relativt sektor")
    if _num(row.get("Kvalitet")) >= 70: reasons.append("stark kvalitet")
    if _num(row.get("Marknadsläge")) >= 70: reasons.append("attraktiv rekyl/setup")
    if _num(row.get("Utdelning")) >= 75: reasons.append("stark utdelningsprofil")
    dd, rsi, upside = _num(row.get("52v från topp")), _num(row.get("RSI14")), _num(row.get("Analytikerpotential"))
    if np.isfinite(dd) and -.35 <= dd <= -.08: reasons.append(f"{abs(dd):.0%} under 52v-topp")
    if np.isfinite(rsi) and 30 <= rsi <= 48: reasons.append(f"RSI {rsi:.0f}")
    if np.isfinite(upside) and upside >= .10: reasons.append(f"analytikermål +{upside:.0%}")
    return "; ".join(reasons[:3]) if reasons else "ingen enskild faktor sticker ut"


SEVERE_RISK_TERMS = ["negativ ROE", "negativ marginal", "hög skuldsättning", "fallande lång trend"]


def _daily_case(row: pd.Series, profile: str) -> dict[str, Any]:
    """Create a compact, explainable 'why today' triage without pretending to be a buy recommendation."""
    score = _num(row.get("Borsiq Score"))
    setup = _num(row.get("Marknadsläge"))
    quality = _num(row.get("Kvalitet"))
    valuation = _num(row.get("Värdering"))
    coverage = _num(row.get("Datatäckning"))
    daily = _num(row.get("Dagsförändring"))
    rsi = _num(row.get("RSI14"))
    draw = _num(row.get("52v från topp"))
    m3 = _num(row.get("3 mån"))
    flags = str(row.get("Riskflaggor", "—"))
    severe = any(term in flags for term in SEVERE_RISK_TERMS)

    prev = previous_score_snapshot(str(row.get("Ticker")), profile)
    prev_score = _num(prev.get("score")) if prev else np.nan
    delta = score - prev_score if np.isfinite(score) and np.isfinite(prev_score) else np.nan

    # 'Dagens relevans' deliberately remains separate from Borsiq Score. It emphasizes
    # current setup and recent score improvement while risk gates can cap the result.
    delta_factor = 50.0 if not np.isfinite(delta) else float(np.clip(50 + delta * 4.0, 0, 100))
    relevance = (
        .55 * (score if np.isfinite(score) else 50)
        + .20 * (setup if np.isfinite(setup) else 50)
        + .10 * (quality if np.isfinite(quality) else 50)
        + .05 * (valuation if np.isfinite(valuation) else 50)
        + .10 * delta_factor
    )
    if np.isfinite(coverage) and coverage < .60:
        relevance -= 5
    if severe:
        relevance = min(relevance - 4, 69)
    relevance = float(np.clip(relevance, 0, 100))

    if relevance >= 75 and not severe:
        priority = "Hög"
    elif relevance >= 63:
        priority = "Medel"
    else:
        priority = "Låg"

    why_today: list[str] = []
    if np.isfinite(delta) and delta >= 3:
        why_today.append(f"Borsiq Score har stigit {delta:+.1f} sedan föregående snapshot")
    elif np.isfinite(delta) and delta <= -3:
        why_today.append(f"Borsiq Score har fallit {delta:+.1f} sedan föregående snapshot")
    if np.isfinite(setup) and setup >= 70:
        why_today.append(f"marknadsläget är starkt i modellen ({setup:.0f}/100)")
    if np.isfinite(rsi) and 32 <= rsi <= 48:
        why_today.append(f"RSI {rsi:.0f} ligger i modellens rekylzon")
    if np.isfinite(draw) and -.35 <= draw <= -.08:
        why_today.append(f"kursen ligger {abs(draw):.0%} under 52-veckorstopp")
    if np.isfinite(m3) and m3 >= .08:
        why_today.append(f"3-månadersmomentum är {m3:+.0%}")
    if np.isfinite(daily) and daily <= -.04:
        why_today.append(f"aktien är ned {abs(daily):.1%} idag – kontrollera om fallet är nyhetsdrivet")
    if not why_today:
        why_today.append("hög total score snarare än en tydlig ny dagsförändring")

    changed: list[str] = []
    if prev:
        mapping = [("Värdering", "valuation"), ("Kvalitet", "quality"), ("Marknadsläge", "setup"), ("Utdelning", "income"), ("Risk", "risk")]
        diffs = []
        for label, key in mapping:
            now = _num(row.get(label)); old = _num(prev.get(key))
            if np.isfinite(now) and np.isfinite(old):
                diffs.append((abs(now-old), label, now-old))
        for _, label, d in sorted(diffs, reverse=True)[:2]:
            if abs(d) >= 1:
                changed.append(f"{label} {d:+.1f}")
    if not changed:
        changed.append("ingen tydlig komponentförändring registrerad ännu")

    caution: list[str] = []
    if flags and flags != "—":
        caution.extend([x.strip() for x in flags.split(",") if x.strip()][:2])
    if np.isfinite(coverage) and coverage < .60:
        caution.append(f"datatäckning bara {coverage:.0%}")
    if not prev:
        caution.append("saknar tidigare snapshot – dagsförändring i score kan inte bedömas")
    if not caution:
        caution.append("inga grova modellflaggor; kontrollera ändå rapport, kassaflöde och aktuell nyhetsbild")

    return {
        "Dagens relevans": round(relevance, 1),
        "Prioritet": priority,
        "Score Δ": delta,
        "Varför idag": "; ".join(why_today[:3]),
        "Förändrat": "; ".join(changed[:2]),
        "Kontrollera": "; ".join(caution[:3]),
        "Severe": severe,
    }


def build_daily_shortlist(df: pd.DataFrame, profile: str, limit: int = 5) -> pd.DataFrame:
    """Rank a small actionable shortlist from already screened shares."""
    if df.empty:
        return df.copy()
    # Do not hit history storage for the entire market; the strongest 15 by base score
    # are enough candidates for the daily triage.
    pool = df.sort_values(["Borsiq Score", "Datatäckning"], ascending=[False, False]).head(15).copy()
    cases = [_daily_case(row, profile) for _, row in pool.iterrows()]
    case_df = pd.DataFrame(cases, index=pool.index)
    for col in case_df.columns:
        pool[col] = case_df[col]
    return pool.sort_values(["Dagens relevans", "Borsiq Score", "Datatäckning"], ascending=[False, False, False]).head(limit)


def scan_universe(symbols: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """Two-stage scan: one bulk price request + cached fundamental requests."""
    symbols = list(dict.fromkeys(symbols))
    rows, errors = [], []
    price_map = fetch_bulk_price_history(tuple(symbols))
    fundamentals: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(symbols)))) as executor:
        futures = {executor.submit(fetch_fundamentals, sym): sym for sym in symbols}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                fundamentals[sym] = future.result()
            except Exception as exc:
                fundamentals[sym] = {"Namn": sym, "Sektor": "Okänd", "Bransch": "Okänd", "Valuta": "SEK", "Fundamental hämtad": "—"}
                errors.append(f"{sym}: fundamentaldata {type(exc).__name__}")
    for sym in symbols:
        hist = price_map.get(sym)
        if hist is None or hist.empty:
            hist = fetch_single_price_history(sym)
            if hist is None or hist.empty:
                errors.append(f"{sym}: ingen kurshistorik efter bulk + fallback")
                continue
        row = _price_snapshot(sym, hist, fundamentals.get(sym, {}))
        if row.get("error"):
            errors.append(f"{sym}: {row['error']}")
        else:
            rows.append(row)
    return (pd.DataFrame(rows) if rows else pd.DataFrame()), errors



@st.cache_data(ttl=1800, show_spinner=False)
def fetch_company_events(symbol: str) -> dict[str, Any]:
    """Fetch lightweight event/news data only for the stock the user opens."""
    t = yf.Ticker(symbol)
    result: dict[str, Any] = {"earnings": None, "ex_dividend": None, "news": []}
    try:
        cal = t.calendar
        if isinstance(cal, dict):
            earnings = cal.get("Earnings Date") or cal.get("EarningsDate")
            if isinstance(earnings, (list, tuple)) and earnings:
                earnings = earnings[0]
            result["earnings"] = earnings
            result["ex_dividend"] = cal.get("Ex-Dividend Date") or cal.get("ExDividendDate")
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            # yfinance has used both dict and DataFrame formats over time.
            for key in ["Earnings Date", "EarningsDate"]:
                if key in cal.index:
                    val = cal.loc[key].iloc[0]
                    result["earnings"] = val
                    break
            for key in ["Ex-Dividend Date", "ExDividendDate"]:
                if key in cal.index:
                    result["ex_dividend"] = cal.loc[key].iloc[0]
                    break
    except Exception:
        pass
    try:
        raw_news = t.news or []
        cleaned = []
        for item in raw_news[:8]:
            content = item.get("content", item) if isinstance(item, dict) else {}
            title = content.get("title") or item.get("title") if isinstance(item, dict) else None
            link = None
            if isinstance(content, dict):
                canonical = content.get("canonicalUrl") or content.get("clickThroughUrl")
                if isinstance(canonical, dict):
                    link = canonical.get("url")
                elif isinstance(canonical, str):
                    link = canonical
            if not link and isinstance(item, dict):
                link = item.get("link")
            provider = ""
            provider_obj = content.get("provider") if isinstance(content, dict) else None
            if isinstance(provider_obj, dict):
                provider = provider_obj.get("displayName") or ""
            if title:
                cleaned.append({"title": str(title), "link": link, "provider": provider})
        result["news"] = cleaned[:5]
    except Exception:
        pass
    return result


def _fmt_date(value: Any) -> str:
    if value is None:
        return "—"
    try:
        ts = pd.to_datetime(value)
        if pd.isna(ts):
            return "—"
        return ts.strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10] if value else "—"


def _supabase_config() -> tuple[str, str]:
    """Read Supabase public connection values from Streamlit secrets when available."""
    try:
        url = str(st.secrets.get("SUPABASE_URL", "")).strip()
        key = str(st.secrets.get("SUPABASE_ANON_KEY", "")).strip()
        return url, key
    except Exception:
        return "", ""


@st.cache_resource(show_spinner=False)
def _supabase_client() -> Any:
    url, key = _supabase_config()
    if not url or not key or create_client is None:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None


def cloud_enabled() -> bool:
    return _supabase_client() is not None


def current_user() -> Any:
    return st.session_state.get("bq_user")


def current_user_id() -> str | None:
    user = current_user()
    return str(getattr(user, "id", "")) or None if user is not None else None


def current_user_email() -> str:
    user = current_user()
    if user is None:
        return ""
    value = getattr(user, "email", "")
    return str(value or "").strip()


def auth_sign_in(email: str, password: str) -> tuple[bool, str]:
    client = _supabase_client()
    if client is None:
        return False, "Supabase är inte konfigurerat."
    try:
        res = client.auth.sign_in_with_password({"email": email.strip(), "password": password})
        user = getattr(res, "user", None)
        if user is None:
            return False, "Inloggningen misslyckades."
        st.session_state["bq_user"] = user
        return True, "Inloggad"
    except Exception as exc:
        return False, f"Inloggningen misslyckades: {exc}"


def auth_sign_up(email: str, password: str) -> tuple[bool, str]:
    client = _supabase_client()
    if client is None:
        return False, "Supabase är inte konfigurerat."
    try:
        res = client.auth.sign_up({"email": email.strip(), "password": password})
        user = getattr(res, "user", None)
        session = getattr(res, "session", None)
        if session is not None and user is not None:
            st.session_state["bq_user"] = user
            return True, "Konto skapat och inloggat."
        return True, "Konto skapat. Kontrollera e-post om Supabase kräver e-postbekräftelse."
    except Exception as exc:
        return False, f"Kontot kunde inte skapas: {exc}"


def auth_sign_out() -> None:
    client = _supabase_client()
    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    st.session_state.pop("bq_user", None)


def _db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_sqlite_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    cols = {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    with _db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                symbol TEXT PRIMARY KEY,
                note TEXT NOT NULL DEFAULT '',
                target_price REAL,
                added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _ensure_sqlite_column(conn, "watchlist", "signal_score_threshold", "REAL NOT NULL DEFAULT 75")
        _ensure_sqlite_column(conn, "watchlist", "signal_score_move", "REAL NOT NULL DEFAULT 8")
        _ensure_sqlite_column(conn, "watchlist", "signal_daily_drop", "REAL NOT NULL DEFAULT 5")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS score_history (
                symbol TEXT NOT NULL,
                score REAL NOT NULL,
                profile TEXT NOT NULL,
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _ensure_sqlite_column(conn, "score_history", "valuation", "REAL")
        _ensure_sqlite_column(conn, "score_history", "quality", "REAL")
        _ensure_sqlite_column(conn, "score_history", "setup", "REAL")
        _ensure_sqlite_column(conn, "score_history", "income", "REAL")
        _ensure_sqlite_column(conn, "score_history", "risk", "REAL")
        _ensure_sqlite_column(conn, "score_history", "coverage", "REAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS radar_history (
                symbol TEXT NOT NULL,
                profile TEXT NOT NULL,
                rank INTEGER NOT NULL,
                score REAL NOT NULL,
                captured_date TEXT NOT NULL,
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, profile, captured_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_history (
                event_key TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 1,
                profile TEXT NOT NULL,
                occurred_date TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                email_sent_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _ensure_sqlite_column(conn, "signal_history", "email_sent_at", "TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_preferences (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                email_enabled INTEGER NOT NULL DEFAULT 0,
                email TEXT NOT NULL DEFAULT '',
                min_priority INTEGER NOT NULL DEFAULT 2,
                notify_kinds TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO notification_preferences(singleton,notify_kinds) VALUES (1,?)",
            ("|".join(SIGNAL_KINDS),),
        )


def _cloud_watchlist() -> pd.DataFrame:
    client = _supabase_client(); uid = current_user_id()
    if client is None or not uid:
        return pd.DataFrame(columns=["symbol", "note", "target_price", "signal_score_threshold", "signal_score_move", "signal_daily_drop", "added_at"])
    try:
        res = client.table("watchlist").select("symbol,note,target_price,signal_score_threshold,signal_score_move,signal_daily_drop,added_at").eq("user_id", uid).order("added_at", desc=True).execute()
        return pd.DataFrame(res.data or [], columns=["symbol", "note", "target_price", "signal_score_threshold", "signal_score_move", "signal_daily_drop", "added_at"])
    except Exception as exc:
        st.session_state["bq_cloud_error"] = str(exc)
        return pd.DataFrame(columns=["symbol", "note", "target_price", "signal_score_threshold", "signal_score_move", "signal_daily_drop", "added_at"])


def get_watchlist() -> pd.DataFrame:
    if cloud_enabled() and current_user_id():
        return _cloud_watchlist()
    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query("SELECT symbol, note, target_price, signal_score_threshold, signal_score_move, signal_daily_drop, added_at FROM watchlist ORDER BY added_at DESC", conn)


def watched_symbols() -> list[str]:
    df = get_watchlist()
    return df["symbol"].astype(str).tolist() if not df.empty else []


def is_watched(symbol: str) -> bool:
    return symbol in set(watched_symbols())


def toggle_watchlist(symbol: str) -> None:
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        existing = client.table("watchlist").select("symbol").eq("user_id", uid).eq("symbol", symbol).execute().data or []
        if existing:
            client.table("watchlist").delete().eq("user_id", uid).eq("symbol", symbol).execute()
        else:
            client.table("watchlist").insert({"user_id": uid, "symbol": symbol}).execute()
        return
    init_db()
    with _db_connect() as conn:
        exists = conn.execute("SELECT 1 FROM watchlist WHERE symbol=?", (symbol,)).fetchone()
        if exists:
            conn.execute("DELETE FROM watchlist WHERE symbol=?", (symbol,))
        else:
            conn.execute("INSERT INTO watchlist(symbol) VALUES (?)", (symbol,))


def update_watchlist_item(
    symbol: str,
    note: str,
    target_price: float | None,
    signal_score_threshold: float = 75.0,
    signal_score_move: float = 8.0,
    signal_daily_drop: float = 5.0,
) -> None:
    target = None if target_price is None or not np.isfinite(target_price) or target_price <= 0 else float(target_price)
    score_threshold = float(np.clip(signal_score_threshold, 0, 100))
    score_move = float(np.clip(signal_score_move, 1, 50))
    daily_drop = float(np.clip(signal_daily_drop, 1, 50))
    client = _supabase_client(); uid = current_user_id()
    payload = {
        "note": note.strip(), "target_price": target,
        "signal_score_threshold": score_threshold,
        "signal_score_move": score_move,
        "signal_daily_drop": daily_drop,
    }
    if client is not None and uid:
        client.table("watchlist").update(payload).eq("user_id", uid).eq("symbol", symbol).execute()
        return
    init_db()
    with _db_connect() as conn:
        conn.execute(
            "UPDATE watchlist SET note=?, target_price=?, signal_score_threshold=?, signal_score_move=?, signal_daily_drop=? WHERE symbol=?",
            (note.strip(), target, score_threshold, score_move, daily_drop, symbol),
        )


def clear_watchlist() -> None:
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        client.table("watchlist").delete().eq("user_id", uid).execute()
        return
    init_db()
    with _db_connect() as conn:
        conn.execute("DELETE FROM watchlist")


def get_notification_preferences() -> dict[str, Any]:
    """Read e-mail notification settings. E-mail delivery itself is done server-side."""
    defaults: dict[str, Any] = {
        "email_enabled": False,
        "email": current_user_email(),
        "min_priority": 2,
        "notify_kinds": SIGNAL_KINDS.copy(),
    }
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = client.table("notification_preferences").select("email_enabled,email,min_priority,notify_kinds").eq("user_id", uid).limit(1).execute().data or []
            if not data:
                return defaults
            row = data[0]
            kinds = row.get("notify_kinds")
            if not isinstance(kinds, list):
                kinds = SIGNAL_KINDS.copy()
            return {
                "email_enabled": bool(row.get("email_enabled", False)),
                "email": str(row.get("email") or defaults["email"]),
                "min_priority": int(row.get("min_priority") or 2),
                "notify_kinds": [str(x) for x in kinds if str(x) in SIGNAL_KINDS],
            }
        except Exception as exc:
            st.session_state["bq_cloud_error"] = str(exc)
            return defaults
    init_db()
    with _db_connect() as conn:
        row = conn.execute("SELECT email_enabled,email,min_priority,notify_kinds FROM notification_preferences WHERE singleton=1").fetchone()
    if not row:
        return defaults
    kinds = [x for x in str(row[3] or "").split("|") if x in SIGNAL_KINDS] or SIGNAL_KINDS.copy()
    return {"email_enabled": bool(row[0]), "email": str(row[1] or defaults["email"]), "min_priority": int(row[2] or 2), "notify_kinds": kinds}


def update_notification_preferences(email_enabled: bool, email: str, min_priority: int, notify_kinds: list[str]) -> None:
    clean_email = email.strip()
    priority = int(np.clip(min_priority, 1, 3))
    kinds = [x for x in SIGNAL_KINDS if x in set(notify_kinds)]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        payload = {
            "user_id": uid, "email_enabled": bool(email_enabled), "email": clean_email,
            "min_priority": priority, "notify_kinds": kinds,
        }
        client.table("notification_preferences").upsert(payload, on_conflict="user_id").execute()
        return
    init_db()
    with _db_connect() as conn:
        conn.execute(
            "UPDATE notification_preferences SET email_enabled=?,email=?,min_priority=?,notify_kinds=?,updated_at=CURRENT_TIMESTAMP WHERE singleton=1",
            (1 if email_enabled else 0, clean_email, priority, "|".join(kinds)),
        )


def save_score_history(df: pd.DataFrame, profile: str) -> None:
    """Persist a daily score + component snapshot for watched shares."""
    watched = set(watched_symbols())
    if not watched or df.empty:
        return
    cols = ["Ticker", "Borsiq Score", "Värdering", "Kvalitet", "Marknadsläge", "Utdelning", "Risk", "Datatäckning"]
    rows = df[df["Ticker"].isin(watched)][cols].dropna(subset=["Borsiq Score"])
    if rows.empty:
        return
    today = datetime.now().date().isoformat()
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        for _, row in rows.iterrows():
            payload = {
                "user_id": uid, "symbol": str(row["Ticker"]), "score": float(row["Borsiq Score"]), "profile": profile, "captured_date": today,
                "valuation": _num(row.get("Värdering")), "quality": _num(row.get("Kvalitet")), "setup": _num(row.get("Marknadsläge")),
                "income": _num(row.get("Utdelning")), "risk": _num(row.get("Risk")), "coverage": _num(row.get("Datatäckning")),
            }
            payload = {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in payload.items()}
            try:
                client.table("score_history").upsert(payload, on_conflict="user_id,symbol,profile,captured_date").execute()
            except Exception:
                # Compatibility with a v1.6 schema until the migration has been run.
                fallback = {k: payload[k] for k in ["user_id", "symbol", "score", "profile", "captured_date"]}
                try: client.table("score_history").upsert(fallback, on_conflict="user_id,symbol,profile,captured_date").execute()
                except Exception: pass
        return
    init_db()
    with _db_connect() as conn:
        for _, row in rows.iterrows():
            vals = (
                float(row["Borsiq Score"]), _num(row.get("Värdering")), _num(row.get("Kvalitet")), _num(row.get("Marknadsläge")),
                _num(row.get("Utdelning")), _num(row.get("Risk")), _num(row.get("Datatäckning")),
            )
            existing = conn.execute("SELECT rowid FROM score_history WHERE symbol=? AND profile=? AND substr(captured_at,1,10)=?", (str(row["Ticker"]), profile, today)).fetchone()
            if existing:
                conn.execute("UPDATE score_history SET score=?,valuation=?,quality=?,setup=?,income=?,risk=?,coverage=?,captured_at=CURRENT_TIMESTAMP WHERE rowid=?", (*vals, existing[0]))
            else:
                conn.execute("INSERT INTO score_history(symbol,score,profile,valuation,quality,setup,income,risk,coverage) VALUES (?,?,?,?,?,?,?,?,?)", (str(row["Ticker"]), vals[0], profile, *vals[1:]))


def previous_score_snapshot(symbol: str, profile: str) -> dict[str, Any] | None:
    """Return the latest earlier daily component snapshot for explainability."""
    client = _supabase_client(); uid = current_user_id(); today = datetime.now().date().isoformat()
    fields = "score,valuation,quality,setup,income,risk,coverage,captured_date"
    try:
        if client is not None and uid:
            try:
                data = client.table("score_history").select(fields).eq("user_id", uid).eq("symbol", symbol).eq("profile", profile).lt("captured_date", today).order("captured_date", desc=True).limit(1).execute().data or []
            except Exception:
                data = client.table("score_history").select("score,captured_date").eq("user_id", uid).eq("symbol", symbol).eq("profile", profile).lt("captured_date", today).order("captured_date", desc=True).limit(1).execute().data or []
            return data[0] if data else None
        init_db()
        with _db_connect() as conn:
            row = conn.execute("SELECT score,valuation,quality,setup,income,risk,coverage,substr(captured_at,1,10) FROM score_history WHERE symbol=? AND profile=? AND substr(captured_at,1,10)<? ORDER BY captured_at DESC LIMIT 1", (symbol, profile, today)).fetchone()
            if not row: return None
            keys = ["score","valuation","quality","setup","income","risk","coverage","captured_date"]
            return dict(zip(keys, row))
    except Exception:
        return None


def _score_explanation(row: pd.Series, profile: str) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Break the score into weighted components and concrete strengths/weaknesses."""
    weights = PROFILE_WEIGHTS[profile]
    factors = [
        ("Värdering", "valuation"), ("Kvalitet", "quality"), ("Marknadsläge", "setup"),
        ("Utdelning", "income"), ("Risk", "risk"),
    ]
    table = []
    for label, key in factors:
        score = _num(row.get(label)); weight = weights[key]
        weighted = score * weight if np.isfinite(score) else np.nan
        impact = (score - 50) * weight if np.isfinite(score) else np.nan
        if not np.isfinite(score): assessment = "Data saknas"
        elif score >= 75: assessment = "Stark"
        elif score >= 60: assessment = "Positiv"
        elif score >= 40: assessment = "Neutral"
        elif score >= 25: assessment = "Svag"
        else: assessment = "Mycket svag"
        table.append({"Del": label, "Score": score, "Vikt %": weight * 100, "Viktade poäng": weighted, "Påverkan mot neutral": impact, "Bedömning": assessment})

    strengths: list[str] = []
    weaknesses: list[str] = []
    pe, fpe, fcfy = _num(row.get("P/E")), _num(row.get("Forward P/E")), _num(row.get("FCF-yield"))
    roe, margin, growth, debt = _num(row.get("ROE")), _num(row.get("Vinstmarginal")), _num(row.get("Omsättningstillväxt")), _num(row.get("Skuld/eget kapital"))
    rsi, m3, dist = _num(row.get("RSI14")), _num(row.get("3 mån")), _num(row.get("Avstånd SMA200"))
    dy, payout, coverage = _num(row.get("Direktavkastning")), _num(row.get("Utdelningsandel")), _num(row.get("Datatäckning"))
    if np.isfinite(pe) and 0 < pe <= 15: strengths.append(f"P/E {pe:.1f} är relativt låg i absoluta tal.")
    if np.isfinite(fpe) and 0 < fpe < pe: strengths.append(f"Forward P/E {fpe:.1f} är lägre än historisk P/E {pe:.1f}.")
    if np.isfinite(fcfy) and fcfy >= .05: strengths.append(f"FCF-yield {fcfy:.1%} ger stöd åt värderingen.")
    if np.isfinite(roe) and roe >= .15: strengths.append(f"ROE {roe:.1%} visar god kapitalavkastning.")
    if np.isfinite(margin) and margin >= .10: strengths.append(f"Vinstmarginal {margin:.1%} är stark.")
    if np.isfinite(growth) and growth >= .08: strengths.append(f"Omsättningen växer {growth:.1%} enligt tillgänglig data.")
    if np.isfinite(rsi) and 32 <= rsi <= 48: strengths.append(f"RSI {rsi:.0f} ligger i ett rekylområde modellen gillar.")
    if np.isfinite(dy) and .025 <= dy <= .08: strengths.append(f"Direktavkastning {dy:.1%} bidrar positivt.")

    if np.isfinite(pe) and pe >= 30: weaknesses.append(f"P/E {pe:.1f} innebär en hög vinstmultipel.")
    if np.isfinite(roe) and roe < 0: weaknesses.append(f"ROE {roe:.1%} är negativ.")
    if np.isfinite(margin) and margin < 0: weaknesses.append(f"Vinstmarginal {margin:.1%} är negativ.")
    if np.isfinite(debt) and debt > 200: weaknesses.append(f"Skuld/eget kapital {debt:.0f} är hög och ger riskavdrag.")
    if np.isfinite(m3) and m3 <= -.15: weaknesses.append(f"Tremånadersmomentum {m3:.1%} är tydligt negativt.")
    if np.isfinite(dist) and dist <= -.10: weaknesses.append(f"Kursen ligger {abs(dist):.1%} under SMA200.")
    if np.isfinite(payout) and payout > 1: weaknesses.append(f"Utdelningsandelen {payout:.0%} är över 100 %.")
    if np.isfinite(coverage) and coverage < .60: weaknesses.append(f"Datatäckningen är bara {coverage:.0%}; totalpoängen rabatteras.")

    # Always surface the strongest model component even when raw metrics are less obvious.
    sorted_factors = sorted(table, key=lambda x: (_num(x["Påverkan mot neutral"])), reverse=True)
    if sorted_factors and _num(sorted_factors[0]["Påverkan mot neutral"]) > 3:
        strengths.insert(0, f"{sorted_factors[0]['Del']} är modellens starkaste del ({sorted_factors[0]['Score']:.0f}/100).")
    if sorted_factors and _num(sorted_factors[-1]["Påverkan mot neutral"]) < -3:
        weaknesses.insert(0, f"{sorted_factors[-1]['Del']} är modellens svagaste del ({sorted_factors[-1]['Score']:.0f}/100).")
    return pd.DataFrame(table), strengths[:5], weaknesses[:5]

def score_change(symbol: str, profile: str, current_score: float) -> float | None:
    """Compare with the latest earlier daily snapshot."""
    client = _supabase_client(); uid = current_user_id()
    today = datetime.now().date().isoformat()
    try:
        if client is not None and uid:
            data = client.table("score_history").select("score,captured_date").eq("user_id", uid).eq("symbol", symbol).eq("profile", profile).lt("captured_date", today).order("captured_date", desc=True).limit(1).execute().data or []
            if data:
                return float(current_score) - float(data[0]["score"])
            return None
        init_db()
        with _db_connect() as conn:
            row = conn.execute("SELECT score FROM score_history WHERE symbol=? AND profile=? AND substr(captured_at,1,10)<? ORDER BY captured_at DESC LIMIT 1", (symbol, profile, today)).fetchone()
            return float(current_score) - float(row[0]) if row else None
    except Exception:
        return None


def previous_score(symbol: str, profile: str) -> float | None:
    """Latest score from an earlier day, used for threshold-crossing signals."""
    client = _supabase_client(); uid = current_user_id()
    today = datetime.now().date().isoformat()
    try:
        if client is not None and uid:
            data = client.table("score_history").select("score,captured_date").eq("user_id", uid).eq("symbol", symbol).eq("profile", profile).lt("captured_date", today).order("captured_date", desc=True).limit(1).execute().data or []
            return float(data[0]["score"]) if data else None
        init_db()
        with _db_connect() as conn:
            row = conn.execute("SELECT score FROM score_history WHERE symbol=? AND profile=? AND substr(captured_at,1,10)<? ORDER BY captured_at DESC LIMIT 1", (symbol, profile, today)).fetchone()
            return float(row[0]) if row else None
    except Exception:
        return None


def previous_top_symbols(profile: str, limit: int = 10) -> set[str]:
    """Top symbols from the latest earlier scan date for the signed-in user/local app."""
    client = _supabase_client(); uid = current_user_id()
    today = datetime.now().date().isoformat()
    try:
        if client is not None and uid:
            dates = client.table("radar_history").select("captured_date").eq("user_id", uid).eq("profile", profile).lt("captured_date", today).order("captured_date", desc=True).limit(1).execute().data or []
            if not dates:
                return set()
            d = dates[0]["captured_date"]
            data = client.table("radar_history").select("symbol,rank").eq("user_id", uid).eq("profile", profile).eq("captured_date", d).lte("rank", limit).execute().data or []
            return {str(x["symbol"]) for x in data}
        init_db()
        with _db_connect() as conn:
            row = conn.execute("SELECT captured_date FROM radar_history WHERE profile=? AND captured_date<? ORDER BY captured_date DESC LIMIT 1", (profile, today)).fetchone()
            if not row:
                return set()
            rows = conn.execute("SELECT symbol FROM radar_history WHERE profile=? AND captured_date=? AND rank<=?", (profile, row[0], limit)).fetchall()
            return {str(x[0]) for x in rows}
    except Exception:
        return set()


def save_radar_history(top_df: pd.DataFrame, profile: str) -> None:
    """Store today's ranking to identify shares newly entering the radar on a later day."""
    if top_df.empty:
        return
    today = datetime.now().date().isoformat()
    client = _supabase_client(); uid = current_user_id()
    rows = top_df.head(20)[["Ticker", "Borsiq Score"]].reset_index(drop=True)
    if client is not None and uid:
        for i, row in rows.iterrows():
            payload = {"user_id": uid, "symbol": str(row["Ticker"]), "profile": profile, "rank": int(i + 1), "score": float(row["Borsiq Score"]), "captured_date": today}
            try:
                client.table("radar_history").upsert(payload, on_conflict="user_id,symbol,profile,captured_date").execute()
            except Exception:
                pass
        return
    init_db()
    with _db_connect() as conn:
        for i, row in rows.iterrows():
            conn.execute(
                "INSERT INTO radar_history(symbol,profile,rank,score,captured_date) VALUES (?,?,?,?,?) ON CONFLICT(symbol,profile,captured_date) DO UPDATE SET rank=excluded.rank,score=excluded.score,captured_at=CURRENT_TIMESTAMP",
                (str(row["Ticker"]), profile, int(i + 1), float(row["Borsiq Score"]), today),
            )


def _signal_event_key(sig: dict[str, Any], profile: str, occurred_date: str | None = None) -> str:
    d = occurred_date or datetime.now().date().isoformat()
    return f"{d}|{profile}|{sig['symbol']}|{sig['kind']}"


def persist_signals(signals: list[dict[str, Any]], profile: str) -> None:
    """Store signal events once per day/profile/symbol/kind while preserving read state."""
    if not signals:
        return
    occurred = datetime.now().date().isoformat()
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        for sig in signals:
            payload = {
                "user_id": uid,
                "event_key": _signal_event_key(sig, profile, occurred),
                "symbol": sig["symbol"], "kind": sig["kind"], "text": sig["text"],
                "priority": int(sig["priority"]), "profile": profile, "occurred_date": occurred,
            }
            try:
                client.table("signal_history").upsert(payload, on_conflict="user_id,event_key").execute()
            except Exception:
                pass
        return
    init_db()
    with _db_connect() as conn:
        for sig in signals:
            conn.execute(
                "INSERT INTO signal_history(event_key,symbol,kind,text,priority,profile,occurred_date) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(event_key) DO UPDATE SET text=excluded.text,priority=excluded.priority",
                (_signal_event_key(sig, profile, occurred), sig["symbol"], sig["kind"], sig["text"], int(sig["priority"]), profile, occurred),
            )


def get_signal_history(limit: int = 150) -> pd.DataFrame:
    cols = ["event_key", "symbol", "kind", "text", "priority", "profile", "occurred_date", "is_read", "email_sent_at", "created_at"]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = client.table("signal_history").select(",".join(cols)).eq("user_id", uid).order("created_at", desc=True).limit(limit).execute().data or []
            return pd.DataFrame(data, columns=cols)
        except Exception:
            return pd.DataFrame(columns=cols)
    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query(
            "SELECT event_key,symbol,kind,text,priority,profile,occurred_date,is_read,email_sent_at,created_at FROM signal_history ORDER BY created_at DESC LIMIT ?",
            conn, params=(limit,),
        )


def mark_signal_read(event_key: str, is_read: bool = True) -> None:
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        client.table("signal_history").update({"is_read": bool(is_read)}).eq("user_id", uid).eq("event_key", event_key).execute()
        return
    init_db()
    with _db_connect() as conn:
        conn.execute("UPDATE signal_history SET is_read=? WHERE event_key=?", (1 if is_read else 0, event_key))


def mark_all_signals_read() -> None:
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        client.table("signal_history").update({"is_read": True}).eq("user_id", uid).eq("is_read", False).execute()
        return
    init_db()
    with _db_connect() as conn:
        conn.execute("UPDATE signal_history SET is_read=1 WHERE is_read=0")


def build_watch_signals(watch_df: pd.DataFrame, top_df: pd.DataFrame, watch_meta: pd.DataFrame, profile: str) -> list[dict[str, Any]]:
    """Create transparent alerts using per-share thresholds from the watchlist."""
    if watch_df.empty:
        return []
    meta_by_symbol = {str(r["symbol"]): r for _, r in watch_meta.iterrows()} if not watch_meta.empty else {}
    current_top = {str(x) for x in top_df.head(10)["Ticker"].tolist()}
    prior_top = previous_top_symbols(profile, 10)
    signals: list[dict[str, Any]] = []
    for _, row in watch_df.iterrows():
        sym = str(row["Ticker"]); name = str(row.get("Namn") or sym)
        score = _num(row.get("Borsiq Score")); price = _num(row.get("Pris")); daily = _num(row.get("Dagsförändring"))
        prev = previous_score(sym, profile)
        delta = score - prev if np.isfinite(score) and prev is not None and np.isfinite(prev) else None
        meta = meta_by_symbol.get(sym)
        target = _num(meta.get("target_price")) if meta is not None else np.nan
        threshold = _num(meta.get("signal_score_threshold")) if meta is not None else 75.0
        move = _num(meta.get("signal_score_move")) if meta is not None else 8.0
        daily_drop = _num(meta.get("signal_daily_drop")) if meta is not None else 5.0
        threshold = threshold if np.isfinite(threshold) else 75.0
        move = move if np.isfinite(move) else 8.0
        daily_drop = daily_drop if np.isfinite(daily_drop) else 5.0

        if sym in current_top and prior_top and sym not in prior_top:
            rank = next((i + 1 for i, x in enumerate(top_df.head(10)["Ticker"].astype(str).tolist()) if x == sym), None)
            signals.append({"priority": 3, "symbol": sym, "name": name, "kind": "Ny i topp 10", "text": f"{name} har gått in på plats {rank} i Borsiq Radar ({score:.0f}/100)."})
        if delta is not None and delta >= move:
            signals.append({"priority": 3, "symbol": sym, "name": name, "kind": "Score lyfter", "text": f"Borsiq Score har stigit {delta:+.1f} sedan föregående registrerade dag till {score:.0f}/100. Din gräns är {move:.1f}."})
        if prev is not None and prev < threshold <= score:
            signals.append({"priority": 2, "symbol": sym, "name": name, "kind": "Scoregräns passerad", "text": f"Borsiq Score har passerat din gräns {threshold:.0f}: {prev:.1f} → {score:.1f}."})
        if np.isfinite(target) and np.isfinite(price) and price >= target:
            signals.append({"priority": 3, "symbol": sym, "name": name, "kind": "Målkurs nådd", "text": f"Kursen {price:.2f} har nått/passerat din målkurs {target:.2f}."})
        if np.isfinite(daily) and daily <= -(daily_drop / 100.0):
            signals.append({"priority": 2, "symbol": sym, "name": name, "kind": "Kraftigt dagsfall", "text": f"Aktien är ned {daily:.1%} idag, vilket passerar din gräns på {daily_drop:.1f} %. Kontrollera nyheter/bolagshändelser."})
        if delta is not None and delta <= -move:
            signals.append({"priority": 2, "symbol": sym, "name": name, "kind": "Score faller", "text": f"Borsiq Score har sjunkit {delta:.1f} sedan föregående registrerade dag till {score:.0f}/100. Din gräns är {move:.1f}."})
    return sorted(signals, key=lambda x: (-int(x["priority"]), x["symbol"], x["kind"]))


def render_signal_cards(signals: list[dict[str, Any]]) -> None:
    if not signals:
        st.info("Inga nya bevakningssignaler just nu.")
        return
    for sig in signals:
        icon = "🔔" if sig["priority"] >= 3 else "⚠️"
        st.markdown(f"**{icon} {sig['kind']} · {sig['symbol']}**  ")
        st.write(sig["text"])


def load_universe_file() -> pd.DataFrame:
    if not UNIVERSE_PATH.exists():
        return pd.DataFrame({"Ticker": SWEDEN_BROAD_TICKERS, "Segment": "Kuraterad"})
    try:
        uni = pd.read_csv(UNIVERSE_PATH)
        if "Ticker" not in uni.columns:
            raise ValueError("Ticker-kolumn saknas")
        uni["Ticker"] = uni["Ticker"].astype(str).str.strip().str.upper()
        uni = uni[uni["Ticker"].ne("")].drop_duplicates("Ticker")
        if "Segment" not in uni.columns:
            uni["Segment"] = "Sverige"
        return uni
    except Exception:
        return pd.DataFrame({"Ticker": SWEDEN_BROAD_TICKERS, "Segment": "Kuraterad"})


def fmt_pct(v: Any, digits: int = 1) -> str:
    x = _num(v); return "—" if not np.isfinite(x) else f"{x * 100:.{digits}f}%"


def fmt_num(v: Any, digits: int = 1) -> str:
    x = _num(v); return "—" if not np.isfinite(x) else f"{x:.{digits}f}"


def parse_symbols(text: str) -> list[str]:
    symbols = []
    for item in text.replace(";", ",").replace("\n", ",").split(","):
        s = item.strip().upper()
        if not s: continue
        if "." not in s and "-" not in s: s += ".ST"
        symbols.append(s)
    return list(dict.fromkeys(symbols))


def dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["Ticker", "Namn", "Sektor", "Borsiq Score", "Signal", "Pris", "Prisdatum", "Dagsförändring", "P/E", "Direktavkastning", "52v från topp", "RSI14", "Värdering", "Kvalitet", "Marknadsläge", "Risk", "Riskflaggor", "Varför"]
    display = df[[c for c in cols if c in df.columns]].copy()
    for col in ["Dagsförändring", "Direktavkastning", "52v från topp"]:
        if col in display: display[col] = pd.to_numeric(display[col], errors="coerce") * 100
    return display


def render_detail(row: pd.Series, profile: str) -> None:
    st.subheader(f"{row['Namn']} · {row['Ticker']}")
    c1, c2, c3, c4, c5 = st.columns(5)
    prev = previous_score_snapshot(str(row["Ticker"]), profile)
    score_delta = None
    if prev and np.isfinite(_num(prev.get("score"))): score_delta = _num(row.get("Borsiq Score")) - _num(prev.get("score"))
    c1.metric("Borsiq Score", f"{row['Borsiq Score']:.0f}/100", f"{score_delta:+.1f}" if score_delta is not None else None)
    c2.metric("Pris", f"{row['Pris']:.2f} {row.get('Valuta', '')}", fmt_pct(row.get("Dagsförändring")))
    c3.metric("Värdering", f"{row['Värdering']:.0f}")
    c4.metric("Kvalitet", f"{row['Kvalitet']:.0f}")
    c5.metric("Risk", f"{row['Risk']:.0f}")
    st.markdown(f"**Bedömning:** {row['Signal']}  \n**Kort förklaring:** {row['Varför']}  \n**Riskflaggor:** {row['Riskflaggor']}")

    factor_df, strengths, weaknesses = _score_explanation(row, profile)
    st.markdown("#### Varför får aktien den här poängen?")
    st.caption(f"Strategin {profile} väger delpoängen olika. 'Påverkan mot neutral' visar hur mycket varje del ungefär lyfter eller sänker modellen jämfört med en neutral delpoäng på 50.")
    st.dataframe(
        factor_df, use_container_width=True, hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
            "Vikt %": st.column_config.NumberColumn("Vikt", format="%.0f%%"),
            "Viktade poäng": st.column_config.NumberColumn("Viktade poäng", format="%.1f"),
            "Påverkan mot neutral": st.column_config.NumberColumn("Påverkan vs neutral", format="%+.1f"),
        },
    )
    base_score = float(pd.to_numeric(factor_df["Viktade poäng"], errors="coerce").sum())
    coverage_for_calc = _num(row.get("Datatäckning"))
    coverage_factor = .80 + .20 * coverage_for_calc if np.isfinite(coverage_for_calc) else .80
    calc_final = base_score * coverage_factor
    q1, q2, q3 = st.columns(3)
    q1.metric("Viktad grundscore", f"{base_score:.1f}")
    q2.metric("Datatäckningsfaktor", f"{coverage_factor:.3f}")
    q3.metric("Beräknad slutscore", f"{calc_final:.1f}")
    st.caption("Formel: viktad grundscore × (0,80 + 0,20 × datatäckning). Små avrundningsskillnader kan förekomma eftersom delpoängen visas avrundade.")
    sx, wx = st.columns(2)
    with sx:
        st.markdown("**Styrkor modellen ser**")
        if strengths:
            for item in strengths: st.markdown(f"- {item}")
        else: st.caption("Inga tydliga styrkor sticker ut i tillgänglig data.")
    with wx:
        st.markdown("**Svagheter / det som drar ned**")
        if weaknesses:
            for item in weaknesses: st.markdown(f"- {item}")
        else: st.caption("Inga tydliga svagheter sticker ut i tillgänglig data.")

    if prev:
        component_map = [("Värdering","valuation"),("Kvalitet","quality"),("Marknadsläge","setup"),("Utdelning","income"),("Risk","risk")]
        changes=[]
        for label,key in component_map:
            old=_num(prev.get(key)); cur=_num(row.get(label))
            if np.isfinite(old) and np.isfinite(cur): changes.append((label,cur-old,old,cur))
        if changes:
            changes.sort(key=lambda x: abs(x[1]), reverse=True)
            st.markdown("#### Vad har ändrats sedan föregående registrerade dag?")
            st.caption(f"Jämförelse mot {prev.get('captured_date','föregående snapshot')}. Historiken sparas för bevakade aktier.")
            cols=st.columns(min(3,len(changes)))
            for i,(label,delta,old,cur) in enumerate(changes[:3]):
                cols[i].metric(label, f"{cur:.0f}", f"{delta:+.1f}")
    elif is_watched(str(row["Ticker"])):
        st.info("Förändringsförklaringen visas när det finns minst en tidigare dagsnapshot för den här bevakade aktien.")

    coverage=_num(row.get("Datatäckning"))
    if np.isfinite(coverage):
        if coverage < .60: st.warning(f"Datatäckning {coverage:.0%}. Flera fundamentala fält saknas; score bör tolkas försiktigt.")
        else: st.caption(f"Datatäckning i kärnmodellen: {coverage:.0%}.")
    price_date = str(row.get("Prisdatum") or "—")
    fundamental_at = str(row.get("Fundamental hämtad") or "—")
    st.caption(f"Datastämpel · senaste kursdag: {price_date} · fundamentaldata hämtad: {fundamental_at}. Detta är hämtningstid, inte nödvändigtvis rapportperiod för varje fundamental datapunkt.")

    watched = is_watched(str(row["Ticker"]))
    if st.button("Ta bort från bevakning" if watched else "Lägg till i bevakning", key=f"watch_{row['Ticker']}"):
        toggle_watchlist(str(row["Ticker"])); st.rerun()
    hist = row.get("_history")
    if isinstance(hist, pd.DataFrame) and not hist.empty:
        chart = hist[["Close"]].copy(); chart["SMA50"] = chart["Close"].rolling(50).mean(); chart["SMA200"] = chart["Close"].rolling(200).mean()
        st.line_chart(chart, height=320)
    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown("#### Värdering"); st.write({"P/E": fmt_num(row.get("P/E")), "Forward P/E": fmt_num(row.get("Forward P/E")), "P/B": fmt_num(row.get("P/B")), "EV/EBITDA": fmt_num(row.get("EV/EBITDA")), "FCF-yield": fmt_pct(row.get("FCF-yield"))})
    with m2:
        st.markdown("#### Kvalitet"); st.write({"ROE": fmt_pct(row.get("ROE")), "Vinstmarginal": fmt_pct(row.get("Vinstmarginal")), "Omsättningstillväxt": fmt_pct(row.get("Omsättningstillväxt")), "Vinsttillväxt": fmt_pct(row.get("Vinsttillväxt")), "Skuld/eget kapital": fmt_num(row.get("Skuld/eget kapital"), 0)})
    with m3:
        st.markdown("#### Utdelning / setup"); st.write({"Direktavkastning": fmt_pct(row.get("Direktavkastning")), "Utdelningsandel": fmt_pct(row.get("Utdelningsandel")), "RSI14": fmt_num(row.get("RSI14"),0), "3 mån": fmt_pct(row.get("3 mån")), "52v från topp": fmt_pct(row.get("52v från topp"))})
    with st.expander("Rapportdatum och senaste nyheter", expanded=False):
        events = fetch_company_events(str(row["Ticker"]))
        e1, e2 = st.columns(2)
        e1.metric("Nästa rapport enligt Yahoo", _fmt_date(events.get("earnings")))
        e2.metric("Ex-dag enligt Yahoo", _fmt_date(events.get("ex_dividend")))
        news = events.get("news") or []
        if news:
            st.markdown("**Senaste rubriker**")
            for item in news:
                title = item.get("title", "Nyhet"); provider = item.get("provider", ""); link = item.get("link"); suffix = f" · {provider}" if provider else ""
                st.markdown(f"- [{title}]({link}){suffix}" if link else f"- {title}{suffix}")
        else: st.caption("Ingen nyhetsdata kunde hämtas just nu.")
        st.caption("Kalender- och nyhetsdata kommer från Yahoo Finance och bör verifieras mot bolagets IR-sida.")
    st.link_button("Öppna hos Yahoo Finance", str(row["Yahoo"]))


def render_overview(
    daily_shortlist: pd.DataFrame,
    filtered: pd.DataFrame,
    scored: pd.DataFrame,
    watch_df: pd.DataFrame,
    signal_history: pd.DataFrame,
    unread_signals: int,
    profile: str,
    idx: dict[str, Any] | None,
    elapsed: float,
    latest_price_date: str,
) -> None:
    """A compact start screen that answers: what matters, why, and what next?"""
    st.subheader("Överblick")
    st.caption("Borsiq ska först hjälpa dig prioritera vad som är värt att analysera vidare — inte överösa dig med tabeller.")

    best = daily_shortlist.iloc[0] if not daily_shortlist.empty else None
    high_priority = int((daily_shortlist["Prioritet"] == "Hög").sum()) if not daily_shortlist.empty else 0
    today = datetime.now().date().isoformat()
    today_signals = signal_history[signal_history["occurred_date"].astype(str) == today] if not signal_history.empty else pd.DataFrame()

    m1, m2, m3, m4 = st.columns(4)
    if best is not None:
        m1.metric("Bästa kandidat idag", str(best["Ticker"]), f"Relevans {_num(best['Dagens relevans']):.0f}/100")
    else:
        m1.metric("Bästa kandidat idag", "—")
    m2.metric("Hög prioritet", high_priority)
    m3.metric("Olästa Radar-signaler", unread_signals)
    m4.metric("Bevakade aktier", len(watch_df))

    left, right = st.columns([1.55, 1])
    with left:
        st.markdown("### Det viktigaste just nu")
        if best is None:
            st.info("Ingen kandidat klarade dagens urval. Justera filtren eller kontrollera datakällan.")
        else:
            with st.container(border=True):
                c1, c2, c3 = st.columns([2.5, 1, 1])
                c1.markdown(f"## {best['Namn']}")
                c1.caption(f"{best['Ticker']} · {best['Sektor']} · {best['Signal']}")
                c2.metric("Borsiq", f"{_num(best['Borsiq Score']):.0f}/100", f"{_num(best.get('Score Δ')):+.1f}" if np.isfinite(_num(best.get('Score Δ'))) else None)
                c3.metric("Idag", f"{_num(best['Dagens relevans']):.0f}/100")
                st.markdown(f"**Varför idag:** {best['Varför idag']}")
                st.markdown(f"**Förändrat:** {best['Förändrat']}")
                st.markdown(f"**Kontrollera:** {best['Kontrollera']}")
                st.caption("Detta är screening för vidare analys, inte ett köpbeslut.")

        if len(daily_shortlist) > 1:
            st.markdown("### Nästa kandidater")
            compact = daily_shortlist.iloc[1:5][["Ticker", "Namn", "Borsiq Score", "Dagens relevans", "Prioritet", "Score Δ"]].copy()
            st.dataframe(
                compact, use_container_width=True, hide_index=True,
                column_config={
                    "Borsiq Score": st.column_config.ProgressColumn("Borsiq", 0, 100, format="%.0f"),
                    "Dagens relevans": st.column_config.ProgressColumn("Idag", 0, 100, format="%.0f"),
                    "Score Δ": st.column_config.NumberColumn("Δ", format="%+.1f"),
                },
            )

    with right:
        st.markdown("### Radar")
        if today_signals.empty:
            st.caption("Inga nya signaler idag.")
        else:
            for _, sig in today_signals.sort_values(["priority", "created_at"], ascending=[False, False]).head(4).iterrows():
                prefix = "🔔" if int(sig.get("priority", 1)) >= 3 else "•"
                st.markdown(f"{prefix} **{sig['symbol']} · {sig['kind']}**  ")
                st.caption(str(sig["text"]))
        if unread_signals:
            st.info(f"{unread_signals} olästa signaler finns i Radar-fliken.")

        st.markdown("### Körstatus")
        status_rows = [
            ("Strategi", profile),
            ("Analyserade", str(len(scored))),
            ("Efter filter", str(len(filtered))),
            ("Senaste kursdag", latest_price_date),
            ("Körtid", f"{elapsed:.1f} s"),
        ]
        if idx:
            status_rows.insert(2, ("OMXS30", f"{idx['index']:.2f} ({fmt_pct(idx.get('daily'))})"))
        for label, value in status_rows:
            st.markdown(f"<div class='bq-status'><span>{label}</span><strong>{value}</strong></div>", unsafe_allow_html=True)

    st.divider()
    st.markdown("### Gå vidare till en aktie")
    candidates = filtered.head(min(25, len(filtered)))
    choices = {f"{r['Ticker']} · {r['Namn']} · {r['Borsiq Score']:.0f}/100": i for i, r in candidates.iterrows()}
    if choices:
        selected = st.selectbox("Välj kandidat för full analys", list(choices), key="overview_detail_choice")
        with st.expander("Öppna full analys", expanded=False):
            render_detail(candidates.loc[choices[selected]], profile)

def main() -> None:
    st.set_page_config(page_title=f"{APP_NAME} · Dagens fynd", page_icon="◈", layout="wide")
    st.markdown("""
    <style>
    .block-container{padding-top:1.35rem;padding-bottom:3rem;max-width:1480px}
    [data-testid="stMetric"]{background:#f8fafc;border:1px solid #e2e8f0;padding:12px 14px;border-radius:14px}
    .bq-hero{padding:22px 24px;border-radius:18px;background:linear-gradient(135deg,#0f172a,#1e293b);color:white;margin-bottom:14px}
    .bq-mark{display:inline-flex;width:42px;height:42px;border-radius:12px;align-items:center;justify-content:center;background:#22c55e;color:#07130b;font-weight:900;margin-right:10px}
    .bq-title{font-size:2rem;font-weight:800;letter-spacing:-.03em}.bq-sub{color:#cbd5e1;margin-top:5px}.bq-domain{color:#86efac;font-weight:700}
    .small-muted{color:#64748b;font-size:.9rem}
    .bq-status{display:flex;justify-content:space-between;gap:18px;padding:9px 0;border-bottom:1px solid #e2e8f0;color:#475569}.bq-status strong{color:#0f172a}
    div[data-testid="stTabs"] button{font-weight:650}
    @media (max-width: 700px){
      .block-container{padding-top:.65rem;padding-left:.75rem;padding-right:.75rem}
      .bq-hero{padding:16px;border-radius:14px}.bq-title{font-size:1.55rem}.bq-sub{font-size:.82rem}
      [data-testid="stMetric"]{padding:9px 10px;border-radius:11px}
      div[data-testid="stHorizontalBlock"]{gap:.55rem}
      .stDataFrame{font-size:.82rem}
    }
    </style>
    """, unsafe_allow_html=True)
    st.markdown(f"""<div class='bq-hero'><div><span class='bq-mark'>BQ</span><span class='bq-title'>{APP_NAME}</span></div><div class='bq-sub'>Hitta vad som är värt att analysera idag — och förstå varför · <span class='bq-domain'>{APP_DOMAIN}</span> · v{APP_VERSION}</div></div>""", unsafe_allow_html=True)
    st.info("Borsiq Score är en kvantitativ screeningmodell — inte ett köp- eller säljråd. Kursdata hämtas i bulk och cachas 15 min; fundamentaldata cachas 6 timmar. Yahoo-data kan vara fördröjd eller ofullständig.")
    st.caption("Arbetsflöde: 1) Överblick → 2) Dagens fynd → 3) full aktieanalys → 4) bevaka och få Radar-signaler.")

    init_db()
    universe_df = load_universe_file()
    file_universe_symbols = universe_df["Ticker"].tolist()

    with st.sidebar:
        st.header("Konto")
        if cloud_enabled():
            user = current_user()
            if user is None:
                with st.expander("Logga in / skapa konto", expanded=False):
                    auth_mode = st.radio("Kontoåtgärd", ["Logga in", "Skapa konto"], horizontal=True, label_visibility="collapsed")
                    with st.form("auth_form"):
                        email = st.text_input("E-post")
                        password = st.text_input("Lösenord", type="password")
                        submitted = st.form_submit_button(auth_mode, use_container_width=True)
                    if submitted:
                        ok, msg = auth_sign_in(email, password) if auth_mode == "Logga in" else auth_sign_up(email, password)
                        (st.success if ok else st.error)(msg)
                        if ok and current_user() is not None:
                            st.rerun()
                st.caption("Utan inloggning används lokal SQLite på denna dator.")
            else:
                st.success(f"Inloggad som {getattr(user, 'email', '')}")
                if st.button("Logga ut", use_container_width=True):
                    auth_sign_out(); st.rerun()
                st.caption("Bevakning och scorehistorik sparas i Supabase.")
        else:
            st.caption("Lokalt läge · konfigurera Supabase för konto och molnsynk.")
        st.divider()
        st.header("Borsiq Radar")
        universe = st.radio("Universum", ["OMXS30", "Sverige bred", "Egen lista"], index=1)
        custom = st.text_area("Tickers", value="INVE-B.ST, VOLV-B.ST, SAND.ST, EVO.ST", height=110) if universe == "Egen lista" else ""
        if universe == "Sverige bred": st.caption(f"Universumsfil: {len(file_universe_symbols)} svenska tickers. Listan ligger i universe.csv och kan underhållas utan kodändring.")
        profile = st.selectbox("Strategi", list(PROFILE_WEIGHTS), index=0)
        min_market_cap = st.number_input("Min börsvärde (mdr SEK)", 0.0, value=5.0, step=1.0)
        min_turnover = st.number_input("Min omsättning/dag (MSEK)", 0.0, value=5.0, step=1.0)
        require_positive = st.checkbox("Kräv positiv P/E", value=True)
        allow_missing_filter_data = st.checkbox("Tillåt saknade filtervärden", value=False, help="Om avstängd måste börsvärde och omsättning finnas när respektive minimifilter är större än 0.")
        top_n = st.slider("Visa topp", 3, 20, 10)
        refresh = st.button("Uppdatera marknadsdata", type="primary", use_container_width=True)
        st.caption("Kurser: cache 15 min · fundamenta: cache 6 h. Knappen rensar båda cacharna.")

    symbols = OMXS30_TICKERS if universe == "OMXS30" else (file_universe_symbols if universe == "Sverige bred" else parse_symbols(custom))
    if refresh: st.cache_data.clear()
    if not symbols: st.warning("Ange minst en ticker."); st.stop()
    start = time.perf_counter()
    with st.spinner(f"Borsiq analyserar {len(symbols)} aktier…"):
        raw_df, errors = scan_universe(symbols)
    if raw_df.empty:
        st.error("Ingen marknadsdata kunde hämtas. Yahoo Finance kan tillfälligt begränsa anrop.")
        if errors: st.code("\n".join(errors[:12]))
        st.stop()

    scored = add_scores(raw_df, profile)
    save_score_history(scored, profile)
    filtered = scored.copy()
    if min_market_cap > 0:
        cap_ok = filtered["Börsvärde BSEK"] >= min_market_cap
        if allow_missing_filter_data: cap_ok = cap_ok | filtered["Börsvärde BSEK"].isna()
        filtered = filtered[cap_ok]
    if min_turnover > 0:
        turnover_ok = filtered["Omsättning MSEK/dag"] >= min_turnover
        if allow_missing_filter_data: turnover_ok = turnover_ok | filtered["Omsättning MSEK/dag"].isna()
        filtered = filtered[turnover_ok]
    if require_positive: filtered = filtered[filtered["P/E"].notna() & (filtered["P/E"] > 0)]
    top = filtered.head(top_n).copy(); daily_shortlist = build_daily_shortlist(filtered, profile, limit=min(5, len(filtered))); idx = fetch_index_snapshot(); elapsed = time.perf_counter() - start

    price_dates = sorted({str(x) for x in raw_df.get("Prisdatum", pd.Series(dtype=str)).dropna().tolist() if str(x) != "—"})
    latest_price_date = price_dates[-1] if price_dates else "—"
    k1,k2,k3,k4,k5 = st.columns(5)
    k1.metric("Analyserade", len(raw_df)); k2.metric("Efter filter", len(filtered)); k3.metric("OMXS30", f"{idx['index']:.2f}" if idx else "—", fmt_pct(idx.get("daily")) if idx else None); k4.metric("Datakörning", f"{elapsed:.1f} s"); k5.metric("Senaste kursdag", latest_price_date)
    if errors:
        with st.expander(f"{len(errors)} ticker(s) kunde inte läsas"): st.code("\n".join(errors))
    if filtered.empty: st.warning("Inga aktier klarade filtren."); st.stop()

    # Förbered bevakningsdata och signaler en gång per körning.
    watch_meta_global = get_watchlist()
    watched_global = watch_meta_global["symbol"].astype(str).tolist() if not watch_meta_global.empty else []
    watch_df_global = scored[scored["Ticker"].isin(watched_global)].copy() if watched_global else pd.DataFrame()
    missing_global = [sym for sym in watched_global if sym not in set(scored["Ticker"])]
    if missing_global:
        with st.spinner(f"Hämtar {len(missing_global)} bevakade aktier utanför aktuellt universum…"):
            extra_raw_global, _ = scan_universe(missing_global)
        if not extra_raw_global.empty:
            extra_scored_global = add_scores(extra_raw_global, profile)
            watch_df_global = pd.concat([watch_df_global, extra_scored_global], ignore_index=True)
    watch_signals = build_watch_signals(watch_df_global, top, watch_meta_global, profile) if watched_global else []
    persist_signals(watch_signals, profile)
    signal_history_global = get_signal_history()
    unread_signals = int((~signal_history_global["is_read"].astype(bool)).sum()) if not signal_history_global.empty else 0
    save_radar_history(filtered.head(max(20, top_n)), profile)

    tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs(["Överblick", "Dagens fynd", f"Radar ({unread_signals})", "Bevakning", "Marknad", "Metod"])
    with tab0:
        render_overview(daily_shortlist, filtered, scored, watch_df_global, signal_history_global, unread_signals, profile, idx, elapsed, latest_price_date)
    with tab1:
        st.subheader("Dagens fynd · snabbaste beslutsunderlaget")
        st.caption("Dagens relevans är en separat triage ovanpå Borsiq Score. Den väger in aktuellt marknadsläge och scoreförändring, och kan begränsas av grova riskflaggor. Den är inte ett köp- eller säljråd.")
        if daily_shortlist.empty:
            st.info("Ingen kandidat kunde byggas från dagens filtrerade universum.")
        else:
            high_count = int((daily_shortlist["Prioritet"] == "Hög").sum())
            d1, d2, d3 = st.columns(3)
            d1.metric("Kortlista", len(daily_shortlist))
            d2.metric("Hög prioritet", high_count)
            d3.metric("Bästa relevans", f"{daily_shortlist.iloc[0]['Dagens relevans']:.0f}/100")

            for rank, (_, case) in enumerate(daily_shortlist.iterrows(), start=1):
                with st.container(border=True):
                    h1, h2, h3, h4 = st.columns([3.2, 1, 1, 1])
                    h1.markdown(f"### {rank}. {case['Namn']} · {case['Ticker']}")
                    h1.caption(f"{case['Signal']} · {case['Sektor']} · senaste kursdag {case.get('Prisdatum','—')}")
                    delta = _num(case.get("Score Δ"))
                    h2.metric("Borsiq", f"{_num(case['Borsiq Score']):.0f}/100", f"{delta:+.1f}" if np.isfinite(delta) else None)
                    h3.metric("Dagens relevans", f"{_num(case['Dagens relevans']):.0f}/100")
                    h4.metric("Prioritet", str(case["Prioritet"]))
                    c1, c2, c3 = st.columns(3)
                    c1.markdown("**Varför idag**")
                    c1.write(str(case["Varför idag"]))
                    c2.markdown("**Vad har förändrats**")
                    c2.write(str(case["Förändrat"]))
                    c3.markdown("**Kontrollera innan du går vidare**")
                    c3.write(str(case["Kontrollera"]))

            st.divider()
            st.subheader("Jämför dagens kortlista")
            quick_cols = ["Ticker", "Namn", "Borsiq Score", "Dagens relevans", "Prioritet", "Score Δ", "Värdering", "Kvalitet", "Marknadsläge", "Risk", "Riskflaggor"]
            quick = daily_shortlist[quick_cols].copy()
            st.dataframe(quick, use_container_width=True, hide_index=True, column_config={
                "Borsiq Score": st.column_config.ProgressColumn("Borsiq", min_value=0, max_value=100, format="%.0f"),
                "Dagens relevans": st.column_config.ProgressColumn("Dagens relevans", min_value=0, max_value=100, format="%.0f"),
                "Score Δ": st.column_config.NumberColumn("Score Δ", format="%+.1f"),
                "Värdering": st.column_config.ProgressColumn("Värdering", 0, 100, format="%.0f"),
                "Kvalitet": st.column_config.ProgressColumn("Kvalitet", 0, 100, format="%.0f"),
                "Marknadsläge": st.column_config.ProgressColumn("Setup", 0, 100, format="%.0f"),
                "Risk": st.column_config.ProgressColumn("Risk", 0, 100, format="%.0f"),
            })

        st.divider(); st.subheader("Topplista enligt ren Borsiq Score")
        display = dataframe_for_display(top)
        st.dataframe(display, use_container_width=True, hide_index=True, column_config={
            "Borsiq Score": st.column_config.ProgressColumn("Borsiq Score", min_value=0, max_value=100, format="%.0f"),
            "Pris": st.column_config.NumberColumn("Pris", format="%.2f"), "Dagsförändring": st.column_config.NumberColumn("Idag", format="%.2f%%"),
            "P/E": st.column_config.NumberColumn("P/E", format="%.1f"), "Direktavkastning": st.column_config.NumberColumn("DA", format="%.1f%%"),
            "52v från topp": st.column_config.NumberColumn("Från 52v-topp", format="%.1f%%"), "RSI14": st.column_config.NumberColumn("RSI", format="%.0f"),
            "Värdering": st.column_config.ProgressColumn("Värdering",0,100,format="%.0f"), "Kvalitet": st.column_config.ProgressColumn("Kvalitet",0,100,format="%.0f"),
            "Marknadsläge": st.column_config.ProgressColumn("Setup",0,100,format="%.0f"), "Risk": st.column_config.ProgressColumn("Risk",0,100,format="%.0f"),
        })
        st.download_button("Ladda ner topplistan som CSV", data=display.to_csv(index=False).encode("utf-8-sig"), file_name=f"borsiq_{datetime.now():%Y-%m-%d}.csv", mime="text/csv")
        st.divider(); st.subheader("Detaljanalys")
        choices = {f"{r['Ticker']} · {r['Namn']} · {r['Borsiq Score']:.0f}/100": i for i,r in top.iterrows()}
        selected = st.selectbox("Välj aktie", list(choices)); render_detail(top.loc[choices[selected]], profile)
    with tab4:
        st.subheader("Marknad · hela analysuniversumet")
        st.caption("Här finns rålistan för jämförelser och egen analys. Överblick och Dagens fynd är de rekommenderade startpunkterna.")
        st.dataframe(dataframe_for_display(scored), use_container_width=True, hide_index=True)
    with tab2:
        st.subheader("Borsiq Radar · dagens förändringar")
        today_str = datetime.now().date().isoformat()
        today_hist = signal_history_global.copy()
        if not today_hist.empty:
            today_hist = today_hist[today_hist["occurred_date"].astype(str) == today_str]
        if today_hist.empty:
            st.info("Inga sparade Radar-händelser för idag ännu. De skapas vid analys eller av den schemalagda scanningen.")
        else:
            r1, r2, r3 = st.columns(3)
            r1.metric("Händelser idag", len(today_hist))
            r2.metric("Hög prioritet", int((pd.to_numeric(today_hist["priority"], errors="coerce") >= 3).sum()))
            r3.metric("Berörda aktier", int(today_hist["symbol"].astype(str).nunique()))
            for _, sig in today_hist.sort_values(["priority", "created_at"], ascending=[False, False]).head(8).iterrows():
                icon = "🔔" if int(sig["priority"]) >= 3 else "⚠️"
                st.markdown(f"**{icon} {sig['kind']} · {sig['symbol']}** — {sig['text']}")

        st.divider()
        st.subheader("Signalhistorik")
        st.caption("Signaler sparas i historiken och kan markeras som lästa. Trösklar för Score och dagsfall kan ställas per bevakad aktie.")
        if not watched_global:
            st.info("Lägg till aktier i bevakningslistan för att få signaler.")
        else:
            if unread_signals:
                if st.button(f"Markera alla {unread_signals} som lästa", use_container_width=False):
                    mark_all_signals_read(); st.rerun()
            history_mode = st.radio("Visa", ["Olästa", "Alla"], horizontal=True, label_visibility="collapsed")
            hist = signal_history_global.copy()
            if history_mode == "Olästa" and not hist.empty:
                hist = hist[~hist["is_read"].astype(bool)]
            if hist.empty:
                st.info("Inga signaler i den valda vyn.")
            else:
                for _, sig in hist.head(100).iterrows():
                    icon = "🔔" if int(sig["priority"]) >= 3 else "⚠️"
                    read_label = "Läst" if bool(sig["is_read"]) else "Oläst"
                    email_label = " · E-post skickad" if pd.notna(sig.get("email_sent_at")) and str(sig.get("email_sent_at") or "").strip() else ""
                    with st.container(border=True):
                        st.markdown(f"**{icon} {sig['kind']} · {sig['symbol']}** · {sig['occurred_date']} · {read_label}{email_label}")
                        st.write(str(sig["text"]))
                        if not bool(sig["is_read"]) and st.button("Markera läst", key=f"read_{sig['event_key']}"):
                            mark_signal_read(str(sig["event_key"]), True); st.rerun()
            st.caption("Regler: ny i topp 10, egen Score-förändringsgräns, egen Score-nivå, målkurs och egen dagsfallsgräns.")

        st.divider()
        st.subheader("E-postnotiser")
        if not (cloud_enabled() and current_user_id()):
            st.info("E-postnotiser kräver inloggat Supabase-konto. Lokalt gästläge sparar bara signalerna i appen.")
        else:
            prefs = get_notification_preferences()
            with st.form("notification_preferences_form"):
                enabled = st.checkbox("Skicka e-post efter den automatiska vardagsscanningen", value=bool(prefs.get("email_enabled", False)))
                email = st.text_input("Mottagare", value=str(prefs.get("email") or current_user_email()))
                min_priority = st.select_slider(
                    "Minsta prioritet", options=[1, 2, 3], value=int(prefs.get("min_priority", 2)),
                    format_func=lambda x: {1: "Alla", 2: "Viktiga", 3: "Hög"}[x],
                )
                selected_kinds = st.multiselect("Signaltyper", SIGNAL_KINDS, default=[x for x in prefs.get("notify_kinds", SIGNAL_KINDS) if x in SIGNAL_KINDS])
                save_notif = st.form_submit_button("Spara e-postinställningar")
            if save_notif:
                if enabled and ("@" not in email or "." not in email.split("@")[-1]):
                    st.error("Ange en giltig e-postadress.")
                elif enabled and not selected_kinds:
                    st.error("Välj minst en signaltyp eller stäng av e-postnotiser.")
                else:
                    update_notification_preferences(enabled, email, min_priority, selected_kinds)
                    st.success("E-postinställningarna är sparade.")
            st.caption("Leverans sker från den schemalagda serverkörningen. Resend/API-nyckeln ligger bara i GitHub Secrets/servermiljö, aldrig i klientappen.")

    with tab3:
        st.subheader("Min bevakning")
        watch_meta = watch_meta_global
        watched = watched_global
        if not watched:
            st.info("Bevakningslistan är tom. Lägg till en aktie från detaljanalysen.")
        else:
            watch_df = watch_df_global.copy()
            if not watch_df.empty:
                order = {sym: i for i, sym in enumerate(watched)}
                watch_df["_watch_order"] = watch_df["Ticker"].map(order).fillna(9999)
                watch_df = watch_df.sort_values("_watch_order").drop(columns=["_watch_order"])
                watch_display = dataframe_for_display(watch_df)
                watch_display.insert(4, "Score Δ", [score_change(str(r["Ticker"]), profile, float(r["Borsiq Score"])) for _, r in watch_df.iterrows()])
                st.dataframe(watch_display, use_container_width=True, hide_index=True, column_config={"Score Δ": st.column_config.NumberColumn("Score Δ", format="%+.1f")})
                st.download_button("Exportera bevakningslista", data="Ticker\n" + "\n".join(watched), file_name="borsiq_bevakning.csv", mime="text/csv")

            st.markdown("#### Anteckningar och målkurser")
            for _, meta in watch_meta.iterrows():
                sym = str(meta["symbol"])
                current_note = str(meta.get("note") or "")
                current_target = _num(meta.get("target_price"))
                with st.expander(sym, expanded=False):
                    note = st.text_area("Anteckning", value=current_note, key=f"note_{sym}")
                    target = st.number_input(
                        "Målkurs (0 = ingen)", min_value=0.0, value=float(current_target) if np.isfinite(current_target) and current_target > 0 else 0.0, step=1.0, key=f"target_{sym}"
                    )
                    current_threshold = _num(meta.get("signal_score_threshold")); current_move = _num(meta.get("signal_score_move")); current_drop = _num(meta.get("signal_daily_drop"))
                    st.markdown("**Signalgränser**")
                    t1, t2, t3 = st.columns(3)
                    score_threshold = t1.number_input("Score-nivå", 0.0, 100.0, float(current_threshold) if np.isfinite(current_threshold) else 75.0, 1.0, key=f"threshold_{sym}")
                    score_move = t2.number_input("Score-förändring", 1.0, 50.0, float(current_move) if np.isfinite(current_move) else 8.0, 1.0, key=f"move_{sym}")
                    daily_drop = t3.number_input("Dagsfall %", 1.0, 50.0, float(current_drop) if np.isfinite(current_drop) else 5.0, 0.5, key=f"drop_{sym}")
                    csave, crem = st.columns(2)
                    if csave.button("Spara", key=f"save_watch_{sym}", use_container_width=True):
                        update_watchlist_item(sym, note, target if target > 0 else None, score_threshold, score_move, daily_drop)
                        st.success("Sparat")
                    if crem.button("Ta bort", key=f"remove_watch_{sym}", use_container_width=True):
                        toggle_watchlist(sym)
                        st.rerun()
            if st.button("Töm bevakningslistan"):
                clear_watchlist()
                st.rerun()
        st.caption("Inloggad användare: bevakning, scorehistorik, radarhistorik och signalhistorik lagras i Supabase. Gäst/lokalt läge: SQLite används på aktuell dator.")
    with tab5:
        w = PROFILE_WEIGHTS[profile]
        st.subheader("Så räknas Borsiq Score")
        st.markdown(f"""
    **Vald strategi: {profile}.** Vikter: värdering {w['valuation']:.0%}, kvalitet {w['quality']:.0%}, marknadsläge {w['setup']:.0%}, utdelning {w['income']:.0%}, risk {w['risk']:.0%}.

    **Värdering** jämför P/E, forward P/E, P/B, EV/EBITDA och FCF-yield i första hand relativt andra bolag i samma sektor när underlaget är tillräckligt. Det minskar problemet att exempelvis bank och industri behandlas som identiska.

    **Kvalitet** väger ROE, marginaler, tillväxt och skuld. **Marknadsläge** kombinerar rekyl från 52-veckorstopp, RSI, tremånadersmomentum och SMA200. **Utdelning** väger direktavkastning tillsammans med utdelningsandel. **Risk** drar ned bolag med negativ lönsamhet, hög skuld eller kraftigt fallande trend.

    Aktier med låg datatäckning får en försiktig rabatt. En hög score är en prioriteringssignal för vidare analys, inte en prognos om framtida avkastning.

    **Bevakningssignaler** jämför aktuell körning med tidigare dagssnapshots, din målkurs och dina egna tröskelvärden per aktie. Signalhistorik sparas med läst/oläst-status. Inloggade användare kan välja vilka signaltyper som ska skickas som e-post efter den schemalagda scanningen. De är regelbaserade informationshändelser, inte automatiska affärsförslag.
    """)

    st.caption("Konton/molnsynk: Supabase när konfigurerat. Datakälla: Yahoo Finance via yfinance. Sverige bred läses från universe.csv och är inte garanterat en officiell komplett Nasdaq-lista. Kontrollera alltid rapporter, nyheter, kassaflöde, skuldsättning och bolagsspecifika händelser före investeringsbeslut.")


if __name__ == "__main__":
    main()
