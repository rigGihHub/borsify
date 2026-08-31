from __future__ import annotations

import math
import hmac
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

from idea_radar import fetch_public_idea_flow, map_mentions, build_verified_ideas

from edge_lab import (
    build_technical_history, summarize_backtest, summarize_universe_backtest,
    build_market_regime_history, summarize_backtest_by_regime, summarize_universe_backtest_by_regime,
    walk_forward_backtest, summarize_trading_friction, simulate_portfolio_backtest,
)

try:
    from supabase import Client, create_client
except Exception:
    Client = Any  # type: ignore
    create_client = None

APP_VERSION = "2.13.0"
APP_NAME = "Borsify"
APP_DOMAIN = "borsify.se"
APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "borsify.db"
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
    out["Borsify Score"] = (base * (.80 + .20 * coverage)).round(1).clip(0, 100)
    out["Riskflaggor"] = out.apply(_risk_flags, axis=1)
    out["Signal"] = out.apply(_signal_label, axis=1)
    out["Varför"] = out.apply(_why_text, axis=1)

    # v2.1: three distinct horizons. These are screening scores, not forecasts.
    growth = _mean_scores([
        _percentile_score(out["Omsättningstillväxt"].clip(-1, 2), True),
        _percentile_score(out["Vinsttillväxt"].clip(-1, 3), True),
        _percentile_score(out["FCF-yield"].clip(-.5, .5), True),
    ])
    invest = .34 * valuation + .31 * quality + .18 * risk + .12 * growth + .05 * setup

    vol_ratio = pd.to_numeric(out.get("Volymkvot", pd.Series(np.nan, index=out.index)), errors="coerce")
    vol_score = ((vol_ratio - .7) / 1.1 * 100).clip(0, 100).fillna(45)
    dist200 = pd.to_numeric(out["Avstånd SMA200"], errors="coerce")
    trend_score = pd.Series(45.0, index=out.index)
    trend_score.loc[dist200.between(0, .20)] = 85
    trend_score.loc[dist200.between(-.05, 0, inclusive="left")] = 65
    trend_score.loc[dist200 > .20] = 65
    trend_score.loc[dist200 < -.10] = 20
    swing = .48 * setup + .18 * trend_score + .17 * vol_score + .10 * risk + .07 * quality

    daily = pd.to_numeric(out["Dagsförändring"], errors="coerce")
    draw = pd.to_numeric(out["52v från topp"], errors="coerce")
    rsi_num = pd.to_numeric(out["RSI14"], errors="coerce")
    selloff = ((-daily - .015) / .10 * 100).clip(0, 100).fillna(0)
    draw_score = ((-draw - .08) / .32 * 100).clip(0, 100).fillna(25)
    oversold = ((48 - rsi_num) / 23 * 100).clip(0, 100).fillna(30)
    reversal = .27 * selloff + .20 * draw_score + .18 * oversold + .16 * quality + .12 * risk + .07 * valuation
    severe_mask = out["Riskflaggor"].astype(str).apply(lambda x: any(term in x for term in SEVERE_RISK_TERMS))
    reversal = reversal.where(~severe_mask, np.minimum(reversal, 62))

    out["INVEST Score"] = invest.round(1).clip(0, 100)
    out["SWING Score"] = swing.round(1).clip(0, 100)
    out["REVERSAL Score"] = reversal.round(1).clip(0, 100)
    return out.sort_values(["Borsify Score", "Datatäckning"], ascending=[False, False])


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
    score = _num(row.get("Borsify Score")); flags = str(row.get("Riskflaggor", ""))
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
    score = _num(row.get("Borsify Score"))
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

    # 'Dagens relevans' deliberately remains separate from Borsify Score. It emphasizes
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
        why_today.append(f"Borsify Score har stigit {delta:+.1f} sedan föregående snapshot")
    elif np.isfinite(delta) and delta <= -3:
        why_today.append(f"Borsify Score har fallit {delta:+.1f} sedan föregående snapshot")
    if np.isfinite(setup) and setup >= 70:
        why_today.append(f"marknadsläget är starkt i modellen ({setup:.0f}/100)")
    if np.isfinite(rsi) and 32 <= rsi <= 48:
        why_today.append(f"RSI {rsi:.0f} visar att kursen nyligen pressats ned till ett område där modellen ibland hittar återhämtningar")
    if np.isfinite(draw) and -.35 <= draw <= -.08:
        why_today.append(f"kursen ligger {abs(draw):.0%} under 52-veckorstopp")
    if np.isfinite(m3) and m3 >= .08:
        why_today.append(f"kursen har utvecklats {m3:+.0%} de senaste tre månaderna, vilket ger stöd åt den kortsiktiga trenden")
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
    pool = df.sort_values(["Borsify Score", "Datatäckning"], ascending=[False, False]).head(15).copy()
    cases = [_daily_case(row, profile) for _, row in pool.iterrows()]
    case_df = pd.DataFrame(cases, index=pool.index)
    for col in case_df.columns:
        pool[col] = case_df[col]
    return pool.sort_values(["Dagens relevans", "Borsify Score", "Datatäckning"], ascending=[False, False, False]).head(limit)


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


def _site_access_password() -> str:
    """Optional shared site password stored only in Streamlit Secrets."""
    try:
        return str(st.secrets.get("APP_ACCESS_PASSWORD", "")).strip()
    except Exception:
        return ""


def require_site_access() -> None:
    """Gate a public Streamlit deployment behind an app-level password when configured.

    Local development remains open if APP_ACCESS_PASSWORD is not configured.
    The password itself never belongs in source control.
    """
    expected = _site_access_password()
    if not expected:
        return
    if st.session_state.get("bq_site_access") is True:
        return

    st.subheader("Borsify är låst")
    st.caption("Ange åtkomstlösenordet för att öppna appen.")
    with st.form("site_access_form", clear_on_submit=True):
        supplied = st.text_input("Åtkomstlösenord", type="password")
        submitted = st.form_submit_button("Öppna Borsify", type="primary", use_container_width=True)
    if submitted:
        if hmac.compare_digest(supplied, expected):
            st.session_state["bq_site_access"] = True
            st.rerun()
        else:
            st.error("Fel lösenord.")
    st.stop()


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
    cols = ["Ticker", "Borsify Score", "Värdering", "Kvalitet", "Marknadsläge", "Utdelning", "Risk", "Datatäckning"]
    rows = df[df["Ticker"].isin(watched)][cols].dropna(subset=["Borsify Score"])
    if rows.empty:
        return
    today = datetime.now().date().isoformat()
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        for _, row in rows.iterrows():
            payload = {
                "user_id": uid, "symbol": str(row["Ticker"]), "score": float(row["Borsify Score"]), "profile": profile, "captured_date": today,
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
                float(row["Borsify Score"]), _num(row.get("Värdering")), _num(row.get("Kvalitet")), _num(row.get("Marknadsläge")),
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
    if np.isfinite(pe) and 0 < pe <= 15: strengths.append(f"P/E {pe:.1f} är relativt låg. Förenklat betalar marknaden inte lika många årsvinster för aktien som vid ett högt P/E.")
    if np.isfinite(fpe) and 0 < fpe < pe: strengths.append(f"Forward P/E {fpe:.1f} är lägre än historisk P/E {pe:.1f}.")
    if np.isfinite(fcfy) and fcfy >= .05: strengths.append(f"FCF-yield {fcfy:.1%} ger stöd åt värderingen.")
    if np.isfinite(roe) and roe >= .15: strengths.append(f"ROE {roe:.1%} visar att bolaget hittills varit bra på att skapa vinst med ägarnas kapital.")
    if np.isfinite(margin) and margin >= .10: strengths.append(f"Vinstmarginal {margin:.1%} är stark.")
    if np.isfinite(growth) and growth >= .08: strengths.append(f"Omsättningen växer {growth:.1%} enligt tillgänglig data.")
    if np.isfinite(rsi) and 32 <= rsi <= 48: strengths.append(f"RSI {rsi:.0f} visar att kursen nyligen pressats ned till ett område där modellen ibland hittar återhämtningslägen.")
    if np.isfinite(dy) and .025 <= dy <= .08: strengths.append(f"Direktavkastning {dy:.1%} bidrar positivt.")

    if np.isfinite(pe) and pe >= 30: weaknesses.append(f"P/E {pe:.1f} är högt. Det betyder att marknaden betalar mycket för varje krona i nuvarande vinst, vilket ökar kraven på framtida tillväxt.")
    if np.isfinite(roe) and roe < 0: weaknesses.append(f"ROE {roe:.1%} är negativ.")
    if np.isfinite(margin) and margin < 0: weaknesses.append(f"Vinstmarginal {margin:.1%} är negativ.")
    if np.isfinite(debt) and debt > 200: weaknesses.append(f"Skuld/eget kapital {debt:.0f} är hög och ger riskavdrag.")
    if np.isfinite(m3) and m3 <= -.15: weaknesses.append(f"Tremånadersmomentum {m3:.1%} är tydligt negativt.")
    if np.isfinite(dist) and dist <= -.10: weaknesses.append(f"Kursen ligger {abs(dist):.1%} under sitt 200-dagarssnitt (SMA200), vilket tyder på en svagare långsiktig kurstrend.")
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
    rows = top_df.head(20)[["Ticker", "Borsify Score"]].reset_index(drop=True)
    if client is not None and uid:
        for i, row in rows.iterrows():
            payload = {"user_id": uid, "symbol": str(row["Ticker"]), "profile": profile, "rank": int(i + 1), "score": float(row["Borsify Score"]), "captured_date": today}
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
                (str(row["Ticker"]), profile, int(i + 1), float(row["Borsify Score"]), today),
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
        score = _num(row.get("Borsify Score")); price = _num(row.get("Pris")); daily = _num(row.get("Dagsförändring"))
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
            signals.append({"priority": 3, "symbol": sym, "name": name, "kind": "Ny i topp 10", "text": f"{name} har gått in på plats {rank} i Borsify Radar ({score:.0f}/100)."})
        if delta is not None and delta >= move:
            signals.append({"priority": 3, "symbol": sym, "name": name, "kind": "Score lyfter", "text": f"Borsify Score har stigit {delta:+.1f} sedan föregående registrerade dag till {score:.0f}/100. Din gräns är {move:.1f}."})
        if prev is not None and prev < threshold <= score:
            signals.append({"priority": 2, "symbol": sym, "name": name, "kind": "Scoregräns passerad", "text": f"Borsify Score har passerat din gräns {threshold:.0f}: {prev:.1f} → {score:.1f}."})
        if np.isfinite(target) and np.isfinite(price) and price >= target:
            signals.append({"priority": 3, "symbol": sym, "name": name, "kind": "Målkurs nådd", "text": f"Kursen {price:.2f} har nått/passerat din målkurs {target:.2f}."})
        if np.isfinite(daily) and daily <= -(daily_drop / 100.0):
            signals.append({"priority": 2, "symbol": sym, "name": name, "kind": "Kraftigt dagsfall", "text": f"Aktien är ned {daily:.1%} idag, vilket passerar din gräns på {daily_drop:.1f} %. Kontrollera nyheter/bolagshändelser."})
        if delta is not None and delta <= -move:
            signals.append({"priority": 2, "symbol": sym, "name": name, "kind": "Score faller", "text": f"Borsify Score har sjunkit {delta:.1f} sedan föregående registrerade dag till {score:.0f}/100. Din gräns är {move:.1f}."})
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




def beginner_term(term: str) -> str:
    explanations = {
        "P/E": "hur många kronor marknaden betalar för varje krona i bolagets årsvinst. Lägre kan vara billigare, men bara om vinsten är hållbar",
        "ROE": "avkastning på eget kapital – ungefär hur effektivt bolaget använder ägarnas pengar för att skapa vinst",
        "RSI": "ett kortsiktigt temperaturmått för kursen. Lågt värde kan betyda att aktien nyligen pressats ned, högt värde att den gått starkt",
        "SMA200": "aktiekursens genomsnitt under ungefär 200 handelsdagar. Över snittet brukar tolkas som starkare lång trend, under som svagare",
        "ATR": "ett mått på hur mycket aktien normalt rör sig från dag till dag. Borsify använder det för att anpassa stop-avstånd efter aktiens normala svängningar",
        "direktavkastning": "årlig utdelning i förhållande till aktiekursen. 4 % betyder ungefär 4 kr i årlig utdelning per 100 kr investerat, om utdelningen ligger kvar",
        "drawdown": "hur mycket värdet som mest har fallit från en tidigare topp. −20 % betyder att 100 000 kr som mest tillfälligt hade varit nere kring 80 000 kr",
        "profit factor": "summan av vinster delad med summan av förluster. Över 1 betyder att vinsterna varit större än förlusterna i testet",
        "Sharpe": "ett förenklat mått på hur mycket avkastning strategin gett i förhållande till hur mycket den svängt. Högre är normalt bättre",
        "risk-on": "ett marknadsläge där börsen generellt är starkare och investerare oftare vågar ta mer risk",
        "risk-off": "ett försiktigare marknadsläge där börsen generellt är svagare och investerare söker mindre risk",
        "volatilitet": "hur mycket priset svänger. Hög volatilitet betyder större rörelser både upp och ned – inte automatiskt högre framtida avkastning",
        "likviditet": "hur lätt en aktie normalt går att köpa eller sälja utan att priset påverkas mycket. Låg likviditet kan ge sämre köp- och säljpris",
        "stop-loss": "en förutbestämd nivå där man planerar att sälja för att begränsa en förlust. Den garanterar inte exakt säljpris om kursen gapar",
        "hävstång": "att få större marknadsexponering än det kapital man satt in. Det förstorar både vinster och förluster och innebär högre risk",
        "diversifiering": "att sprida kapitalet på flera innehav så att ett enskilt bolag inte får lika stor påverkan på hela portföljen",
    }
    return explanations.get(term, term)


def render_beginner_glossary(key: str = "guide") -> None:
    labels = {"overview_terms": "Överblick", "daily_terms": "Dagens fynd", "edge_terms": "Edge Lab"}
    suffix = labels.get(key, key.replace("_", " ").strip().title())
    with st.expander(f"Förklara börsorden enkelt · {suffix}", expanded=False):
        st.markdown(f"""
**P/E:** {beginner_term("P/E")}.  
**ROE:** {beginner_term("ROE")}.  
**RSI:** {beginner_term("RSI")}.  
**SMA200:** {beginner_term("SMA200")}.  
**Direktavkastning:** {beginner_term("direktavkastning")}.  
**Drawdown:** {beginner_term("drawdown")}.  
**Profit factor:** {beginner_term("profit factor")}.  
**ATR:** {beginner_term("ATR")}.  
**Volatilitet:** {beginner_term("volatilitet")}.  
**Likviditet:** {beginner_term("likviditet")}.  
**Stop-loss:** {beginner_term("stop-loss")}.
""")



DISCOVERY_INTENTS = [
    "Bästa möjligheter just nu",
    "Bra långsiktig investering",
    "Utdelningsaktier",
    "Billiga kvalitetsbolag",
    "Aktier som fallit mycket",
    "Kortsiktigt köpläge",
    "Stabilare aktier",
]


def apply_discovery_intent(df: pd.DataFrame, intent: str) -> pd.DataFrame:
    """Rank the already screened universe by a beginner-friendly goal without changing core scores."""
    out = df.copy()
    def c(name: str, default: float = 50.0) -> pd.Series:
        if name not in out.columns:
            return pd.Series(default, index=out.index, dtype=float)
        return pd.to_numeric(out[name], errors="coerce").fillna(default)
    if intent == "Bra långsiktig investering":
        match = c("INVEST Score")
    elif intent == "Utdelningsaktier":
        match = .55*c("Utdelning") + .20*c("Kvalitet") + .15*c("Risk") + .10*c("Värdering")
        dy = pd.to_numeric(out.get("Direktavkastning"), errors="coerce")
        out = out[dy.notna() & (dy > 0)].copy(); match = match.loc[out.index]
    elif intent == "Billiga kvalitetsbolag":
        match = .45*c("Värdering") + .35*c("Kvalitet") + .20*c("Risk")
    elif intent == "Aktier som fallit mycket":
        match = c("REVERSAL Score")
    elif intent == "Kortsiktigt köpläge":
        match = c("SWING Score")
    elif intent == "Stabilare aktier":
        match = .55*c("Risk") + .30*c("Kvalitet") + .15*c("Värdering")
    else:
        match = c("Borsify Score")
    out["Match Score"] = pd.to_numeric(match, errors="coerce").reindex(out.index).fillna(0).round(1)
    return out.sort_values(["Match Score", "Datatäckning"], ascending=[False, False])


def intent_plain_text(intent: str) -> str:
    texts = {
        "Bästa möjligheter just nu": "En bred ranking av aktier som sammantaget ser mest intressanta ut enligt din valda Borsify-strategi.",
        "Bra långsiktig investering": "Prioriterar bolag som kombinerar kvalitet, rimlig värdering och risk för ett längre ägande.",
        "Utdelningsaktier": "Visar bara bolag med registrerad utdelning och prioriterar både direktavkastning och hur hållbar utdelningen verkar vara.",
        "Billiga kvalitetsbolag": "Letar efter en kombination av attraktiv värdering och starkare bolagskvalitet – inte bara lågt P/E.",
        "Aktier som fallit mycket": "Letar efter möjliga överreaktioner efter kursfall, men väger samtidigt in kvalitet och risk för att undvika rena fallande knivar.",
        "Kortsiktigt köpläge": "Prioriterar kursläge, trend och momentum för dagar till veckor. Det är mer timing än bolagsvärdering.",
        "Stabilare aktier": "Prioriterar högre riskbetyg och kvalitet. Stabilare betyder inte riskfritt – aktier kan alltid falla.",
    }
    return texts.get(intent, "")


def dividend_safety_label(row: pd.Series) -> tuple[str, str]:
    payout = _num(row.get("Utdelningsandel")); quality = _num(row.get("Kvalitet")); dy = _num(row.get("Direktavkastning"))
    if not np.isfinite(dy) or dy <= 0:
        return "Ingen registrerad utdelning", "Datakällan visar ingen positiv direktavkastning just nu."
    if not np.isfinite(payout):
        return "Oklar", "Utdelningsandelen saknas, så Borsify kan inte bedöma hur stor del av vinsten som delas ut."
    if payout > 1:
        return "Förhöjd risk", "Bolaget delar enligt aktuell data ut mer än hela vinsten. Det kan vara tillfälligt men bör kontrolleras."
    if payout > .80:
        return "Bevaka", "En stor del av vinsten delas ut. Det lämnar mindre marginal om vinsten försvagas."
    if .25 <= payout <= .75 and np.isfinite(quality) and quality >= 60:
        return "Ser rimlig ut", "Utdelningen tar en måttlig del av vinsten och bolagets kvalitetsbetyg är samtidigt relativt starkt."
    return "Neutral", "Utdelningen ser inte uppenbart ansträngd ut i de få mått Borsify har, men historiken behöver fortfarande kontrolleras."


def quality_at_fair_price_snapshot(row: pd.Series) -> tuple[float, list[str], list[str]]:
    """Current-snapshot quality/value check inspired by long-term quality-at-a-fair-price thinking.

    This deliberately does not pretend to measure multi-year durability because the current
    Yahoo snapshot does not provide point-in-time 5-10 year fundamentals in the screener.
    """
    quality = _num(row.get("Kvalitet")); valuation = _num(row.get("Värdering")); risk = _num(row.get("Risk"))
    roe = _num(row.get("ROE")); margin = _num(row.get("Vinstmarginal")); debt = _num(row.get("Skuld/eget kapital"))
    fcf = _num(row.get("FCF-yield")); growth = _num(row.get("Vinsttillväxt"))
    parts = [x for x in [quality, valuation, risk] if np.isfinite(x)]
    base = np.mean(parts) if parts else 50.0
    score = .45*(quality if np.isfinite(quality) else base) + .35*(valuation if np.isfinite(valuation) else base) + .20*(risk if np.isfinite(risk) else base)
    positives, cautions = [], []
    if np.isfinite(roe):
        (positives if roe >= .15 else cautions).append(f"ROE {fmt_pct(roe)}: " + ("bolaget använder ägarnas kapital effektivt i dagens data." if roe >= .15 else "lönsamheten är inte särskilt hög i dagens data."))
    if np.isfinite(margin):
        (positives if margin >= .10 else cautions).append(f"Vinstmarginal {fmt_pct(margin)}: " + ("en hygglig del av försäljningen blir vinst." if margin >= .10 else "marginalen är tunnare och ger mindre felmarginal."))
    if np.isfinite(debt):
        (positives if debt <= 100 else cautions).append(f"Skuld/eget kapital {debt:.0f}: " + ("skuldsättningen ser måttlig ut i den här grova kontrollen." if debt <= 100 else "skuldsättningen är högre och behöver granskas närmare."))
    if np.isfinite(fcf):
        (positives if fcf > .03 else cautions).append(f"Fritt kassaflöde/börsvärde {fmt_pct(fcf)}: " + ("bolaget genererar kontanter i förhållande till priset." if fcf > .03 else "kassaflödesavkastningen är låg eller svag just nu."))
    if np.isfinite(growth) and growth < 0:
        cautions.append(f"Vinsttillväxt {fmt_pct(growth)}: vinsten minskar enligt senaste tillgängliga uppgift.")
    return round(float(np.clip(score, 0, 100)), 1), positives[:4], cautions[:4]


def render_quality_at_fair_price(df: pd.DataFrame) -> None:
    if df.empty:
        return
    rows=[]
    for _, r in df.iterrows():
        score, positives, cautions = quality_at_fair_price_snapshot(r)
        rr=r.copy(); rr["QRP Score"]=score; rr["QRP Positives"]=positives; rr["QRP Cautions"]=cautions; rows.append(rr)
    q=pd.DataFrame(rows).sort_values(["QRP Score", "Datatäckning"], ascending=[False, False]).head(5)
    st.subheader("Kvalitet till rätt pris · långsiktig kontroll")
    st.caption("Inspirerad av principen att hellre leta efter bra bolag till rimliga priser än enbart billiga aktier. Detta är en nulägeskontroll – Borsify saknar ännu 5–10 års point-in-time fundamentahistorik för att bevisa uthålligheten.")
    for rank, (_, r) in enumerate(q.iterrows(), 1):
        with st.container(border=True):
            c1,c2,c3,c4=st.columns([2.7,1,1,1])
            c1.markdown(f"**{rank}. {r.get('Namn','')} · {r.get('Ticker','')}**")
            c1.caption("Bra företag + rimligt pris + hanterbar risk väger tyngst i den här kontrollen.")
            c2.metric("Kvalitet/pris", f"{_num(r.get('QRP Score')):.0f}/100")
            c3.metric("Kvalitet", f"{_num(r.get('Kvalitet')):.0f}/100")
            c4.metric("Värdering", f"{_num(r.get('Värdering')):.0f}/100")
            pos=r.get("QRP Positives") or []; caut=r.get("QRP Cautions") or []
            if pos: st.write("**Det som talar för:** " + " ".join(pos))
            if caut: st.write("**Det som behöver kollas:** " + " ".join(caut))


@st.cache_data(ttl=900, show_spinner=False)
def fetch_idea_flow_cached() -> tuple[pd.DataFrame, list[str]]:
    return fetch_public_idea_flow()


def render_idea_flow(scored: pd.DataFrame) -> None:
    st.subheader("Idéflöde · vad pratas det om just nu?")
    st.caption("Borsify använder media och forum för att hitta uppslag – aldrig som bevis för att en aktie är bra. Varje matchad aktie måste därefter klara kontrollen av pris, kvalitet, risk och övriga nyckeltal.")
    st.info("Många omnämnanden kan göra ett uppslag lättare att upptäcka, men de höjer **inte** Borsify Score. Forum väger dessutom lägre än ekonomimedia i själva upptäcktsstyrkan.")

    f1, f2 = st.columns([1.2, 2.2])
    with f1:
        fetch_clicked = st.button("Hämta senaste uppslag", key="idea_flow_fetch", type="primary", use_container_width=True)
    with f2:
        flow_filter = st.radio("Visa", ["Alla", "Ekonomimedia", "Forum"], horizontal=True, key="idea_flow_kind_filter")

    if fetch_clicked:
        with st.spinner("Hämtar publika rubriker och foruminlägg…"):
            feed, errors = fetch_idea_flow_cached()
            st.session_state["idea_flow_feed"] = feed
            st.session_state["idea_flow_errors"] = errors

    feed = st.session_state.get("idea_flow_feed")
    errors = st.session_state.get("idea_flow_errors", [])
    if feed is None:
        st.write("Tryck på knappen. Borsify läser endast publika RSS/Atom-flöden och återger rubrik, källa och länk – inte hela artiklar.")
        with st.expander("Vilka typer av källor bevakas?"):
            st.write("Ekonomimedia: EFN direkt RSS samt svenska ekonomimedier via Google News, inklusive flöden för breda börsnyheter, analyser/riktkurser och bolagshändelser. Forum: Reddit Aktiemarknaden och ISKbets. ISKbets behandlas uttryckligen som en mer spekulativ idékälla.")
        return

    if errors:
        with st.expander(f"{len(errors)} källa/källor kunde inte läsas"):
            st.write("Övriga källor används ändå. Felet kan vara tillfälligt eller bero på att en publik feed ändrats.")
            for e in errors:
                st.write(f"• {e}")
    if feed.empty:
        st.warning("Inga externa rubriker kunde hämtas just nu.")
        return

    view_feed = feed.copy()
    if flow_filter == "Ekonomimedia":
        view_feed = view_feed[view_feed["kind"] == "media"]
    elif flow_filter == "Forum":
        view_feed = view_feed[view_feed["kind"] == "forum"]

    mentions = map_mentions(view_feed, scored)
    ideas = build_verified_ideas(mentions, scored)
    media_items = int((feed["kind"] == "media").sum())
    forum_items = int((feed["kind"] == "forum").sum())
    publishers = int(feed.get("publisher", feed["source"]).astype(str).nunique())
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Uppslag hämtade", len(feed))
    m2.metric("Ekonomimedia", media_items)
    m3.metric("Forum", forum_items)
    m4.metric("Olika källor", publishers)

    if ideas.empty:
        st.info("Uppslag hämtades, men inget bolag kunde matchas säkert mot aktierna i ditt nuvarande universum med valt källfilter.")
        return

    passed = int((ideas.get("Borsify-granskning", pd.Series(dtype=str)) == "Klarar första kontrollen").sum())
    st.caption(f"{len(ideas)} aktier matchades · {passed} klarar Borsifys första kontroll. Upptäcktsstyrka betyder hur brett och nyligen aktien nämnts – inte förväntad avkastning.")

    for _, r in ideas.head(12).iterrows():
        status = str(r.get("Borsify-granskning", ""))
        with st.container(border=True):
            a, b, c = st.columns([3.2, 1, 1.25])
            a.markdown(f"### {r.get('Namn','')} · {r.get('Ticker','')}")
            media_sources = int(r.get("Mediekällor", 0) or 0)
            forum_sources = int(r.get("Forumkällor", 0) or 0)
            a.caption(f"{int(r.get('Antal omnämnanden',0))} uppslag · {media_sources} mediekälla/källor · {forum_sources} forumkälla/källor")
            b.metric("Borsify", f"{_num(r.get('Borsify Score')):.0f}/100" if np.isfinite(_num(r.get('Borsify Score'))) else "—")
            c.metric("Kontroll", status)
            st.write(str(r.get("Förklaring", "")))
            st.caption(f"Upptäcktsstyrka {_num(r.get('Upptäcktsstyrka')):.0f}/100 · mäter bara hur tydligt uppslaget syns i externa källor.")
            flags = str(r.get("Riskflaggor", ""))
            if flags and flags not in {"—", "nan"}:
                st.caption(f"Riskflaggor: {flags}")
            headlines = r.get("Rubriker") or []
            if headlines:
                with st.expander("Visa rubrikerna bakom uppslaget"):
                    for h in headlines:
                        title = str(h.get("title", "")).replace("[", "(").replace("]", ")")
                        link = str(h.get("link", ""))
                        source = str(h.get("source", ""))
                        category = str(h.get("category", ""))
                        label = f"{source} · {category}" if category else source
                        if link.startswith("http"):
                            st.markdown(f"- [{title}]({link}) · {label}")
                        else:
                            st.write(f"• {title} · {label}")

    with st.expander("Så ska mediabevakningen tolkas"):
        st.write("Borsify försöker hitta **uppslag**, inte följa flocken. Flera oberoende mediekällor ger högre upptäcktsstyrka än många inlägg från ett enda forum. Ett bolag kan ändå sorteras bort direkt om nyckeltalen är svaga. Spekulativa forumkällor får lägre vikt och kan aldrig ensamma ge maximal upptäcktsstyrka.")
        st.caption("Bevakningen bygger på publika flöden. Paywall-innehåll läses inte och Borsify ska inte tolka en rubrik som ett verifierat faktapåstående om bolaget.")


def render_dividend_discovery(df: pd.DataFrame) -> None:
    if df.empty: return
    div = apply_discovery_intent(df, "Utdelningsaktier").head(5)
    if div.empty: return
    st.subheader("Utdelningsläge · topp 5")
    st.caption("Hög direktavkastning är inte automatiskt bra. Borsify väger även in utdelningsandel, kvalitet och risk.")
    for rank, (_, r) in enumerate(div.iterrows(), 1):
        dy = _num(r.get("Direktavkastning")); payout = _num(r.get("Utdelningsandel")); label, why = dividend_safety_label(r)
        with st.container(border=True):
            a,b,c,d = st.columns([2.5,1,1,1.2])
            a.markdown(f"**{rank}. {r.get('Namn','')} · {r.get('Ticker','')}**")
            a.caption(why)
            b.metric("Direktavkastning", fmt_pct(dy))
            annual = dy*10000 if np.isfinite(dy) else np.nan
            c.metric("På 10 000 kr/år*", f"{annual:,.0f} kr".replace(",", " ") if np.isfinite(annual) else "—")
            d.metric("Utdelning", label)
            st.caption(f"Utdelningsandel: {fmt_pct(payout)} · *ungefärligt belopp före skatt om utdelningen ligger kvar och kurs/utdelning motsvarar dagens uppgifter.")

def _download_close_series(frame: pd.DataFrame, ticker: str = "^OMXS30") -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        level0 = set(map(str, data.columns.get_level_values(0)))
        level1 = set(map(str, data.columns.get_level_values(1)))
        try:
            if ticker in level0:
                data = data[ticker]
            elif ticker in level1:
                data = data.xs(ticker, axis=1, level=1, drop_level=True)
        except Exception:
            return pd.Series(dtype=float)
    if "Close" not in data.columns:
        return pd.Series(dtype=float)
    close = pd.to_numeric(data["Close"], errors="coerce").dropna()
    close.index = pd.to_datetime(close.index).tz_localize(None) if getattr(pd.to_datetime(close.index), "tz", None) is not None else pd.to_datetime(close.index)
    return close.sort_index()


def _performance_stats(index_series: pd.Series) -> dict[str, float]:
    s = pd.to_numeric(index_series, errors="coerce").dropna()
    if len(s) < 2 or _num(s.iloc[0]) <= 0:
        return {"return": np.nan, "cagr": np.nan, "volatility": np.nan, "sharpe": np.nan, "max_drawdown": np.nan}
    total = _num(s.iloc[-1] / s.iloc[0] - 1)
    days = max((pd.Timestamp(s.index[-1]) - pd.Timestamp(s.index[0])).days, 1)
    cagr = (s.iloc[-1] / s.iloc[0]) ** (365.25 / days) - 1 if s.iloc[-1] > 0 else np.nan
    rets = s.pct_change().dropna()
    vol = _num(rets.std(ddof=1) * np.sqrt(252)) if len(rets) >= 2 else np.nan
    sharpe = _num(rets.mean() / rets.std(ddof=1) * np.sqrt(252)) if len(rets) >= 2 and _num(rets.std(ddof=1)) > 0 else np.nan
    dd = s / s.cummax() - 1
    return {"return": total, "cagr": _num(cagr), "volatility": vol, "sharpe": sharpe, "max_drawdown": _num(dd.min())}


def parse_symbols(text: str) -> list[str]:
    symbols = []
    for item in text.replace(";", ",").replace("\n", ",").split(","):
        s = item.strip().upper()
        if not s: continue
        if "." not in s and "-" not in s: s += ".ST"
        symbols.append(s)
    return list(dict.fromkeys(symbols))


def dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["Ticker", "Namn", "Sektor", "Match Score", "Borsify Score", "Signal", "Pris", "Prisdatum", "Dagsförändring", "P/E", "Direktavkastning", "52v från topp", "RSI14", "Värdering", "Kvalitet", "Marknadsläge", "Risk", "Riskflaggor", "Varför"]
    display = df[[c for c in cols if c in df.columns]].copy()
    for col in ["Dagsförändring", "Direktavkastning", "52v från topp"]:
        if col in display: display[col] = pd.to_numeric(display[col], errors="coerce") * 100
    return display



def render_discovery_shortlist(df: pd.DataFrame, intent: str) -> None:
    st.subheader("Upptäck · bäst match för ditt mål")
    st.caption(intent_plain_text(intent))
    picks = df.head(5)
    if picks.empty:
        st.info("Inga aktier matchar ditt mål tillsammans med de övriga filtren.")
        return
    for rank, (_, r) in enumerate(picks.iterrows(), 1):
        with st.container(border=True):
            a,b,c,d = st.columns([2.7,1,1,1])
            a.markdown(f"**{rank}. {r.get('Namn','')} · {r.get('Ticker','')}**")
            a.caption(str(r.get("Varför", "Borsify har rankat aktien högt utifrån ditt val.")))
            b.metric("Match", f"{_num(r.get('Match Score')):.0f}/100")
            c.metric("Borsify", f"{_num(r.get('Borsify Score')):.0f}/100")
            price = _num(r.get("Pris")); ccy = str(r.get("Valuta") or "")
            d.metric("Kurs", f"{price:.2f} {ccy}" if np.isfinite(price) else "—", fmt_pct(r.get("Dagsförändring")))
    st.caption("Match visar hur väl aktien passar just det mål du valt. Borsify Score finns kvar som den bredare grundbedömningen.")

def investment_analysis_text(row: pd.Series, horizon: str = "INVEST") -> str:
    """Grounded explanation in plain Swedish for users without finance background."""
    name = str(row.get("Namn") or row.get("Ticker") or "Aktien")
    score_col = {"INVEST": "INVEST Score", "SWING": "SWING Score", "REVERSAL": "REVERSAL Score"}.get(horizon, "INVEST Score")
    score = _num(row.get(score_col)); val = _num(row.get("Värdering")); qual = _num(row.get("Kvalitet"))
    pe = _num(row.get("P/E")); roe = _num(row.get("ROE")); growth = _num(row.get("Vinsttillväxt")); m3 = _num(row.get("3 mån")); rsi = _num(row.get("RSI14")); vol = _num(row.get("Volymkvot")); draw = _num(row.get("52v från topp")); daily = _num(row.get("Dagsförändring")); dist = _num(row.get("Avstånd SMA200")); dy = _num(row.get("Direktavkastning"))
    flags = str(row.get("Riskflaggor", "—"))
    intro = f"{name} får {score:.0f}/100" if np.isfinite(score) else name
    if horizon == "INVEST":
        parts = [f"{intro} för långsiktigt ägande."]
        if np.isfinite(val) and val >= 65: parts.append("Priset ser relativt rimligt ut jämfört med liknande bolag.")
        if np.isfinite(qual) and qual >= 65: parts.append("Bolagets lönsamhet, tillväxt och ekonomi ser sammantaget starka ut i modellen.")
        if np.isfinite(pe): parts.append(f"P/E är {pe:.1f}; det betyder förenklat att marknaden betalar cirka {pe:.1f} gånger ett års nuvarande vinst.")
        if np.isfinite(roe): parts.append(f"ROE är {roe:.1%}; det visar hur effektivt bolaget använder ägarnas kapital.")
        if np.isfinite(growth): parts.append(f"Den registrerade vinsttillväxten är {growth:+.1%}.")
        if np.isfinite(dy) and dy > 0: parts.append(f"Direktavkastningen är cirka {dy:.1%}, alltså ungefär {dy*100:.1f} kr i årlig utdelning per 100 kr investerat om utdelningen ligger kvar.")
    elif horizon == "SWING":
        parts = [f"{intro} för ett kortare kursläge på dagar till veckor."]
        if np.isfinite(dist): parts.append("Kursen ligger över sitt 200-dagarssnitt, vilket brukar ses som en starkare lång trend." if dist >= 0 else "Kursen ligger under sitt 200-dagarssnitt, vilket betyder att den längre trenden är svagare.")
        if np.isfinite(m3): parts.append(f"På tre månader har kursen rört sig {m3:+.1%}.")
        if np.isfinite(rsi): parts.append(f"RSI är {rsi:.0f}; det är ett temperaturmått på den senaste kursrörelsen, där lägre nivåer ofta betyder att aktien pressats ned.")
        if np.isfinite(vol): parts.append(f"Handelsvolymen är {vol:.1f} gånger normalnivån för de senaste 20 dagarna.")
    else:
        parts = [f"{intro} som möjlig återhämtning efter en nedgång."]
        if np.isfinite(daily): parts.append(f"Aktien har rört sig {daily:+.1%} idag.")
        if np.isfinite(draw): parts.append(f"Den ligger cirka {abs(draw):.1%} under sin högsta nivå det senaste året.")
        if np.isfinite(rsi): parts.append(f"RSI är {rsi:.0f}; ett lågt värde kan betyda att säljtrycket varit ovanligt stort, men det garanterar inte en uppgång.")
        if np.isfinite(qual): parts.append(f"Bolagets kvalitetsbetyg är {qual:.0f}/100, vilket hjälper modellen att skilja en möjlig överreaktion från ett bolag med tydliga grundproblem.")
    if flags == "—":
        parts.append("Modellen hittar inga av sina grövre riskflaggor just nu.")
    else:
        parts.append(f"Det viktigaste att vara försiktig med är: {flags}.")
    parts.append("Se detta som en förklaring till varför aktien hamnat högt i Borsify – inte som ett löfte om att kursen kommer stiga.")
    return " ".join(parts)


def render_engine_board(df: pd.DataFrame) -> None:
    st.subheader("Tre motorer · olika tidshorisonter")
    st.caption("INVEST söker långsiktig kvalitet till rimligt pris. SWING söker tekniska lägen för dagar–veckor. REVERSAL söker möjliga överreaktioner. Modellerna ska inte blandas ihop.")
    specs=[("INVEST", "INVEST Score", "Lång sikt · ca 1–5 år"), ("SWING", "SWING Score", "Kort sikt · ca 2 dagar–8 veckor"), ("REVERSAL", "REVERSAL Score", "Överreaktion · dagar–månader") ]
    cols=st.columns(3)
    for col,(label,score_col,horizon) in zip(cols,specs):
        with col:
            st.markdown(f"### {label}")
            st.caption(horizon)
            top=df.sort_values([score_col,"Datatäckning"], ascending=[False,False]).head(3)
            for rank,(_,r) in enumerate(top.iterrows(),1):
                with st.container(border=True):
                    st.markdown(f"**{rank}. {r['Namn']} · {r['Ticker']}**")
                    e1, e2 = st.columns(2)
                    e1.metric(label, f"{_num(r[score_col]):.0f}/100")
                    price = _num(r.get("Pris"))
                    price_text = f"{price:.2f} {r.get('Valuta', '')}" if np.isfinite(price) else "—"
                    e2.metric("Aktuell kurs", price_text, fmt_pct(r.get("Dagsförändring")))
                    st.caption(f"Senaste kursdag: {r.get('Prisdatum', '—')}")
                    st.write(investment_analysis_text(r,label))


def render_detail(row: pd.Series, profile: str, key_prefix: str = "detail") -> None:
    st.subheader(f"{row['Namn']} · {row['Ticker']}")
    c1, c2, c3, c4, c5 = st.columns(5)
    prev = previous_score_snapshot(str(row["Ticker"]), profile)
    score_delta = None
    if prev and np.isfinite(_num(prev.get("score"))): score_delta = _num(row.get("Borsify Score")) - _num(prev.get("score"))
    c1.metric("Borsify Score", f"{row['Borsify Score']:.0f}/100", f"{score_delta:+.1f}" if score_delta is not None else None)
    c2.metric("Pris", f"{row['Pris']:.2f} {row.get('Valuta', '')}", fmt_pct(row.get("Dagsförändring")))
    c3.metric("Värdering", f"{row['Värdering']:.0f}")
    st.markdown("### Varför kan detta vara en bra investering?")
    st.write(investment_analysis_text(row, "INVEST"))
    qrp_score, qrp_pos, qrp_cautions = quality_at_fair_price_snapshot(row)
    with st.expander("Kvalitet till rätt pris · enkel långsiktig kontroll"):
        st.metric("Kvalitet/pris", f"{qrp_score:.0f}/100")
        st.write("**Vad betyder det?** Borsify tittar på om bolaget verkar lönsamt och finansiellt rimligt samtidigt som aktien inte ser för dyr ut. Det är en nulägeskontroll, inte ett bevis på att kvaliteten hållit i många år.")
        if qrp_pos: st.write("**Talar för:** " + " ".join(qrp_pos))
        if qrp_cautions: st.write("**Behöver kollas:** " + " ".join(qrp_cautions))
    render_beginner_glossary(f"{key_prefix}_terms")
    e1, e2, e3 = st.columns(3)
    e1.metric("INVEST", f"{_num(row.get('INVEST Score')):.0f}/100")
    e2.metric("SWING", f"{_num(row.get('SWING Score')):.0f}/100")
    e3.metric("REVERSAL", f"{_num(row.get('REVERSAL Score')):.0f}/100")
    with st.expander("Visa analys för kort sikt och överreaktion"):
        st.markdown("**SWING · dagar–veckor**")
        st.write(investment_analysis_text(row, "SWING"))
        st.markdown("**REVERSAL · möjlig överreaktion**")
        st.write(investment_analysis_text(row, "REVERSAL"))
    c4.metric("Kvalitet", f"{row['Kvalitet']:.0f}")
    c5.metric("Risk", f"{row['Risk']:.0f}")
    st.markdown(f"**Bedömning:** {row['Signal']}  \n**Kort förklaring:** {row['Varför']}  \n**Riskflaggor:** {row['Riskflaggor']}")

    factor_df, strengths, weaknesses = _score_explanation(row, profile)
    st.markdown("#### Varför får aktien den här poängen?")
    st.caption(f"Strategin {profile} väger delarna olika. Tänk på 50 som ett neutralt utgångsläge: en del över 50 hjälper aktien upp i rankingen och en del under 50 drar ned den. Tabellen visar ungefär hur stor påverkan varje del har.")
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
    st.caption("Enkelt uttryckt: Borsify väger ihop delbetygen och sänker sedan slutbetyget lite om viktig information saknas. Därför kan en aktie med bra delbetyg ändå få en försiktigare totalscore när datatäckningen är låg.")
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
    if st.button("Ta bort från bevakning" if watched else "Lägg till i bevakning", key=f"{key_prefix}_watch_{row['Ticker']}"):
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
    """Ren startsida: vad är intressant, varför och vad bör jag se upp med?"""
    best = daily_shortlist.iloc[0] if not daily_shortlist.empty else None
    high_priority = int((daily_shortlist["Prioritet"] == "Hög").sum()) if not daily_shortlist.empty else 0
    today = datetime.now().date().isoformat()
    today_signals = signal_history[signal_history["occurred_date"].astype(str) == today] if not signal_history.empty else pd.DataFrame()

    st.markdown("## Dagens mest intressanta aktie")
    st.caption("Borsify börjar med slutsatsen. Du kan öppna siffrorna och den fulla analysen när du vill.")
    if best is None:
        st.info("Ingen kandidat klarade dagens urval. Prova att lätta på filtren eller kontrollera datakällan.")
    else:
        with st.container(border=True):
            title, score, price = st.columns([3.2, 1, 1.25])
            title.markdown(f"## {best['Namn']}")
            title.caption(f"{best['Ticker']} · {best['Sektor']} · {best['Signal']}")
            score.metric("Borsify", f"{_num(best['Borsify Score']):.0f}/100")
            best_price = _num(best.get("Pris"))
            price.metric("Aktuell kurs", f"{best_price:.2f} {best.get('Valuta', '')}" if np.isfinite(best_price) else "—", fmt_pct(best.get("Dagsförändring")))

            why, caution = st.columns(2)
            with why:
                st.markdown("**Varför den sticker ut**")
                st.write(str(best.get("Varför idag", "—")))
            with caution:
                st.markdown("**Vad du bör kontrollera**")
                st.write(str(best.get("Kontrollera", "—")))
            changed = str(best.get("Förändrat", "")).strip()
            if changed and changed != "—":
                st.caption(f"Vad som förändrats: {changed}")
            st.caption("Borsify pekar ut vad som är värt att undersöka vidare. Det är inte ett köp- eller säljråd.")

    s1, s2, s3 = st.columns(3)
    s1.metric("Fler med hög prioritet", high_priority)
    s2.metric("Nya Radar-signaler", unread_signals)
    s3.metric("Bevakade aktier", len(watch_df))

    if len(daily_shortlist) > 1:
        st.markdown("### Fler aktier värda en titt")
        compact = daily_shortlist.iloc[1:5][["Ticker", "Namn", "Pris", "Valuta", "Dagsförändring", "Borsify Score", "Dagens relevans", "Prioritet"]].copy()
        st.dataframe(
            compact, use_container_width=True, hide_index=True,
            column_config={
                "Borsify Score": st.column_config.ProgressColumn("Borsify", min_value=0, max_value=100, format="%.0f"),
                "Dagens relevans": st.column_config.ProgressColumn("Idag", min_value=0, max_value=100, format="%.0f"),
                "Pris": st.column_config.NumberColumn("Kurs", format="%.2f"),
                "Dagsförändring": st.column_config.NumberColumn("Idag %", format="%.2f%%"),
            },
        )

    if not today_signals.empty or unread_signals:
        with st.expander(f"Radar · {unread_signals} olästa signaler", expanded=False):
            if today_signals.empty:
                st.write("Inga nya signaler idag.")
            else:
                for _, sig in today_signals.sort_values(["priority", "created_at"], ascending=[False, False]).head(6).iterrows():
                    prefix = "🔔" if int(sig.get("priority", 1)) >= 3 else "•"
                    st.markdown(f"{prefix} **{sig['symbol']} · {sig['kind']}** — {sig['text']}")

    st.markdown("### Vill du förstå en kandidat bättre?")
    candidates = filtered.head(min(25, len(filtered)))
    choices = {f"{r['Ticker']} · {r['Namn']} · {r['Borsify Score']:.0f}/100": i for i, r in candidates.iterrows()}
    if choices:
        selected = st.selectbox("Välj aktie", list(choices), key="overview_detail_choice")
        with st.expander("Öppna full analys", expanded=False):
            render_detail(candidates.loc[choices[selected]], profile, key_prefix="overview")

    with st.expander("Datastatus", expanded=False):
        st.write(f"Strategi: {profile} · analyserade: {len(scored)} · efter filter: {len(filtered)} · senaste kursdag: {latest_price_date} · körtid: {elapsed:.1f} s")
        if idx:
            st.write(f"OMXS30: {idx['index']:.2f} ({fmt_pct(idx.get('daily'))})")
        st.caption(f"Borsify v{APP_VERSION}. Kurs- och fundamentaldata kan vara fördröjd eller ofullständig.")


def render_edge_lab(default_symbol: str) -> None:
    st.subheader("Edge Lab · historiskt signaltest")
    st.caption("Edge Lab försöker svara på en enkel fråga: om Borsify hade gett samma signaler tidigare, hur hade de gått då? Historik bevisar inte vad som händer framåt, men hjälper oss att upptäcka svaga modeller.")
    render_beginner_glossary("edge_terms")
    st.caption("Testar tekniska signaler historiskt utan att använda dagens fundamentaldata. Det är medvetet: dagens fundamenta på gamla datum skulle skapa look-ahead bias. Grundtestet visar bruttoresultat. Längre ned kan du lägga på courtage, spread/slippage och positionsstorlek för ett mer ekonomiskt realistiskt stresstest.")
    c1, c2, c3, c4 = st.columns([1.5, 1, 1, 1])
    symbol = c1.text_input("Ticker", value=default_symbol or "INVE-B.ST", key="edge_symbol").strip().upper()
    engine = c2.selectbox("Motor", ["SWING", "REVERSAL"], key="edge_engine")
    threshold = c3.slider("Min score", 40, 90, 70, 5, key="edge_threshold")
    horizon = c4.selectbox("Utfall efter", [5, 10, 20], index=1, format_func=lambda x: f"{x} börsdagar", key="edge_horizon")
    years = st.slider("Historik", 2, 10, 5, key="edge_years")

    if not symbol:
        st.info("Ange en ticker.")
        return
    period = f"{years}y"
    try:
        hist = yf.download(symbol, period=period, interval="1d", auto_adjust=False, progress=False, threads=False)
    except Exception as exc:
        st.error(f"Kunde inte hämta historik för {symbol}: {exc}")
        return
    tech = build_technical_history(hist)
    if tech.empty:
        st.warning("Det finns inte tillräcklig historik för att köra testet.")
        return
    score_col = "swing_proxy" if engine == "SWING" else "reversal_proxy"
    summary = summarize_backtest(tech, score_col, threshold, horizon)
    if int(summary.get("signals", 0)) == 0:
        st.warning("Inga historiska signaler hittades med vald tröskel. Sänk scoregränsen eller öka historiken.")
        return

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Historiska signaler", int(summary["signals"]))
    m2.metric("Träffsäkerhet", f"{summary['win_rate']:.1%}", f"vs {summary['baseline_win_rate']:.1%}")
    m3.metric("Medianavkastning", f"{summary['median_return']:.2%}", f"vs {summary['baseline_median_return']:.2%}")
    m4.metric("Snittavkastning", f"{summary['mean_return']:.2%}")
    pf = summary.get("profit_factor", np.nan)
    m5.metric("Profit factor", f"{pf:.2f}" if np.isfinite(pf) else "—", help=beginner_term("profit factor"))

    edge_win = summary["win_rate"] - summary["baseline_win_rate"]
    edge_med = summary["median_return"] - summary["baseline_median_return"]
    if int(summary["signals"]) < 30:
        st.warning("Litet stickprov. Under 30 signaler är för tunt för att dra starka slutsatser.")
    elif edge_win > .05 and edge_med > 0:
        st.success(f"Den här proxy-signalen har historiskt slagit baslinjen för {symbol} i valt test: +{edge_win:.1%} högre träffsäkerhet och {edge_med:+.2%} bättre medianutfall. Det är inte bevis för framtida edge.")
    elif edge_win < 0 and edge_med <= 0:
        st.error("Den valda signalen har inte visat historisk edge mot baslinjen i detta test. Det är ett skäl att inte höja modellvikten utan vidare.")
    else:
        st.info("Resultatet är blandat. Signalen bör inte betraktas som verifierad edge utan bredare test över fler aktier och marknadsregimer.")

    fwd_col = f"fwd_{horizon}d"
    hits = tech[tech[score_col] >= threshold].dropna(subset=[fwd_col]).copy().tail(100)
    if not hits.empty:
        shown = pd.DataFrame({
            "Datum": hits.index.astype(str).str[:10],
            "Score": hits[score_col].round(1).values,
            f"Utfall {horizon}d": (hits[fwd_col] * 100).round(2).values,
            "RSI14": hits["rsi14"].round(1).values,
            "Volymkvot": hits["volume_ratio"].round(2).values,
            "Avstånd SMA200 %": (hits["dist_sma200"] * 100).round(1).values,
        })
        st.dataframe(shown.iloc[::-1], use_container_width=True, hide_index=True)

    st.markdown("**Vad Edge Lab inte testar ännu:** full INVEST-modell, historiska fundamenta, estimatrevideringar, sektorrotation, skatt, likviditetsbegränsningar och verkliga orderfyllnader. Portföljdelen längre ned modellerar samtidig exponering och kapitalbindning, men är fortfarande ett diagnostiskt backtest – inte verklig exekvering.")

    st.divider()
    st.subheader("Marknadsregim · när fungerar signalen?")
    st.caption("Samma signal delas upp efter OMXS30-regim. Regimen använder bara information som fanns den dagen: index mot SMA200, SMA50 mot SMA200 och 60-dagars momentum. Risk-on, Neutral och Risk-off testas separat.")
    try:
        benchmark_hist = yf.download("^OMXS30", period=period, interval="1d", auto_adjust=False, progress=False, threads=False)
    except Exception:
        benchmark_hist = pd.DataFrame()
    regime_hist = build_market_regime_history(benchmark_hist)
    regime_summary = summarize_backtest_by_regime(tech, regime_hist, score_col, threshold, horizon)
    if regime_summary.empty:
        st.info("Kunde inte bygga tillräcklig OMXS30-historik för regimtestet just nu.")
    else:
        display_regime = regime_summary.copy()
        display_regime["Träffsäkerhet %"] = (display_regime["win_rate"] * 100).round(1)
        display_regime["Baslinje %"] = (display_regime["baseline_win_rate"] * 100).round(1)
        display_regime["Median %"] = (display_regime["median_return"] * 100).round(2)
        display_regime["Median edge %"] = (display_regime["median_excess"] * 100).round(2)
        display_regime = display_regime.rename(columns={"regime":"Regim","signals":"Signaler","profit_factor":"Profit factor"})
        st.dataframe(display_regime[["Regim","Signaler","Träffsäkerhet %","Baslinje %","Median %","Median edge %","Profit factor"]], use_container_width=True, hide_index=True)
        enough = regime_summary[regime_summary["signals"] >= 20].copy()
        if not enough.empty:
            best_regime = enough.sort_values(["median_excess","win_rate"], ascending=False).iloc[0]
            worst_regime = enough.sort_values(["median_excess","win_rate"], ascending=True).iloc[0]
            st.info(f"Starkast historiskt i detta test: **{best_regime['regime']}** med median-edge {best_regime['median_excess']:+.2%}. Svagast: **{worst_regime['regime']}** med {worst_regime['median_excess']:+.2%}. Detta är diagnostik, inte ett bevis på framtida edge.")
        else:
            st.warning("För få signaler per regim för att jämförelsen ska vara robust.")

    st.divider()
    st.subheader("Walk-forward · fungerar signalen på osedd historik?")
    st.caption("Det här testet väljer scoretröskel enbart på en äldre träningsperiod och fryser sedan valet under nästa, osedda testperiod. Signaler som överlappar samma framtida utfallsfönster räknas inte som oberoende trades.")
    wf1, wf2, wf3 = st.columns(3)
    train_months = wf1.selectbox("Träningsfönster", [12, 18, 24, 36], index=2, format_func=lambda x: f"{x} månader", key="edge_wf_train")
    test_months = wf2.selectbox("Testfönster", [3, 6, 9, 12], index=1, format_func=lambda x: f"{x} månader", key="edge_wf_test")
    threshold_floor = wf3.slider("Lägsta tröskel att optimera", 40, 75, 50, 5, key="edge_wf_floor")
    threshold_grid = list(range(int(threshold_floor), 91, 5))
    wf = walk_forward_backtest(
        tech, score_col, threshold_grid, horizon,
        train_days=int(train_months * 21), test_days=int(test_months * 21),
        min_train_signals=8, min_test_signals=2,
    )
    if int(wf.get("folds", 0)) == 0:
        st.info("Historiken räcker inte till för vald walk-forward-konfiguration. Öka historiken eller korta tränings-/testfönstret.")
    elif int(wf.get("signals", 0)) == 0:
        st.warning("Walk-forward-testet kunde välja trösklar men hittade inga out-of-sample-signaler. Det är i sig ett tecken på att signalen är för selektiv eller instabil.")
    else:
        w1, w2, w3, w4, w5, w6 = st.columns(6)
        w1.metric("Testfönster", int(wf["folds"]))
        w2.metric("OOS-signaler", int(wf["signals"]))
        w3.metric("OOS träffsäkerhet", f"{wf['win_rate']:.1%}", f"vs {wf['baseline_win_rate']:.1%}")
        w4.metric("OOS median", f"{wf['median_return']:.2%}", f"edge {wf['median_excess']:+.2%}")
        w5.metric("Profit factor", f"{wf['profit_factor']:.2f}" if np.isfinite(wf['profit_factor']) else "—", help=beginner_term("profit factor"))
        w6.metric("Positiva testfönster", f"{wf['positive_fold_share']:.0%}" if np.isfinite(wf['positive_fold_share']) else "—")
        if wf["signals"] < 20 or int(wf.get("eligible_folds", 0)) < 3:
            st.warning("Out-of-sample-stickprovet är fortfarande tunt. Resultatet ska inte användas för att höja produktionsvikten ännu.")
        elif wf["median_excess"] > 0 and wf["win_rate"] > wf["baseline_win_rate"] and wf["positive_fold_share"] >= .60:
            st.success("Signalen har klarat ett första walk-forward-test: positiv median-edge, högre träffsäkerhet än baslinjen och positiv edge i en majoritet av de testfönster som hade tillräckligt med signaler. Det är ett robusthetstecken, inte ett löfte om framtida avkastning.")
        elif wf["median_excess"] <= 0 and wf["win_rate"] <= wf["baseline_win_rate"]:
            st.error("Signalen tappar sin edge på osedd historik. Det talar för överanpassning eller en för svag signal och är ett skäl att inte optimera produktionsmodellen mot fullhistorik-resultatet.")
        else:
            st.info("Walk-forward-resultatet är blandat. Strategin bör betraktas som oprövad tills fler out-of-sample-fönster visar samma beteende.")
        if float(wf.get("threshold_std", 0.0)) >= 10:
            st.warning(f"Den valda tröskeln är instabil mellan träningsfönstren (standardavvikelse {wf['threshold_std']:.1f} scorepoäng). Det är ett möjligt tecken på parameterkänslighet.")
        folds = wf.get("fold_table")
        if isinstance(folds, pd.DataFrame) and not folds.empty:
            st.markdown("#### Walk-forward per testfönster")
            fw = folds.copy()
            fw["OOS träff %"] = (fw["test_win_rate"] * 100).round(1)
            fw["Baslinje %"] = (fw["test_baseline_win_rate"] * 100).round(1)
            fw["OOS median %"] = (fw["test_median_return"] * 100).round(2)
            fw["OOS edge %"] = (fw["test_median_excess"] * 100).round(2)
            fw = fw.rename(columns={"test_start":"Test från","test_end":"Test till","threshold":"Vald tröskel","test_signals":"Signaler"})
            st.dataframe(fw[["Test från","Test till","Vald tröskel","Signaler","OOS träff %","Baslinje %","OOS median %","OOS edge %"]], use_container_width=True, hide_index=True)

        st.markdown("#### Handelsfriktion · överlever signalen verkliga kostnader?")
        st.caption("Stresstestet använder endast de out-of-sample-trades som walk-forward-testet faktiskt tog. Kostnader dras från varje trade före beräkning av nettoresultat. Det är fortfarande en förenklad sekventiell simulering – inte en full portföljmotor.")
        fc1, fc2, fc3 = st.columns(3)
        commission_bps = fc1.number_input("Courtage tur/retur (bps)", min_value=0.0, max_value=200.0, value=10.0, step=5.0, key="edge_cost_commission")
        execution_bps = fc2.number_input("Spread + slippage tur/retur (bps)", min_value=0.0, max_value=300.0, value=20.0, step=5.0, key="edge_cost_execution")
        position_pct = fc3.slider("Kapital per trade", 5, 100, 25, 5, key="edge_position_pct")
        friction = summarize_trading_friction(
            wf.get("trade_returns", []),
            roundtrip_cost_bps=float(commission_bps + execution_bps),
            position_fraction=float(position_pct) / 100.0,
        )
        if int(friction.get("trades", 0)) > 0:
            f1, f2, f3, f4, f5 = st.columns(5)
            f1.metric("Netto träffsäkerhet", f"{friction['net_win_rate']:.1%}")
            f2.metric("Netto median/trade", f"{friction['net_median_return']:.2%}", f"kostnad −{friction['cost_drag_per_trade']:.2%}")
            f3.metric("Netto profit factor", f"{friction['net_profit_factor']:.2f}" if np.isfinite(friction['net_profit_factor']) else "—")
            f4.metric("Sekventiell kapitalutveckling", f"{friction['compounded_return']:+.1%}")
            f5.metric("Max drawdown", f"{friction['max_drawdown']:.1%}", help=beginner_term("drawdown"))
            if friction["net_median_return"] <= 0 or (np.isfinite(friction["net_profit_factor"]) and friction["net_profit_factor"] < 1.0):
                st.error("Efter valda handelsfriktioner försvinner den ekonomiska edgen i detta walk-forward-test. Bruttoresultatet bör då inte användas som argument för att höja modellvikten.")
            elif friction["net_median_return"] > 0 and (not np.isfinite(friction["net_profit_factor"]) or friction["net_profit_factor"] >= 1.2):
                st.success("Signalen behåller positivt nettoresultat efter valda kostnader i detta out-of-sample-test. Det är ett bättre robusthetstecken än bruttoresultatet, men fortfarande inte ett live-validerat handelsresultat.")
            else:
                st.info("Signalen överlever kostnaderna, men marginalen är tunn. Små förändringar i spread, slippage eller exekvering kan fortfarande äta upp resultatet.")

    st.divider()
    st.subheader("Universumtest · fungerar signalen över många svenska aktier?")
    st.caption("Det här är ett hårdare test än en enda ticker. Samma tekniska signal körs över Sverige bred och jämförs med respektive akties normala framtida avkastning. Fundamenta används fortfarande inte historiskt.")
    uc1, uc2, uc3 = st.columns(3)
    uni_threshold = uc1.slider("Min score · universum", 40, 90, threshold, 5, key="edge_uni_threshold")
    uni_horizon = uc2.selectbox("Utfall · universum", [5, 10, 20], index=[5,10,20].index(horizon), format_func=lambda x: f"{x} börsdagar", key="edge_uni_horizon")
    uni_years = uc3.slider("Historik · universum", 2, 10, min(years, 5), key="edge_uni_years")
    max_symbols = st.slider("Antal aktier i universumtest", 10, min(81, len(load_universe_file())), min(50, len(load_universe_file())), 5, key="edge_uni_count")
    run_universe = st.button("Kör universumtest", type="primary", key="run_universe_edge")
    if run_universe:
        universe_df = load_universe_file().head(max_symbols)
        symbols = universe_df["Ticker"].dropna().astype(str).str.upper().tolist()
        period = f"{uni_years}y"
        with st.spinner(f"Testar {len(symbols)} aktier över {uni_years} års historik …"):
            try:
                bulk = yf.download(tickers=symbols, period=period, interval="1d", auto_adjust=False, actions=False, group_by="ticker", threads=True, progress=False)
            except Exception as exc:
                st.error(f"Kunde inte hämta universumhistorik: {exc}")
                bulk = pd.DataFrame()
            histories = {}
            if isinstance(bulk, pd.DataFrame) and not bulk.empty:
                if len(symbols) == 1:
                    histories[symbols[0]] = bulk.copy()
                elif isinstance(bulk.columns, pd.MultiIndex):
                    l0 = set(map(str, bulk.columns.get_level_values(0)))
                    l1 = set(map(str, bulk.columns.get_level_values(1)))
                    for sym in symbols:
                        try:
                            if sym in l0:
                                histories[sym] = bulk[sym].copy()
                            elif sym in l1:
                                histories[sym] = bulk.xs(sym, axis=1, level=1, drop_level=True).copy()
                        except Exception:
                            pass
            score_col_uni = "swing_proxy" if engine == "SWING" else "reversal_proxy"
            uni = summarize_universe_backtest(histories, score_col_uni, uni_threshold, uni_horizon)
        if int(uni.get("symbols_tested", 0)) == 0:
            st.warning("Universumtestet fick inte tillräcklig historik från datakällan.")
        else:
            q1, q2, q3, q4, q5, q6 = st.columns(6)
            q1.metric("Aktier testade", int(uni["symbols_tested"]))
            q2.metric("Signaler", int(uni["signals"]))
            q3.metric("Träffsäkerhet", f"{uni['win_rate']:.1%}", f"vs {uni['baseline_win_rate']:.1%}")
            q4.metric("Median", f"{uni['median_return']:.2%}", f"edge {uni['median_excess']:+.2%}")
            q5.metric("Profit factor", f"{uni['profit_factor']:.2f}" if np.isfinite(uni['profit_factor']) else "—")
            q6.metric("Aktier med positiv edge", f"{uni['positive_edge_share']:.0%}")
            if uni["signals"] < 100 or uni["symbols_with_signals"] < 10:
                st.warning("Stickprovet är fortfarande begränsat. Jag skulle inte ändra produktionsmodellen på detta resultat ensamt.")
            elif uni["median_excess"] > 0 and uni["win_rate"] > uni["baseline_win_rate"] and uni["positive_edge_share"] >= .55:
                st.success("Signalen visar bred positiv historisk edge i detta universumtest. Det är ett bättre tecken än ett bra resultat på en enskild aktie, men fortfarande inte ett komplett handelsbacktest.")
            elif uni["median_excess"] <= 0 and uni["win_rate"] <= uni["baseline_win_rate"]:
                st.error("Signalen misslyckas med att slå baslinjen brett. Det talar emot att ge den högre vikt i modellen utan omdesign.")
            else:
                st.info("Resultatet är blandat mellan aktier. Det tyder på att signalen kan vara regim- eller bolagsberoende snarare än robust över hela marknaden.")
            per_symbol = uni.get("per_symbol")
            if isinstance(per_symbol, pd.DataFrame) and not per_symbol.empty:
                st.markdown("#### Resultat per aktie")
                shown_uni = per_symbol.copy()
                shown_uni["Träffsäkerhet"] = (shown_uni["win_rate"] * 100).round(1)
                shown_uni["Baslinje %"] = (shown_uni["baseline_win_rate"] * 100).round(1)
                shown_uni["Median %"] = (shown_uni["median_return"] * 100).round(2)
                shown_uni["Median edge %"] = (shown_uni["median_excess"] * 100).round(2)
                shown_uni = shown_uni.rename(columns={"symbol":"Ticker","signals":"Signaler"})
                st.dataframe(shown_uni[["Ticker","Signaler","Träffsäkerhet","Baslinje %","Median %","Median edge %"]].sort_values(["Median edge %","Signaler"], ascending=[False,False]), use_container_width=True, hide_index=True)

            st.markdown("#### Portföljtest · flera samtidiga positioner")
            st.caption("Här behandlas signalerna som en faktisk gemensam kapitalpool. Borsify prioriterar högst score när flera signaler kommer samma dag, blockerar dubbla samtidiga positioner i samma aktie och binder kapital tills den valda horisonten löper ut. Equity-kurvan mark-to-market-värderar varje öppen position dagligen med historisk stängningskurs, så drawdown och exponering även fångar rörelser mellan in- och utgång.")
            pc1, pc2, pc3, pc4 = st.columns(4)
            portfolio_max_positions = pc1.slider("Max samtidiga positioner", 1, 15, 5, 1, key="edge_portfolio_max_positions")
            portfolio_position_pct = pc2.slider("Max allokering per position", 5, 100, 20, 5, key="edge_portfolio_position_pct")
            portfolio_commission = pc3.number_input("Portfölj · courtage t/r (bps)", min_value=0.0, max_value=200.0, value=10.0, step=5.0, key="edge_portfolio_commission")
            portfolio_execution = pc4.number_input("Portfölj · spread/slippage t/r (bps)", min_value=0.0, max_value=300.0, value=20.0, step=5.0, key="edge_portfolio_execution")

            use_risk_sizing = st.toggle("Riskstyrd positionsstorlek + ATR-stop", value=True, key="edge_portfolio_risk_sizing")
            risk_per_trade = 1.0
            max_portfolio_risk = 5.0
            atr_stop_multiple = 2.0
            if use_risk_sizing:
                rc1, rc2, rc3 = st.columns(3)
                risk_per_trade = rc1.slider("Risk per trade (% av kapital)", 0.25, 5.0, 1.0, 0.25, key="edge_portfolio_risk_per_trade")
                max_portfolio_risk = rc2.slider("Max total öppen risk (%)", 1.0, 20.0, 5.0, 0.5, key="edge_portfolio_max_risk")
                atr_stop_multiple = rc3.slider("ATR-multipel för stop", 0.5, 5.0, 2.0, 0.25, key="edge_portfolio_atr_stop")
                st.caption("Positionsstorleken begränsas av både maxallokeringen och vald risk per trade. Stop-avståndet baseras på trailing ATR och klampas till 2–15 %. Modellen antar stop-fill på stopnivån; gap-through och verklig orderfyllnad kan ge sämre utfall i verkligheten.")

            portfolio = simulate_portfolio_backtest(
                histories,
                score_col_uni,
                uni_threshold,
                uni_horizon,
                max_positions=portfolio_max_positions,
                position_fraction=float(portfolio_position_pct) / 100.0,
                roundtrip_cost_bps=float(portfolio_commission + portfolio_execution),
                use_risk_sizing=use_risk_sizing,
                risk_per_trade=float(risk_per_trade) / 100.0,
                max_portfolio_risk=float(max_portfolio_risk) / 100.0,
                atr_stop_multiple=float(atr_stop_multiple),
            )
            if int(portfolio.get("trades", 0)) == 0:
                st.info("Portföljtestet fick inga genomförbara trades med nuvarande signaltröskel och historik.")
            else:
                pp1, pp2, pp3, pp4, pp5, pp6 = st.columns(6)
                pp1.metric("Trades", int(portfolio["trades"]), f"{int(portfolio.get('symbols_traded', 0))} aktier")
                pp2.metric("Netto träffsäkerhet", f"{portfolio['win_rate']:.1%}")
                pp3.metric("Total kapitalutveckling", f"{portfolio['total_return']:+.1%}")
                pp4.metric("Daglig max drawdown", f"{portfolio['max_drawdown']:.1%}", help=beginner_term("drawdown"))
                pp5.metric("Snittexponering", f"{portfolio['avg_exposure']:.0%}")
                pp6.metric("Profit factor", f"{portfolio['profit_factor']:.2f}" if np.isfinite(portfolio['profit_factor']) else "—", help=beginner_term("profit factor"))
                if use_risk_sizing:
                    rr1, rr2, rr3 = st.columns(3)
                    rr1.metric("Max risk vid nyöppning", f"{portfolio.get('max_entry_risk', 0.0):.1%}")
                    rr2.metric("Max risk / MTM-kapital", f"{portfolio.get('max_open_risk', 0.0):.1%}", help="Kan stiga över valt risktak efter att portföljen fallit. Risktaket används när nya positioner öppnas; backtestet tvångsminskar inte redan öppna positioner.")
                    rr3.metric("Nekade av risktak", int(portfolio.get("rejected_risk", 0)))
                    st.caption(f"Stop-andel: {portfolio.get('stop_rate', 0.0):.1%}. Risktaket kontrolleras vid entry. Därefter kan stop-risk som andel av aktuell MTM-equity förändras när marknaden rör sig.")

                eq = portfolio.get("equity_curve")
                if isinstance(eq, pd.DataFrame) and not eq.empty:
                    chart = eq[["equity"]].rename(columns={"equity": "Kapitalindex (MTM)"}) * 100
                    st.line_chart(chart, use_container_width=True)
                    st.caption("Kapitalindexet värderar öppna innehav med respektive dags stängningskurs. Full t/r-friktion bokförs när traden stängs; framtida exitkostnad periodiseras inte i den öppna MTM-kurvan.")
                    exposure_cols = ["exposure"] + (["open_risk"] if "open_risk" in eq.columns else [])
                    exposure_chart = eq[exposure_cols].rename(columns={"exposure": "Exponering", "open_risk": "Öppen stop-risk"}) * 100
                    st.area_chart(exposure_chart, use_container_width=True)

                    st.markdown("#### Borsify mot OMXS30 · samma tidsperiod")
                    try:
                        bench_raw = yf.download("^OMXS30", start=pd.Timestamp(eq.index.min()).date().isoformat(), end=(pd.Timestamp(eq.index.max()) + pd.Timedelta(days=2)).date().isoformat(), interval="1d", auto_adjust=False, progress=False, threads=False)
                    except Exception:
                        bench_raw = pd.DataFrame()
                    bench_close = _download_close_series(bench_raw, "^OMXS30")
                    if not bench_close.empty:
                        compare_index = pd.DatetimeIndex(pd.to_datetime(eq.index)).tz_localize(None)
                        bench_aligned = bench_close.reindex(compare_index).ffill().bfill()
                        if bench_aligned.notna().sum() >= 2 and _num(bench_aligned.iloc[0]) > 0:
                            bq_index = pd.to_numeric(eq["equity"], errors="coerce") / _num(eq["equity"].iloc[0]) * 100
                            omx_index = bench_aligned / _num(bench_aligned.iloc[0]) * 100
                            comparison = pd.DataFrame({"Borsify": bq_index.values, "OMXS30": omx_index.values}, index=compare_index)
                            st.line_chart(comparison, use_container_width=True)
                            bq_stats = _performance_stats(pd.Series(bq_index.values, index=compare_index))
                            omx_stats = _performance_stats(pd.Series(omx_index.values, index=compare_index))
                            bm1, bm2, bm3, bm4 = st.columns(4)
                            bm1.metric("Borsify total", f"{bq_stats['return']:+.1%}" if np.isfinite(bq_stats['return']) else "—", f"OMXS30 {omx_stats['return']:+.1%}" if np.isfinite(omx_stats['return']) else None)
                            bm2.metric("Årstakt (CAGR)", f"{bq_stats['cagr']:+.1%}" if np.isfinite(bq_stats['cagr']) else "—", f"OMXS30 {omx_stats['cagr']:+.1%}" if np.isfinite(omx_stats['cagr']) else None, help="Ungefär vilken årlig tillväxttakt som skulle ge samma totalresultat över perioden.")
                            bm3.metric("Max fall från topp", f"{bq_stats['max_drawdown']:.1%}" if np.isfinite(bq_stats['max_drawdown']) else "—", f"OMXS30 {omx_stats['max_drawdown']:.1%}" if np.isfinite(omx_stats['max_drawdown']) else None, help=beginner_term("drawdown"))
                            bm4.metric("Riskjusterad kvot", f"{bq_stats['sharpe']:.2f}" if np.isfinite(bq_stats['sharpe']) else "—", f"OMXS30 {omx_stats['sharpe']:.2f}" if np.isfinite(omx_stats['sharpe']) else None, help=beginner_term("Sharpe"))
                            excess = bq_stats["return"] - omx_stats["return"] if np.isfinite(bq_stats["return"]) and np.isfinite(omx_stats["return"]) else np.nan
                            if np.isfinite(excess):
                                if excess > .02:
                                    st.success(f"Enkelt uttryckt: i den här historiska simuleringen slog Borsify OMXS30 med cirka {excess:+.1%} totalt. Kontrollera också drawdown och riskjusterad kvot – högre avkastning är mindre imponerande om vägen dit varit mycket mer riskfylld.")
                                elif excess < -.02:
                                    st.warning(f"Enkelt uttryckt: i den här historiska simuleringen gav Borsify cirka {abs(excess):.1%} sämre total avkastning än OMXS30. Då hade ett enkelt indexalternativ varit bättre under samma period.")
                                else:
                                    st.info("Enkelt uttryckt: Borsify och OMXS30 gav ungefär samma totalresultat i den här perioden. Då blir risk, drawdown och handelskostnader extra viktiga i jämförelsen.")
                            st.caption("Jämförelsen normaliserar båda till 100 vid start. OMXS30 är ett jämförelseindex, inte ett investerbart totalavkastningsindex här; utdelningar i indexet kan därför göra jämförelsen ofullständig.")
                    else:
                        st.info("OMXS30-data kunde inte hämtas för exakt samma period, så benchmarkjämförelsen visas inte i denna körning.")

                rejected = int(portfolio.get("rejected_capacity", 0))
                if rejected > 0:
                    st.caption(f"{rejected} signaler kunde inte öppnas eftersom portföljen redan var full eller saknade ledigt kapital. Det är avsiktligt: universumsignaler får inte låtsas använda samma kapital flera gånger samtidigt.")
                if portfolio["total_return"] <= 0 or (np.isfinite(portfolio["profit_factor"]) and portfolio["profit_factor"] < 1.0):
                    st.error("När signalerna konkurrerar om samma kapitalpool håller strategin inte ihop med dessa antaganden. Ett bra signaltest är alltså inte tillräckligt för att motivera modellen.")
                elif portfolio["max_drawdown"] <= -.25:
                    st.warning("Portföljen är historiskt lönsam i denna simulering men drawdown är hög. Riskkontroll och positionsstorlek behöver förbättras innan resultatet kan betraktas som robust.")
                else:
                    st.success("Strategin behåller positivt resultat när samtidiga positioner och kapitalbindning modelleras. Det är ett starkare diagnostiskt test, men fortfarande inte live-validerad avkastning.")

                trades = portfolio.get("trade_log")
                if isinstance(trades, pd.DataFrame) and not trades.empty:
                    with st.expander("Visa portföljens trade-logg"):
                        shown_trades = trades.copy()
                        shown_trades["entry_date"] = pd.to_datetime(shown_trades["entry_date"]).dt.strftime("%Y-%m-%d")
                        shown_trades["exit_date"] = pd.to_datetime(shown_trades["exit_date"]).dt.strftime("%Y-%m-%d")
                        shown_trades["score"] = shown_trades["score"].round(1)
                        shown_trades["gross_return"] = (shown_trades["gross_return"] * 100).round(2)
                        shown_trades["net_return"] = (shown_trades["net_return"] * 100).round(2)
                        shown_trades["pnl"] = shown_trades["pnl"].round(4)
                        if "stop_pct" in shown_trades.columns:
                            shown_trades["stop_pct"] = (shown_trades["stop_pct"] * 100).round(2)
                        shown_trades = shown_trades.rename(columns={"symbol":"Ticker","entry_date":"In","exit_date":"Ut","score":"Score","gross_return":"Brutto %","net_return":"Netto %","capital":"Kapitalandel","pnl":"P/L","stop_pct":"Stop %","stopped":"Stoppad"})
                        trade_cols = ["Ticker","In","Ut","Score","Brutto %","Netto %","Kapitalandel"]
                        if "Stop %" in shown_trades.columns: trade_cols += ["Stop %","Stoppad"]
                        trade_cols += ["P/L"]
                        st.dataframe(shown_trades[trade_cols], use_container_width=True, hide_index=True)

            st.markdown("#### Universumtest uppdelat på marknadsregim")
            try:
                benchmark_uni = yf.download("^OMXS30", period=period, interval="1d", auto_adjust=False, progress=False, threads=False)
            except Exception:
                benchmark_uni = pd.DataFrame()
            regime_uni_hist = build_market_regime_history(benchmark_uni)
            regime_uni = summarize_universe_backtest_by_regime(histories, regime_uni_hist, score_col_uni, uni_threshold, uni_horizon)
            if regime_uni.empty:
                st.info("Ingen tillräcklig regimdata kunde byggas för universumtestet.")
            else:
                ru = regime_uni.copy()
                ru["Träffsäkerhet %"] = (ru["win_rate"] * 100).round(1)
                ru["Baslinje %"] = (ru["baseline_win_rate"] * 100).round(1)
                ru["Median %"] = (ru["median_return"] * 100).round(2)
                ru["Median edge %"] = (ru["median_excess"] * 100).round(2)
                ru = ru.rename(columns={"regime":"Regim","symbols_with_signals":"Aktier","signals":"Signaler","profit_factor":"Profit factor"})
                st.dataframe(ru[["Regim","Aktier","Signaler","Träffsäkerhet %","Baslinje %","Median %","Median edge %","Profit factor"]], use_container_width=True, hide_index=True)
                robust = regime_uni[(regime_uni["signals"] >= 100) & (regime_uni["symbols_with_signals"] >= 10)]
                if len(robust) >= 2:
                    spread = float(robust["median_excess"].max() - robust["median_excess"].min())
                    if spread >= .02:
                        st.warning("Signalen är tydligt regimberoende i universumtestet. Det talar för att Borsify senare bör justera SWING/REVERSAL-kraven efter marknadsläget i stället för att använda samma tröskel hela tiden.")
                    else:
                        st.success("Signalen ser relativt stabil ut mellan de regimer som har tillräckligt stort stickprov. Det är ett positivt robusthetstecken, men handelsfriktioner och walk-forward-test återstår.")


def main() -> None:
    st.set_page_config(page_title=f"{APP_NAME} · Dagens fynd", page_icon="◈", layout="wide")
    st.markdown("""
    <style>
    .block-container{padding-top:1.35rem;padding-bottom:3rem;max-width:1480px}
    /* Theme-safe KPI cards: use Streamlit theme variables instead of fixed light colors. */
    [data-testid="stMetric"]{background:var(--secondary-background-color);border:1px solid color-mix(in srgb,var(--text-color) 16%,transparent);padding:12px 14px;border-radius:14px;color:var(--text-color)}
    [data-testid="stMetric"] [data-testid="stMetricLabel"],
    [data-testid="stMetric"] [data-testid="stMetricLabel"] *{color:var(--text-color) !important;opacity:.72}
    [data-testid="stMetric"] [data-testid="stMetricValue"],
    [data-testid="stMetric"] [data-testid="stMetricValue"] *{color:var(--text-color) !important;opacity:1}
    [data-testid="stMetric"] [data-testid="stMetricDelta"],
    [data-testid="stMetric"] [data-testid="stMetricDelta"] *{opacity:1}
    [data-testid="stMetric"] svg{fill:currentColor}
    .bq-hero{padding:22px 24px;border-radius:18px;background:linear-gradient(135deg,#0f172a,#1e293b);color:white;margin-bottom:14px}
    .bq-mark{display:inline-flex;width:42px;height:42px;border-radius:12px;align-items:center;justify-content:center;background:#22c55e;color:#07130b;font-weight:900;margin-right:10px}
    .bq-title{font-size:2rem;font-weight:800;letter-spacing:-.03em}.bq-sub{color:#cbd5e1;margin-top:5px}.bq-domain{color:#86efac;font-weight:700}
    .small-muted{color:#64748b;font-size:.9rem}
    .bq-status{display:flex;justify-content:space-between;gap:18px;padding:9px 0;border-bottom:1px solid rgba(148,163,184,.32);color:inherit}.bq-status span{opacity:.72}.bq-status strong{color:inherit}
    div[data-testid="stTabs"] button{font-weight:650}
    @media (max-width: 700px){
      .block-container{padding-top:.65rem;padding-left:.75rem;padding-right:.75rem}
      .bq-hero{padding:16px;border-radius:14px}.bq-title{font-size:1.55rem}.bq-sub{font-size:.82rem}
      [data-testid="stMetric"]{padding:9px 10px;border-radius:11px;min-height:84px}
      [data-testid="stMetric"] [data-testid="stMetricValue"]{font-size:1.15rem}
      div[data-testid="stHorizontalBlock"]{gap:.55rem}
      .stDataFrame{font-size:.82rem}
    }
    </style>
    """, unsafe_allow_html=True)
    st.markdown(f"""<div class='bq-hero'><div><span class='bq-mark'>BQ</span><span class='bq-title'>{APP_NAME}</span></div><div class='bq-sub'>Hitta intressanta aktier — och förstå varför · <span class='bq-domain'>{APP_DOMAIN}</span></div></div>""", unsafe_allow_html=True)

    require_site_access()
    init_db()
    universe_df = load_universe_file()
    file_universe_symbols = universe_df["Ticker"].tolist()

    with st.sidebar:
        st.header("Hitta aktier")
        st.markdown("### Vad letar du efter?")
        discovery_intent = st.selectbox(
            "Mitt mål", DISCOVERY_INTENTS, index=0,
            help="Välj med vanliga ord. Borsify översätter målet till en ranking bakom kulisserna.",
        )
        st.caption(intent_plain_text(discovery_intent))

        universe = st.radio("Universum", ["OMXS30", "Sverige bred", "Egen lista"], index=1)
        custom = st.text_area("Tickers", value="INVE-B.ST, VOLV-B.ST, SAND.ST, EVO.ST", height=100) if universe == "Egen lista" else ""
        if universe == "Sverige bred":
            st.caption(f"{len(file_universe_symbols)} svenska aktier i nuvarande universum.")

        with st.expander("Fler filter", expanded=False):
            profile = st.selectbox("Borsify-strategi", list(PROFILE_WEIGHTS), index=0, help="Påverkar grundscoren. Om du är osäker kan Balanserad vara kvar.")
            min_market_cap = st.number_input("Min börsvärde (mdr SEK)", 0.0, value=5.0, step=1.0)
            min_turnover = st.number_input("Min omsättning/dag (MSEK)", 0.0, value=5.0, step=1.0)
            require_positive = st.checkbox("Kräv positiv P/E", value=True)
            dividend_only = st.checkbox(
                "Bara aktier med direktavkastning",
                value=False,
                help="Visar bara bolag där datakällan just nu registrerar en positiv direktavkastning.",
            )
            min_dividend_yield = st.number_input(
                "Min direktavkastning (%)", 0.0, 20.0, value=0.0, step=0.5,
                disabled=not dividend_only,
                help="Exempel: 3 betyder minst cirka 3 % direktavkastning enligt aktuell data. Utdelningar kan ändras eller slopas.",
            )
            allow_missing_filter_data = st.checkbox("Tillåt saknade filtervärden", value=False)
            top_n = st.slider("Visa topp", 3, 20, 10)

        refresh = st.button("Uppdatera marknadsdata", type="primary", use_container_width=True)
        st.caption("Kurser cachas 15 min · fundamenta 6 h.")

        with st.expander("Konto", expanded=False):
            if cloud_enabled():
                user = current_user()
                if user is None:
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
                else:
                    st.success(f"Inloggad som {getattr(user, 'email', '')}")
                    if st.button("Logga ut", use_container_width=True):
                        auth_sign_out(); st.rerun()
                    st.caption("Bevakning och scorehistorik sparas i molnet.")
            else:
                st.caption("Lokalt läge · konfigurera Supabase för konto och molnsynk.")
    symbols = OMXS30_TICKERS if universe == "OMXS30" else (file_universe_symbols if universe == "Sverige bred" else parse_symbols(custom))
    if refresh: st.cache_data.clear()
    if not symbols: st.warning("Ange minst en ticker."); st.stop()
    start = time.perf_counter()
    with st.spinner(f"Borsify analyserar {len(symbols)} aktier…"):
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
    if dividend_only:
        dy = pd.to_numeric(filtered["Direktavkastning"], errors="coerce")
        min_yield = float(min_dividend_yield) / 100.0
        filtered = filtered[dy.notna() & (dy > 0) & (dy >= min_yield)]
    filtered = apply_discovery_intent(filtered, discovery_intent)
    top = filtered.head(top_n).copy(); daily_shortlist = build_daily_shortlist(filtered, profile, limit=min(5, len(filtered))); idx = fetch_index_snapshot(); elapsed = time.perf_counter() - start

    price_dates = sorted({str(x) for x in raw_df.get("Prisdatum", pd.Series(dtype=str)).dropna().tolist() if str(x) != "—"})
    latest_price_date = price_dates[-1] if price_dates else "—"
    market_note = f" · OMXS30 {idx['index']:.0f} ({fmt_pct(idx.get('daily'))})" if idx else ""
    st.caption(f"{len(raw_df)} aktier analyserade · {len(filtered)} kvar efter dina val · kursdata {latest_price_date}{market_note}")
    if errors:
        with st.expander(f"Datakällan saknade {len(errors)} ticker(s) — övriga analyserades"):
            st.caption("Detta beror oftast på tillfälliga Yahoo-problem, ändrad ticker eller otillräcklig kurshistorik. Det påverkar inte aktier som redan har lästs in.")
            for error in errors:
                st.write(f"• {error}")
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

    nav_overview, nav_discover, nav_watch, nav_analyse, nav_method = st.tabs([
        "Överblick", "Upptäck", f"Bevakning ({len(watch_df_global)})", "Analysera", "Metod"
    ])
    with nav_overview:
        render_overview(daily_shortlist, filtered, scored, watch_df_global, signal_history_global, unread_signals, profile, idx, elapsed, latest_price_date)
    with nav_discover:
        discover_daily, discover_ideas, discover_radar = st.tabs(["Dagens fynd", "Idéflöde", f"Radar ({unread_signals})"])
        with discover_daily:
            st.info(f"Du letar efter: **{discovery_intent}**. {intent_plain_text(discovery_intent)}")
            render_discovery_shortlist(filtered, discovery_intent)
            st.divider()
            if discovery_intent in {"Bra långsiktig investering", "Billiga kvalitetsbolag", "Bästa möjligheter just nu"}:
                render_quality_at_fair_price(filtered)
                st.divider()
            if discovery_intent == "Utdelningsaktier" or dividend_only:
                render_dividend_discovery(filtered)
                st.divider()
            render_engine_board(filtered)
            st.divider()
            st.subheader("Dagens fynd · snabbaste beslutsunderlaget")
            st.caption("Dagens relevans är en separat triage ovanpå Borsify Score. Den väger in aktuellt marknadsläge och scoreförändring, och kan begränsas av grova riskflaggor. Den är inte ett köp- eller säljråd.")
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
                        h1, h2, h3, h4, h5 = st.columns([3.0, 1, 1.15, 1, 1])
                        h1.markdown(f"### {rank}. {case['Namn']} · {case['Ticker']}")
                        h1.caption(f"{case['Signal']} · {case['Sektor']} · senaste kursdag {case.get('Prisdatum','—')}")
                        delta = _num(case.get("Score Δ"))
                        h2.metric("Borsify", f"{_num(case['Borsify Score']):.0f}/100", f"{delta:+.1f}" if np.isfinite(delta) else None)
                        case_price = _num(case.get("Pris"))
                        h3.metric("Aktuell kurs", f"{case_price:.2f} {case.get('Valuta', '')}" if np.isfinite(case_price) else "—", fmt_pct(case.get("Dagsförändring")))
                        h4.metric("Dagens relevans", f"{_num(case['Dagens relevans']):.0f}/100")
                        h5.metric("Prioritet", str(case["Prioritet"]))
                        c1, c2, c3 = st.columns(3)
                        c1.markdown("**Varför idag**")
                        c1.write(str(case["Varför idag"]))
                        c2.markdown("**Vad har förändrats**")
                        c2.write(str(case["Förändrat"]))
                        c3.markdown("**Kontrollera innan du går vidare**")
                        c3.write(str(case["Kontrollera"]))

                st.divider()
                st.subheader("Jämför dagens kortlista")
                quick_cols = ["Ticker", "Namn", "Pris", "Valuta", "Dagsförändring", "Prisdatum", "Borsify Score", "INVEST Score", "SWING Score", "REVERSAL Score", "Dagens relevans", "Prioritet", "Score Δ", "Värdering", "Kvalitet", "Marknadsläge", "Risk", "Riskflaggor"]
                quick = daily_shortlist[quick_cols].copy()
                st.dataframe(quick, use_container_width=True, hide_index=True, column_config={
                    "Borsify Score": st.column_config.ProgressColumn("Borsify", min_value=0, max_value=100, format="%.0f"),
                    "Dagens relevans": st.column_config.ProgressColumn("Dagens relevans", min_value=0, max_value=100, format="%.0f"),
                    "Score Δ": st.column_config.NumberColumn("Score Δ", format="%+.1f"),
                    "Värdering": st.column_config.ProgressColumn("Värdering", min_value=0, max_value=100, format="%.0f"),
                    "Kvalitet": st.column_config.ProgressColumn("Kvalitet", min_value=0, max_value=100, format="%.0f"),
                    "Marknadsläge": st.column_config.ProgressColumn("Setup", min_value=0, max_value=100, format="%.0f"),
                    "Risk": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100, format="%.0f"),
                })

            st.divider(); st.subheader("Topplista enligt ditt val")
            display = dataframe_for_display(top)
            st.dataframe(display, use_container_width=True, hide_index=True, column_config={
                "Match Score": st.column_config.ProgressColumn("Match", min_value=0, max_value=100, format="%.0f"),
                "Borsify Score": st.column_config.ProgressColumn("Borsify Score", min_value=0, max_value=100, format="%.0f"),
                "Pris": st.column_config.NumberColumn("Pris", format="%.2f"), "Dagsförändring": st.column_config.NumberColumn("Idag", format="%.2f%%"),
                "P/E": st.column_config.NumberColumn("P/E", format="%.1f"), "Direktavkastning": st.column_config.NumberColumn("DA", format="%.1f%%"),
                "52v från topp": st.column_config.NumberColumn("Från 52v-topp", format="%.1f%%"), "RSI14": st.column_config.NumberColumn("RSI", format="%.0f"),
                "Värdering": st.column_config.ProgressColumn("Värdering", min_value=0, max_value=100, format="%.0f"), "Kvalitet": st.column_config.ProgressColumn("Kvalitet", min_value=0, max_value=100, format="%.0f"),
                "Marknadsläge": st.column_config.ProgressColumn("Setup", min_value=0, max_value=100, format="%.0f"), "Risk": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100, format="%.0f"),
            })
            st.download_button("Ladda ner topplistan som CSV", data=display.to_csv(index=False).encode("utf-8-sig"), file_name=f"borsify_{datetime.now():%Y-%m-%d}.csv", mime="text/csv")
            st.divider(); st.subheader("Detaljanalys")
            choices = {f"{r['Ticker']} · {r['Namn']} · {r['Borsify Score']:.0f}/100": i for i,r in top.iterrows()}
            selected = st.selectbox("Välj aktie", list(choices)); render_detail(top.loc[choices[selected]], profile, key_prefix="daily")
        with discover_ideas:
            render_idea_flow(scored)

        with discover_radar:
            st.subheader("Borsify Radar · dagens förändringar")
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

    with nav_watch:
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
                watch_display.insert(4, "Score Δ", [score_change(str(r["Ticker"]), profile, float(r["Borsify Score"])) for _, r in watch_df.iterrows()])
                st.dataframe(watch_display, use_container_width=True, hide_index=True, column_config={"Score Δ": st.column_config.NumberColumn("Score Δ", format="%+.1f")})
                st.download_button("Exportera bevakningslista", data="Ticker\n" + "\n".join(watched), file_name="borsify_bevakning.csv", mime="text/csv")

            st.markdown("#### Varför bevakar jag den? · intressepris och signaler")
            st.caption("Skriv med egna ord varför du följer aktien. Borsify visar samtidigt sitt eget skäl så att du senare kan se om caset har förändrats.")
            for _, meta in watch_meta.iterrows():
                sym = str(meta["symbol"])
                current_note = str(meta.get("note") or "")
                current_target = _num(meta.get("target_price"))
                with st.expander(sym, expanded=False):
                    current_row = watch_df_global[watch_df_global["Ticker"].astype(str) == sym].head(1) if not watch_df_global.empty else pd.DataFrame()
                    if not current_row.empty:
                        wr = current_row.iloc[0]
                        st.markdown(f"**Borsifys skäl just nu:** {wr.get('Varför','—')}")
                        cp = _num(wr.get("Pris"))
                        if np.isfinite(cp): st.caption(f"Aktuell hämtad kurs: {cp:.2f} {wr.get('Valuta','')} · kursdag {wr.get('Prisdatum','—')}")
                    note = st.text_area("Min anledning att bevaka", value=current_note, key=f"note_{sym}", placeholder="Exempel: Bra bolag men jag vill vänta på lägre pris.")
                    target = st.number_input(
                        "Mitt intressepris (0 = inget)", min_value=0.0, value=float(current_target) if np.isfinite(current_target) and current_target > 0 else 0.0, step=1.0, key=f"target_{sym}"
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
    with nav_analyse:
        analyse_market, analyse_edge = st.tabs(["Marknad", "Edge Lab"])
        with analyse_market:
            st.subheader("Marknad · hela analysuniversumet")
            st.caption("Här finns rålistan för jämförelser och egen analys. Överblick och Dagens fynd är de rekommenderade startpunkterna.")
            st.dataframe(dataframe_for_display(scored), use_container_width=True, hide_index=True)
        with analyse_edge:
            default_edge_symbol = str(filtered.iloc[0]["Ticker"]) if not filtered.empty else "INVE-B.ST"
            render_edge_lab(default_edge_symbol)
    with nav_method:
        w = PROFILE_WEIGHTS[profile]
        st.subheader("Så räknas Borsify Score")
        with st.expander("Risk på vanlig svenska · det viktigaste före ett köp", expanded=False):
            st.markdown(f"""
- **Volatilitet:** {beginner_term('volatilitet')}.
- **Likviditet:** {beginner_term('likviditet')}.
- **Stop-loss:** {beginner_term('stop-loss')}.
- **Diversifiering:** {beginner_term('diversifiering')}.
- **Hävstång:** {beginner_term('hävstång')}. Borsify fokuserar i första hand på vanliga aktier och uppmuntrar inte användaren att ta hävstång för att förstora en signal.

Borsify försöker därför visa både **varför något ser intressant ut** och **vad som kan gå fel**. Ett högt score är ett analysurval, inte en garanti.
""")
        st.markdown(f"""
    **Vald strategi: {profile}.** Vikter: värdering {w['valuation']:.0%}, kvalitet {w['quality']:.0%}, marknadsläge {w['setup']:.0%}, utdelning {w['income']:.0%}, risk {w['risk']:.0%}.

    **Värdering** jämför P/E, forward P/E, P/B, EV/EBITDA och FCF-yield i första hand relativt andra bolag i samma sektor när underlaget är tillräckligt. Det minskar problemet att exempelvis bank och industri behandlas som identiska.

    **Kvalitet** försöker svara på: ”Är det här ett välskött och lönsamt bolag?” Den väger bland annat ROE (hur effektivt bolaget använder ägarnas pengar), marginaler, tillväxt och skuld. **Marknadsläge** försöker svara på: ”Är kursläget intressant just nu?” och använder bland annat RSI och 200-dagarssnittet. **Utdelning** tittar både på direktavkastningen och hur stor del av vinsten som går till utdelning. **Risk** drar ned bolag med exempelvis förluster, hög skuld eller en tydligt fallande kursutveckling.

    Aktier med låg datatäckning får en försiktig rabatt. En hög score är en prioriteringssignal för vidare analys, inte en prognos om framtida avkastning.

    **Bevakningssignaler** jämför aktuell körning med tidigare dagssnapshots, din målkurs och dina egna tröskelvärden per aktie. Signalhistorik sparas med läst/oläst-status. Inloggade användare kan välja vilka signaltyper som ska skickas som e-post efter den schemalagda scanningen. De är regelbaserade informationshändelser, inte automatiska affärsförslag.
    """)

    st.caption("Konton/molnsynk: Supabase när konfigurerat. Datakälla: Yahoo Finance via yfinance. Sverige bred läses från universe.csv och är inte garanterat en officiell komplett Nasdaq-lista. Kontrollera alltid rapporter, nyheter, kassaflöde, skuldsättning och bolagsspecifika händelser före investeringsbeslut.")



if __name__ == "__main__":
    main()
