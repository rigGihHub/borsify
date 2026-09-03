from __future__ import annotations

import math
import re
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
from fx import FX_TO_SEK_SYMBOLS, major_currency, quote_amount_to_sek, major_amount_to_sek
from case_journal import assess_case_change, journal_table
from case_breaker import evaluate_case_breakers
from case_alert import evaluate_case_alert
from daily_focus import build_daily_focus, focus_context
from since_last_visit import build_since_last_visit, visit_label
from deep_case_engine import build_deep_metrics, assess_deep_case, deep_rank_key
from earnings_quality import build_earnings_quality_metrics, assess_earnings_quality, apply_earnings_quality_gate
from data_trust import add_data_trust
from fundamental_cache import get_cached_fundamentals, put_cached_fundamentals, CACHE_MAX_AGE_HOURS
from scan_pipeline import assess_price_history
from staged_scan_validation import validate_candidate_pool, activation_readiness
from prefilter_history import save_prefilter_validation, get_prefilter_validation_history
from inflection_engine import build_inflection_metrics, assess_inflection, apply_inflection_gate, inflection_rank_value
from mispricing_engine import build_mispricing_assessment, apply_mispricing_gate, mispricing_rank_value
from scenario_engine import build_scenarios
from case_quality_gate import build_case_quality_gate, case_gate_rank_key
from catalyst_engine import build_catalyst_assessment
from short_term_engine import assess_short_term_case, short_term_rank_key
from short_edge_lab import (
    build_point_in_time_short_signals, add_forward_returns, evaluate_thresholds,
    walk_forward_threshold_test, component_bucket_analysis, summarize_edge,
)
from daytrade_validation import (
    build_point_in_time_daytrade, evaluate_daytrade, walk_forward_fixed_gate,
    validation_grade, compare_horizons,
)
from daytrade_universe_validation import (
    split_downloaded_histories, validate_universe, universe_validation_label,
)
from recommendation_ledger import (
    build_recommendation_records, evaluate_record_from_history,
    outcome_summary, calibration_by_gate,
)
from recommendation_relevance import apply_recommendation_relevance
from recommendation_learning import (
    learning_summary, learning_tables, score_band_monotonicity, data_limits_note,
    MIN_COHORT,
)
from case_plan import apply_case_plans
from horizon_rankings import top_three, add_horizon_scores
from near_buy import near_buy_candidates
from portfolio_advisor import assess_holding
from market_universe import load_avanza_universe, universe_symbols, coverage_table, breadth_summary
from universe_quality import apply_universe_quality, filter_rankable_universe, quality_summary
from qc_history import evolve_qc_state, is_quarantined, scan_health, quarantine_summary, should_record_qc_outcome
from case_ai import build_case_ai_input, build_case_ai_instructions, local_case_explanation
from ai_cost import token_usage, estimate_usage_cost, format_cost_usd

from edge_lab import (
    build_technical_history, summarize_backtest, summarize_universe_backtest,
    build_market_regime_history, summarize_backtest_by_regime, summarize_universe_backtest_by_regime,
    walk_forward_backtest, summarize_trading_friction, simulate_portfolio_backtest,
)

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore

try:
    from supabase import Client, create_client
except Exception:
    Client = Any  # type: ignore
    create_client = None

APP_VERSION = "2.66.0"
APP_NAME = "Borsify"
APP_DOMAIN = "borsify.se"
APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "borsify.db"
UNIVERSE_PATH = APP_DIR / "universe.csv"
AVANZA_UNIVERSE_PATH = APP_DIR / "avanza_universe.csv"

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

# Kuraterade startuniversum för utländska marknader. Fokus ligger på stora och
# relativt likvida bolag för att hålla första internationella versionen robust.
US_LARGE_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "LLY", "AVGO", "JPM",
    "V", "MA", "XOM", "COST", "WMT", "NFLX", "ORCL", "JNJ", "PG", "HD",
    "BAC", "KO", "ABBV", "CVX", "CRM", "AMD", "PEP", "TMO", "CSCO", "MCD",
    "IBM", "GE", "CAT", "GS", "AXP", "AMGN", "TXN", "INTU", "QCOM", "NOW"
]

NORDIC_LARGE_TICKERS = [
    # Danmark
    "NOVO-B.CO", "DSV.CO", "MAERSK-B.CO", "CARL-B.CO", "VWS.CO", "ORSTED.CO", "COLO-B.CO", "GMAB.CO",
    "DANSKE.CO", "PNDORA.CO", "ROCK-B.CO", "TRYG.CO",
    # Norge
    "EQNR.OL", "DNB.OL", "KOG.OL", "TEL.OL", "MOWI.OL", "NHY.OL", "YAR.OL", "ORK.OL",
    "AKRBP.OL", "SALM.OL", "TOM.OL", "GJF.OL",
    # Finland
    "NOKIA.HE", "KNEBV.HE", "SAMPO.HE", "FORTUM.HE", "UPM.HE", "NESTE.HE", "WRT1V.HE", "METSO.HE",
    "STERV.HE", "KESKOB.HE", "ELISA.HE", "ORNBV.HE"
]

GERMANY_LARGE_TICKERS = [
    "SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "AIR.DE", "MUV2.DE", "MBG.DE", "BMW.DE", "VOW3.DE",
    "BAS.DE", "BAYN.DE", "DB1.DE", "DHL.DE", "RWE.DE", "IFX.DE", "ADS.DE", "HEN3.DE", "BEI.DE",
    "FRE.DE", "HEI.DE", "MTX.DE", "SY1.DE", "VNA.DE", "CON.DE", "PAH3.DE", "ENR.DE", "SHL.DE", "QIA.DE"
]

UK_LARGE_TICKERS = [
    "AZN.L", "SHEL.L", "HSBA.L", "ULVR.L", "RIO.L", "BP.L", "GSK.L", "REL.L", "LSEG.L", "BA.L",
    "DGE.L", "NG.L", "BATS.L", "GLEN.L", "BARC.L", "LLOY.L", "RR.L", "CPG.L", "AAL.L", "PRU.L",
    "IMB.L", "VOD.L", "STAN.L", "EXPN.L", "III.L", "ANTO.L", "SSE.L", "NWG.L"
]

CANADA_LARGE_TICKERS = [
    "RY.TO", "TD.TO", "SHOP.TO", "ENB.TO", "CNR.TO", "CP.TO", "BMO.TO", "BNS.TO",
    "TRI.TO", "CNQ.TO", "SU.TO", "MFC.TO", "BCE.TO", "T.TO", "WCN.TO", "CSU.TO",
    "ATD.TO", "QSR.TO", "NTR.TO", "ABX.TO", "AEM.TO", "FTS.TO", "SLF.TO", "GWO.TO"
]

FRANCE_LARGE_TICKERS = [
    "MC.PA", "OR.PA", "TTE.PA", "SAN.PA", "AIR.PA", "SU.PA", "BNP.PA", "EL.PA",
    "SAF.PA", "AI.PA", "CS.PA", "RI.PA", "DG.PA", "KER.PA", "HO.PA", "ENGI.PA",
    "VIE.PA", "CAP.PA", "ORA.PA", "GLE.PA", "STLAP.PA", "ML.PA"
]

NETHERLANDS_LARGE_TICKERS = [
    "ASML.AS", "SHELL.AS", "INGA.AS", "ADYEN.AS", "PRX.AS", "PHIA.AS", "HEIA.AS",
    "UNA.AS", "WKL.AS", "AKZA.AS", "ASM.AS", "RAND.AS", "KPN.AS", "NN.AS", "AGN.AS"
]

BELGIUM_LARGE_TICKERS = [
    "ABI.BR", "UCB.BR", "KBC.BR", "GBLB.BR", "AGS.BR", "SOLB.BR", "UMI.BR",
    "ELI.BR", "COLR.BR", "ACKB.BR"
]

ITALY_LARGE_TICKERS = [
    "ENEL.MI", "ENI.MI", "ISP.MI", "UCG.MI", "STM.MI", "RACE.MI", "G.MI",
    "PRY.MI", "LDO.MI", "MB.MI", "TIT.MI", "AMP.MI", "SRG.MI", "TRN.MI"
]

SPAIN_LARGE_TICKERS = [
    "SAN.MC", "IBE.MC", "ITX.MC", "BBVA.MC", "TEF.MC", "REP.MC", "FER.MC",
    "CABK.MC", "AENA.MC", "ACS.MC", "AMS.MC", "GRF.MC"
]

SWITZERLAND_LARGE_TICKERS = [
    "NESN.SW", "ROG.SW", "NOVN.SW", "UBSG.SW", "ABBN.SW", "ZURN.SW", "CFR.SW",
    "SIKA.SW", "GIVN.SW", "LONN.SW", "HOLN.SW", "SCMN.SW", "SGSN.SW", "LOGN.SW"
]

PORTUGAL_LARGE_TICKERS = [
    "EDP.LS", "GALP.LS", "JMT.LS", "BCP.LS", "SON.LS", "REN.LS", "CTT.LS", "SEM.LS"
]

# Ett medvetet begränsat globalt radaruniversum. Syftet är att hitta kandidater över flera
# marknader utan att göra varje Streamlit-körning orimligt tung. Varje region finns kvar
# separat om användaren vill göra en bredare regional analys.
GLOBAL_RADAR_TICKERS = list(dict.fromkeys(
    SWEDEN_BROAD_TICKERS
    + US_LARGE_TICKERS
    + NORDIC_LARGE_TICKERS
    + GERMANY_LARGE_TICKERS
    + UK_LARGE_TICKERS
    + CANADA_LARGE_TICKERS
    + FRANCE_LARGE_TICKERS
    + NETHERLANDS_LARGE_TICKERS
    + BELGIUM_LARGE_TICKERS
    + ITALY_LARGE_TICKERS
    + SPAIN_LARGE_TICKERS
    + SWITZERLAND_LARGE_TICKERS
    + PORTUGAL_LARGE_TICKERS
))

MARKET_CONFIGS = {
    "Sverige": {"currency": "SEK", "benchmark": "^OMXS30", "benchmark_name": "OMXS30"},
    "USA": {"currency": "USD", "benchmark": "^GSPC", "benchmark_name": "S&P 500"},
    "Norden exkl. Sverige": {"currency": "lokal valuta", "benchmark": None, "benchmark_name": "—"},
    "Tyskland": {"currency": "EUR", "benchmark": "^GDAXI", "benchmark_name": "DAX"},
    "Storbritannien": {"currency": "GBP", "benchmark": "^FTSE", "benchmark_name": "FTSE 100"},
    "Kanada": {"currency": "CAD", "benchmark": "^GSPTSE", "benchmark_name": "S&P/TSX Composite"},
    "Frankrike": {"currency": "EUR", "benchmark": "^FCHI", "benchmark_name": "CAC 40"},
    "Nederländerna": {"currency": "EUR", "benchmark": "^AEX", "benchmark_name": "AEX"},
    "Belgien": {"currency": "EUR", "benchmark": "^BFX", "benchmark_name": "BEL 20"},
    "Italien": {"currency": "EUR", "benchmark": "FTSEMIB.MI", "benchmark_name": "FTSE MIB"},
    "Spanien": {"currency": "EUR", "benchmark": "^IBEX", "benchmark_name": "IBEX 35"},
    "Schweiz": {"currency": "CHF", "benchmark": "^SSMI", "benchmark_name": "SMI"},
    "Portugal": {"currency": "EUR", "benchmark": "PSI20.LS", "benchmark_name": "PSI"},
    "Alla marknader": {"currency": "blandat", "benchmark": "VT", "benchmark_name": "Globalt aktieindex (VT)"},
}

MARKET_UNIVERSES = {
    "Sverige": SWEDEN_BROAD_TICKERS,
    "USA": US_LARGE_TICKERS,
    "Norden exkl. Sverige": NORDIC_LARGE_TICKERS,
    "Tyskland": GERMANY_LARGE_TICKERS,
    "Storbritannien": UK_LARGE_TICKERS,
    "Kanada": CANADA_LARGE_TICKERS,
    "Frankrike": FRANCE_LARGE_TICKERS,
    "Nederländerna": NETHERLANDS_LARGE_TICKERS,
    "Belgien": BELGIUM_LARGE_TICKERS,
    "Italien": ITALY_LARGE_TICKERS,
    "Spanien": SPAIN_LARGE_TICKERS,
    "Schweiz": SWITZERLAND_LARGE_TICKERS,
    "Portugal": PORTUGAL_LARGE_TICKERS,
    "Alla marknader": GLOBAL_RADAR_TICKERS,
}


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


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fundamentals(symbol: str) -> dict[str, Any]:
    """Fetch slower fundamental fields with a persistent 24-hour cache.

    Streamlit's in-memory cache is fast but disappears on process restarts and is
    cleared by the normal refresh button. The SQLite cache avoids repeating the
    same Yahoo get_info request during the same day while price data can still be
    refreshed independently.
    """
    cached = get_cached_fundamentals(DB_PATH, symbol, CACHE_MAX_AGE_HOURS)
    if cached is not None:
        cached = dict(cached)
        cached["_Fundamental cache"] = "beständig cache"
        return cached

    t = yf.Ticker(symbol)
    info = _safe_info(t)
    market_cap, fcf, target = _num(info.get("marketCap")), _num(info.get("freeCashflow")), _num(info.get("targetMeanPrice"))
    payload = {
        "Namn": info.get("shortName") or info.get("longName") or symbol,
        "Sektor": info.get("sector") or "Okänd",
        "Bransch": info.get("industry") or "Okänd",
        "Valuta": info.get("currency") or "SEK",
        "Finansiell valuta": info.get("financialCurrency") or major_currency(info.get("currency") or "SEK"),
        "Börsvärde lokal mdr": market_cap / 1e9 if np.isfinite(market_cap) else np.nan,
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
    put_cached_fundamentals(DB_PATH, symbol, payload)
    payload["_Fundamental cache"] = "Yahoo"
    return payload


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
        "Omsättning lokal M/dag": avg20_volume * price / 1e6 if np.isfinite(avg20_volume) and np.isfinite(price) else np.nan,
        "Omsättning MSEK/dag": avg20_volume * price / 1e6 if np.isfinite(avg20_volume) and np.isfinite(price) else np.nan,
        "Analytikerpotential": target / price - 1 if np.isfinite(target) and np.isfinite(price) and price > 0 else np.nan,
        "Yahoo": f"https://finance.yahoo.com/quote/{quote(symbol)}", "_history": hist.tail(260),
    })
    return row


@st.cache_data(ttl=900, show_spinner=False)
def fetch_fx_rates_to_sek(currencies: tuple[str, ...]) -> dict[str, float]:
    """Fetch latest SEK conversion rates for the currencies used in the current scan."""
    needed = sorted({major_currency(c) for c in currencies if major_currency(c) != "SEK"})
    rates: dict[str, float] = {"SEK": 1.0}
    for currency in needed:
        symbol = FX_TO_SEK_SYMBOLS.get(currency)
        if not symbol:
            continue
        try:
            hist = yf.Ticker(symbol).history(period="5d", interval="1d", auto_adjust=True, actions=False)
            if isinstance(hist, pd.DataFrame) and not hist.empty and "Close" in hist.columns:
                close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
                if not close.empty:
                    rate = _num(close.iloc[-1])
                    if np.isfinite(rate) and rate > 0:
                        rates[currency] = rate
        except Exception:
            continue
    return rates


def add_sek_conversions(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float], list[str]]:
    """Add comparable SEK price, market-cap and turnover columns without changing source values."""
    if df.empty:
        return df.copy(), {"SEK": 1.0}, []
    out = df.copy()
    quote_ccy = out.get("Valuta", pd.Series("SEK", index=out.index)).fillna("SEK").astype(str)
    fin_ccy = out.get("Finansiell valuta", quote_ccy).fillna(quote_ccy).astype(str)
    currencies = tuple(sorted(set(quote_ccy.tolist() + fin_ccy.tolist())))
    rates = fetch_fx_rates_to_sek(currencies)
    missing = sorted({major_currency(c) for c in currencies if major_currency(c) not in rates and major_currency(c) != "SEK"})

    out["Pris SEK"] = [quote_amount_to_sek(v, c, rates) for v, c in zip(out.get("Pris", pd.Series(np.nan, index=out.index)), quote_ccy)]
    local_cap = out.get("Börsvärde lokal mdr", out.get("Börsvärde BSEK", pd.Series(np.nan, index=out.index)))
    out["Börsvärde BSEK"] = [major_amount_to_sek(v, c, rates) for v, c in zip(local_cap, fin_ccy)]
    local_turn = out.get("Omsättning lokal M/dag", out.get("Omsättning MSEK/dag", pd.Series(np.nan, index=out.index)))
    out["Omsättning MSEK/dag"] = [quote_amount_to_sek(v, c, rates) for v, c in zip(local_turn, quote_ccy)]
    out["FX till SEK"] = [rates.get(major_currency(c), np.nan) for c in quote_ccy]
    return out, rates, missing


def fmt_price_with_sek(row: pd.Series | dict[str, Any]) -> str:
    price = _num(row.get("Pris"))
    ccy = str(row.get("Valuta") or "")
    sek = _num(row.get("Pris SEK"))
    if not np.isfinite(price):
        return "—"
    major = major_currency(ccy)
    base = f"{price:.2f} {ccy}".strip()
    if major == "SEK" or not np.isfinite(sek):
        return base
    return f"{base} · ≈ {sek:,.0f} SEK".replace(",", " ")


@st.cache_data(ttl=900, show_spinner=False)
def fetch_index_snapshot(symbol: str = "^OMXS30") -> dict[str, float]:
    """Current benchmark plus trailing returns used for relative-strength checks."""
    if not symbol:
        return {}
    try:
        hist = yf.Ticker(symbol).history(period="1y", interval="1d", auto_adjust=True, actions=False)
        if hist is None or hist.empty:
            return {}
        close = hist["Close"].dropna().astype(float)
        if close.empty:
            return {}
        return {
            "index": _num(close.iloc[-1]),
            "daily": _pct_change(close, 1),
            "month": _pct_change(close, min(21, max(len(close)-1, 1))),
            "3m": _pct_change(close, min(63, max(len(close)-1, 1))),
            "6m": _pct_change(close, min(126, max(len(close)-1, 1))),
        }
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

    # v2.27: analyst target potential is deliberately NOT part of Valuation.
    # A stale/optimistic target price is an opinion, not evidence that the share is cheap.
    valuation = _mean_scores([
        _sector_percentile_score(temp, "P/E", False), _sector_percentile_score(temp, "Forward P/E", False),
        _sector_percentile_score(temp, "P/B", False), _sector_percentile_score(temp, "EV/EBITDA", False),
        _sector_percentile_score(temp, "FCF-yield", True),
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
    # v2.27: growth no longer includes FCF-yield. FCF-yield is a valuation/cash-return
    # measure and previously leaked the same information into both valuation and growth.
    growth = _mean_scores([
        _percentile_score(out["Omsättningstillväxt"].clip(-1, 2), True),
        _percentile_score(out["Vinsttillväxt"].clip(-1, 3), True),
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
    """Price-first scan with persistent fundamentals caching.

    Stage 1 validates quote/history data before any expensive Yahoo get_info call.
    Stage 2 fetches fundamentals only for symbols that can actually be ranked.
    A 24-hour SQLite cache avoids repeating unchanged fundamentals on reruns or
    after normal Streamlit cache clears.
    """
    symbols = list(dict.fromkeys(symbols))
    rows, errors = [], []
    metrics = {
        "requested": len(symbols),
        "price_usable": 0,
        "price_rejected_before_fundamentals": 0,
        "fundamental_candidates": 0,
        "fundamental_yahoo": 0,
        "fundamental_persistent_cache": 0,
        "single_price_fallbacks": 0,
        "price_seconds": 0.0,
        "fundamental_seconds": 0.0,
    }

    price_started = time.perf_counter()
    price_map = fetch_bulk_price_history(tuple(symbols))
    usable_histories: dict[str, pd.DataFrame] = {}

    for sym in symbols:
        hist = price_map.get(sym)
        if hist is None or hist.empty:
            metrics["single_price_fallbacks"] += 1
            hist = fetch_single_price_history(sym)

        if hist is None or hist.empty:
            errors.append(f"{sym}: ingen kurshistorik efter bulk + fallback")
            metrics["price_rejected_before_fundamentals"] += 1
            continue

        price_gate = assess_price_history(hist)
        if not bool(price_gate.get("usable")):
            errors.append(
                f"{sym}: prisdata stoppad före bolagsdata · "
                f"{price_gate.get('reason','otillräcklig kursdata')}"
            )
            metrics["price_rejected_before_fundamentals"] += 1
            continue

        usable_histories[sym] = hist

    metrics["price_seconds"] = round(time.perf_counter() - price_started, 3)
    metrics["price_usable"] = len(usable_histories)
    metrics["fundamental_candidates"] = len(usable_histories)

    fundamentals: dict[str, dict[str, Any]] = {}
    fundamental_started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(usable_histories)))) as executor:
        futures = {executor.submit(fetch_fundamentals, sym): sym for sym in usable_histories}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                data = future.result()
                fundamentals[sym] = data
                source = str(data.get("_Fundamental cache") or "")
                if source == "Yahoo":
                    metrics["fundamental_yahoo"] += 1
                elif source == "beständig cache":
                    metrics["fundamental_persistent_cache"] += 1
            except Exception as exc:
                fundamentals[sym] = {
                    "Namn": sym, "Sektor": "Okänd", "Bransch": "Okänd",
                    "Valuta": "SEK", "Fundamental hämtad": "—",
                }
                errors.append(f"{sym}: fundamentaldata {type(exc).__name__}")
    metrics["fundamental_seconds"] = round(time.perf_counter() - fundamental_started, 3)

    for sym, hist in usable_histories.items():
        row = _price_snapshot(sym, hist, fundamentals.get(sym, {}))
        if row.get("error"):
            errors.append(f"{sym}: {row['error']}")
        else:
            rows.append(row)

    try:
        st.session_state["bq_scan_metrics"] = metrics
    except Exception:
        pass
    return (pd.DataFrame(rows) if rows else pd.DataFrame()), errors



@st.cache_data(ttl=43200, show_spinner=False)
def fetch_deep_statements(symbol: str) -> dict[str, Any]:
    """Fetch multi-year statements for a small finalist pool only.

    Broad scanning stays fast; deeper Yahoo requests are reserved for the strongest
    long-term candidates. Missing statements are returned as empty frames rather
    than inferred.
    """
    try:
        t = yf.Ticker(symbol)
        def _frame(value: Any) -> pd.DataFrame:
            return value if isinstance(value, pd.DataFrame) else pd.DataFrame()
        try: income = _frame(t.income_stmt)
        except Exception: income = pd.DataFrame()
        try: cashflow = _frame(t.cashflow)
        except Exception: cashflow = pd.DataFrame()
        try: balance = _frame(t.balance_sheet)
        except Exception: balance = pd.DataFrame()
        try: quarterly_income = _frame(t.quarterly_income_stmt)
        except Exception: quarterly_income = pd.DataFrame()
        try: quarterly_cashflow = _frame(t.quarterly_cashflow)
        except Exception: quarterly_cashflow = pd.DataFrame()
        try: quarterly_balance = _frame(t.quarterly_balance_sheet)
        except Exception: quarterly_balance = pd.DataFrame()

        def _analyst_frame(*names: str) -> pd.DataFrame:
            for name in names:
                try:
                    value = getattr(t, name)
                    if callable(value):
                        value = value()
                    if isinstance(value, pd.DataFrame):
                        return value
                except Exception:
                    continue
            return pd.DataFrame()

        # Analyst estimate tables are optional. Yahoo/yfinance coverage varies by
        # market, so missing data is never inferred or replaced with headline text.
        eps_trend = _analyst_frame("eps_trend", "get_eps_trend")
        eps_revisions = _analyst_frame("eps_revisions", "get_eps_revisions")
        earnings_history = _analyst_frame("earnings_history", "get_earnings_history")

        # Catalyst inputs are deliberately lightweight and optional. Calendar timing is
        # useful when available; news headlines are triage evidence only and are never
        # treated as verified economic impact.
        earnings_date = None
        try:
            cal = t.calendar
            if isinstance(cal, dict):
                earnings_date = cal.get("Earnings Date") or cal.get("EarningsDate")
                if isinstance(earnings_date, (list, tuple)) and earnings_date:
                    earnings_date = earnings_date[0]
            elif isinstance(cal, pd.DataFrame) and not cal.empty:
                for key in ["Earnings Date", "EarningsDate"]:
                    if key in cal.index:
                        earnings_date = cal.loc[key].iloc[0]
                        break
        except Exception:
            earnings_date = None

        catalyst_news = []
        try:
            for item in (t.news or [])[:6]:
                content = item.get("content", item) if isinstance(item, dict) else {}
                title = content.get("title") if isinstance(content, dict) else None
                if not title and isinstance(item, dict):
                    title = item.get("title")
                link = None
                if isinstance(content, dict):
                    canonical = content.get("canonicalUrl") or content.get("clickThroughUrl")
                    if isinstance(canonical, dict):
                        link = canonical.get("url")
                    elif isinstance(canonical, str):
                        link = canonical
                if not link and isinstance(item, dict):
                    link = item.get("link")
                if title:
                    published_at = None
                    provider = None
                    if isinstance(content, dict):
                        published_at = content.get("pubDate") or content.get("displayTime")
                        provider_obj = content.get("provider")
                        if isinstance(provider_obj, dict):
                            provider = provider_obj.get("displayName") or provider_obj.get("name")
                    if not published_at and isinstance(item, dict):
                        published_at = item.get("providerPublishTime") or item.get("pubDate")
                    catalyst_news.append({
                        "title": str(title),
                        "link": link,
                        "published_at": published_at,
                        "provider": provider,
                    })
        except Exception:
            catalyst_news = []

        return {
            "income": income, "cashflow": cashflow, "balance": balance,
            "quarterly_income": quarterly_income, "quarterly_cashflow": quarterly_cashflow,
            "quarterly_balance": quarterly_balance,
            "eps_trend": eps_trend, "eps_revisions": eps_revisions,
            "earnings_history": earnings_history,
            "catalyst_events": {"earnings": earnings_date, "news": catalyst_news},
            "error": ""
        }
    except Exception as exc:
        return {"income": pd.DataFrame(), "cashflow": pd.DataFrame(), "balance": pd.DataFrame(), "error": type(exc).__name__}


def build_deep_longlist(df: pd.DataFrame, pool_size: int = 6, limit: int = 5) -> pd.DataFrame:
    """Deep-check a small INVEST finalist pool using multi-year statements.

    Ordering is gate-first (value-trap/data-quality checks) and only then uses the
    existing INVEST score. This intentionally avoids inventing a new unvalidated
    weighted mega-score.
    """
    if df.empty:
        return df.copy()
    pool = df.sort_values(["INVEST Score", "Datatäckning"], ascending=[False, False]).head(pool_size).copy()
    records: dict[str, dict[str, Any]] = {}
    max_workers = min(3, max(1, len(pool)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_deep_statements, str(row["Ticker"])): idx for idx, row in pool.iterrows()}
        for future in as_completed(futures):
            idx = futures[future]
            row = pool.loc[idx]
            try:
                raw = future.result()
                metrics = build_deep_metrics(raw.get("income"), raw.get("cashflow"), raw.get("balance"))
                assessment = assess_deep_case(metrics, row)

                earnings_quality_metrics = build_earnings_quality_metrics(
                    raw.get("income"), raw.get("cashflow"), raw.get("balance")
                )
                earnings_quality = assess_earnings_quality(earnings_quality_metrics)
                assessment.update(earnings_quality)
                assessment = apply_earnings_quality_gate(assessment)

                inflection_metrics = build_inflection_metrics(
                    raw.get("quarterly_income"), raw.get("quarterly_cashflow"),
                    raw.get("eps_trend"), raw.get("eps_revisions"), raw.get("earnings_history"),
                    raw.get("quarterly_balance")
                )
                inflection = assess_inflection(inflection_metrics)
                assessment.update(inflection)
                assessment = apply_inflection_gate(assessment)
                mispricing = build_mispricing_assessment(row, assessment)
                assessment.update(mispricing)
                assessment = apply_mispricing_gate(assessment)
                scenario = build_scenarios(row.to_dict(), assessment, assessment, assessment)
                assessment["Scenario Status"] = scenario.get("status", "Otillräcklig data")
                assessment["Scenario Confidence"] = scenario.get("confidence", 0)
                if scenario.get("status") == "OK":
                    assessment["Scenario Verdict"] = scenario.get("verdict", "—")
                    assessment["Scenario Asymmetry"] = scenario.get("asymmetry", np.nan)
                    assessment["Scenario Risk Label"] = scenario.get("risk_label", "—")
                    assessment["Scenario Note"] = scenario.get("note", "—")
                    for label, key in (("Bear", "bear"), ("Base", "base"), ("Bull", "bull")):
                        s = scenario.get(key, {})
                        assessment[f"{label} EPS growth"] = s.get("eps_growth", np.nan)
                        assessment[f"{label} exit P/E"] = s.get("exit_pe", np.nan)
                        assessment[f"{label} future price"] = s.get("future_price", np.nan)
                        assessment[f"{label} upside"] = s.get("upside", np.nan)
                        assessment[f"{label} annualized return"] = s.get("annualized_return", np.nan)
                else:
                    assessment["Scenario Verdict"] = "Kan inte bedömas"
                    assessment["Scenario Asymmetry"] = np.nan
                    assessment["Scenario Note"] = scenario.get("reason", "Otillräcklig data")
                catalyst = build_catalyst_assessment({**row.to_dict(), **assessment}, raw.get("catalyst_events"))
                assessment.update(catalyst)
                assessment.update(build_case_quality_gate({**row.to_dict(), **assessment}))
                if raw.get("error"):
                    assessment["Deep fetch error"] = raw.get("error")
                records[idx] = assessment
            except Exception as exc:
                records[idx] = {
                    "Djupkontroll": "Otillräcklig data", "Value Trap Risk": np.nan, "Deep Confidence": 0.0,
                    "Fleråriga styrkor": "kunde inte verifieras", "Fleråriga varningar": f"djupdata kunde inte läsas ({type(exc).__name__})",
                    "Varför marknaden kan ha fel": "kan inte bedömas med tillräcklig flerårsdata",
                    "Devil's Advocate": "otillräcklig data – gå inte vidare på modellen ensam", "Rapportdatum": "—",
                }
    # Pandas .at still falls back to .loc when a target column does not yet exist.
    # Some assessment fields are lists/dicts (e.g. catalyst candidates/supports), so
    # create all new columns as object dtype before assigning cell-by-cell.
    # Build an object-typed result frame first, then join it into pool.
    # This avoids Pandas scalar assignment entirely for list/dict values.
    if records:
        assessment_frame = pd.DataFrame.from_dict(records, orient="index")
        for key in assessment_frame.columns:
            assessment_frame[key] = assessment_frame[key].astype("object")
        existing = [c for c in assessment_frame.columns if c in pool.columns]
        if existing:
            pool = pool.drop(columns=existing)
        pool = pool.join(assessment_frame, how="left")
    # Final ordering is evidence-gate first. INVEST only breaks ties after the
    # independent quality, inflection, mispricing and scenario checks.
    order = sorted(pool.index, key=lambda idx: case_gate_rank_key(pool.loc[idx]), reverse=True)
    return pool.loc[order].head(limit).copy()


def build_short_term_longlist(df: pd.DataFrame, benchmark: dict[str, Any] | None, pool_size: int = 8, limit: int = 5) -> pd.DataFrame:
    """Build a 1–6 month finalist list.

    Stage 1 uses only causal current technical/relative-strength data to choose a small
    candidate pool. Stage 2 adds fresh quarterly/estimate inflection and catalyst evidence.
    A prior fall is never a positive input and hard anti-falling-knife vetoes survive stage 2.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    prelim = df.copy()
    prelim_records: dict[Any, dict[str, Any]] = {}
    for idx, row in prelim.iterrows():
        prelim_records[idx] = assess_short_term_case(row, benchmark)
    for idx, assessment in prelim_records.items():
        for key, value in assessment.items():
            prelim.at[idx, key] = value

    prelim_order = sorted(prelim.index, key=lambda idx: short_term_rank_key(prelim.loc[idx]), reverse=True)
    pool = prelim.loc[prelim_order].head(pool_size).copy()
    if pool.empty:
        return pool

    records: dict[Any, dict[str, Any]] = {}
    max_workers = min(3, max(1, len(pool)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_deep_statements, str(row["Ticker"])): idx for idx, row in pool.iterrows()}
        for future in as_completed(futures):
            idx = futures[future]
            row = pool.loc[idx]
            try:
                raw = future.result()
                inflection_metrics = build_inflection_metrics(
                    raw.get("quarterly_income"), raw.get("quarterly_cashflow"),
                    raw.get("eps_trend"), raw.get("eps_revisions"), raw.get("earnings_history"),
                    raw.get("quarterly_balance")
                )
                inflection = assess_inflection(inflection_metrics)
                catalyst = build_catalyst_assessment({**row.to_dict(), **inflection}, raw.get("catalyst_events"))
                result = assess_short_term_case(row, benchmark, inflection, catalyst)
                result.update({
                    "Inflection Signal": inflection.get("Inflection Signal", "Otillräcklig förändringsdata"),
                    "Inflection Score": inflection.get("Inflection Score", np.nan),
                    "Varför nu": inflection.get("Varför nu", "—"),
                    "Catalyst Signal": catalyst.get("Catalyst Signal", "Ingen tydlig katalysator verifierad"),
                    "Primary Catalyst": catalyst.get("Primary Catalyst", "Ingen verifierad"),
                    "Catalyst Timing": catalyst.get("Catalyst Timing", "—"),
                    "Catalyst Evidence": catalyst.get("Catalyst Evidence", "Otillräcklig katalysatordata."),
                    "Catalyst Warnings": catalyst.get("Catalyst Warnings", "—"),
                })
                if raw.get("error"):
                    result["Short Data Warning"] = raw.get("error")
                records[idx] = result
            except Exception as exc:
                fallback = assess_short_term_case(row, benchmark)
                fallback["Short Data Warning"] = f"Färsk fundamental-/estimatsdata kunde inte läsas ({type(exc).__name__})."
                records[idx] = fallback

    # Same protection as the deep longlist: pre-create new fields as object dtype
    # so iterable assessment values never trigger Pandas' multi-column assignment path.
    if records:
        assessment_frame = pd.DataFrame.from_dict(records, orient="index")
        for key in assessment_frame.columns:
            assessment_frame[key] = assessment_frame[key].astype("object")
        existing = [c for c in assessment_frame.columns if c in pool.columns]
        if existing:
            pool = pool.drop(columns=existing)
        pool = pool.join(assessment_frame, how="left")

    order = sorted(pool.index, key=lambda idx: short_term_rank_key(pool.loc[idx]), reverse=True)
    return pool.loc[order].head(limit).copy()


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
        _ensure_sqlite_column(conn, "watchlist", "breaker_min_score", "REAL NOT NULL DEFAULT 0")
        _ensure_sqlite_column(conn, "watchlist", "breaker_min_quality", "REAL NOT NULL DEFAULT 0")
        _ensure_sqlite_column(conn, "watchlist", "breaker_min_risk", "REAL NOT NULL DEFAULT 0")
        _ensure_sqlite_column(conn, "watchlist", "breaker_max_score_drop", "REAL NOT NULL DEFAULT 0")
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS visit_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                last_seen_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviewed_changes (
                change_key TEXT PRIMARY KEY,
                reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendation_ledger (
                record_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                horizon_type TEXT NOT NULL,
                model_version TEXT NOT NULL,
                profile TEXT NOT NULL,
                market TEXT NOT NULL,
                rank INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                gate TEXT NOT NULL DEFAULT '',
                score REAL,
                confidence REAL,
                evidence_count INTEGER,
                why_now TEXT NOT NULL DEFAULT '',
                primary_catalyst TEXT NOT NULL DEFAULT '',
                captured_date TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                snapshot_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendation_outcomes (
                record_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                horizon TEXT NOT NULL,
                trading_days INTEGER NOT NULL,
                evaluated_date TEXT NOT NULL,
                evaluated_price REAL NOT NULL,
                return_pct REAL NOT NULL,
                positive INTEGER NOT NULL DEFAULT 0,
                gain_10 INTEGER NOT NULL DEFAULT 0,
                loss_10 INTEGER NOT NULL DEFAULT 0,
                evaluated_at TEXT NOT NULL,
                PRIMARY KEY (record_id, horizon)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_usage (
                request_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holdings (
                holding_id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                purchase_price REAL NOT NULL,
                quantity REAL NOT NULL DEFAULT 1,
                purchase_date TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS universe_qc_state (
                symbol TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'OKÄND',
                failure_streak INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                last_checked_at TEXT,
                last_verified_at TEXT,
                last_reason TEXT NOT NULL DEFAULT '',
                quarantine_until TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS universe_qc_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                counted_failure INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )




def get_universe_qc_states() -> pd.DataFrame:
    cols = [
        "symbol","status","failure_streak","success_count","failure_count",
        "last_checked_at","last_verified_at","last_reason","quarantine_until",
    ]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = client.table("universe_qc_state").select(",".join(cols)).eq("user_id", uid).execute().data or []
            return pd.DataFrame(data, columns=cols)
        except Exception:
            st.session_state["bq_qc_state_migration_needed"] = True
            return pd.DataFrame(columns=cols)
    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query(f"SELECT {','.join(cols)} FROM universe_qc_state", conn)


def save_universe_qc_state(state: dict[str, Any], outcome: str, counted_failure: bool) -> None:
    symbol = str(state.get("symbol") or "").upper().strip()
    if not symbol:
        return
    client = _supabase_client(); uid = current_user_id()
    payload = {
        "symbol": symbol,
        "status": str(state.get("status") or "OKÄND"),
        "failure_streak": int(state.get("failure_streak") or 0),
        "success_count": int(state.get("success_count") or 0),
        "failure_count": int(state.get("failure_count") or 0),
        "last_checked_at": state.get("last_checked_at"),
        "last_verified_at": state.get("last_verified_at"),
        "last_reason": str(state.get("last_reason") or ""),
        "quarantine_until": state.get("quarantine_until"),
    }
    if client is not None and uid:
        try:
            client.table("universe_qc_state").upsert({"user_id": uid, **payload}, on_conflict="user_id,symbol").execute()
            client.table("universe_qc_events").insert({
                "user_id": uid, "symbol": symbol, "outcome": str(outcome),
                "reason": payload["last_reason"], "counted_failure": bool(counted_failure),
            }).execute()
            return
        except Exception:
            st.session_state["bq_qc_state_migration_needed"] = True
            return
    init_db()
    with _db_connect() as conn:
        conn.execute(
            """
            INSERT INTO universe_qc_state(
                symbol,status,failure_streak,success_count,failure_count,last_checked_at,
                last_verified_at,last_reason,quarantine_until
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET
                status=excluded.status,
                failure_streak=excluded.failure_streak,
                success_count=excluded.success_count,
                failure_count=excluded.failure_count,
                last_checked_at=excluded.last_checked_at,
                last_verified_at=excluded.last_verified_at,
                last_reason=excluded.last_reason,
                quarantine_until=excluded.quarantine_until
            """,
            (
                payload["symbol"], payload["status"], payload["failure_streak"], payload["success_count"],
                payload["failure_count"], payload["last_checked_at"], payload["last_verified_at"],
                payload["last_reason"], payload["quarantine_until"],
            ),
        )
        conn.execute(
            "INSERT INTO universe_qc_events(symbol,outcome,reason,counted_failure) VALUES(?,?,?,?)",
            (symbol, str(outcome), payload["last_reason"], 1 if counted_failure else 0),
        )


def active_quarantine_symbols(states: pd.DataFrame) -> set[str]:
    if states is None or states.empty:
        return set()
    return {
        str(row.get("symbol") or "").upper()
        for _, row in states.iterrows()
        if str(row.get("symbol") or "") and is_quarantined(row)
    }



def get_holdings() -> pd.DataFrame:
    cols = ["holding_id","symbol","purchase_price","quantity","purchase_date","note","created_at"]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = (
                client.table("holdings").select(",".join(cols))
                .eq("user_id", uid).order("created_at", desc=False).execute().data or []
            )
            return pd.DataFrame(data, columns=cols)
        except Exception:
            st.session_state["bq_holdings_migration_needed"] = True
            return pd.DataFrame(columns=cols)
    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query(
            f"SELECT {','.join(cols)} FROM holdings ORDER BY created_at ASC", conn
        )


def add_holding(symbol: str, purchase_price: float, quantity: float, purchase_date: str, note: str = "") -> None:
    symbol = str(symbol or "").upper().strip()
    if not symbol or purchase_price <= 0 or quantity <= 0:
        return
    client = _supabase_client(); uid = current_user_id()
    payload = {
        "symbol": symbol, "purchase_price": float(purchase_price), "quantity": float(quantity),
        "purchase_date": str(purchase_date or ""), "note": str(note or ""),
    }
    if client is not None and uid:
        try:
            client.table("holdings").insert({"user_id": uid, **payload}).execute()
            return
        except Exception:
            st.session_state["bq_holdings_migration_needed"] = True
            return
    init_db()
    with _db_connect() as conn:
        conn.execute(
            "INSERT INTO holdings(symbol,purchase_price,quantity,purchase_date,note) VALUES(?,?,?,?,?)",
            (payload["symbol"], payload["purchase_price"], payload["quantity"], payload["purchase_date"], payload["note"]),
        )


def delete_holding(holding_id: int) -> None:
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            client.table("holdings").delete().eq("user_id", uid).eq("holding_id", int(holding_id)).execute()
            return
        except Exception:
            st.session_state["bq_holdings_migration_needed"] = True
            return
    init_db()
    with _db_connect() as conn:
        conn.execute("DELETE FROM holdings WHERE holding_id=?", (int(holding_id),))



def _load_last_visit() -> str | None:
    """Read the previous overview visit. Missing cloud migration degrades safely."""
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = client.table("visit_state").select("last_seen_at").eq("user_id", uid).limit(1).execute().data or []
            return str(data[0].get("last_seen_at")) if data else None
        except Exception:
            st.session_state["bq_visit_state_migration_needed"] = True
            return None
    init_db()
    with _db_connect() as conn:
        row = conn.execute("SELECT last_seen_at FROM visit_state WHERE singleton=1").fetchone()
    return str(row[0]) if row else None


def _save_last_visit(value: str) -> None:
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            client.table("visit_state").upsert({"user_id": uid, "last_seen_at": value}, on_conflict="user_id").execute()
        except Exception:
            st.session_state["bq_visit_state_migration_needed"] = True
        return
    init_db()
    with _db_connect() as conn:
        conn.execute(
            "INSERT INTO visit_state(singleton,last_seen_at) VALUES(1,?) "
            "ON CONFLICT(singleton) DO UPDATE SET last_seen_at=excluded.last_seen_at",
            (value,),
        )


def visit_context() -> tuple[str | None, str]:
    """Freeze the previous-visit marker for this Streamlit session/reruns."""
    if "bq_previous_visit_at" not in st.session_state:
        previous = _load_last_visit()
        current = datetime.now().isoformat(timespec="seconds")
        st.session_state["bq_previous_visit_at"] = previous
        st.session_state["bq_current_visit_started_at"] = current
        _save_last_visit(current)
    return st.session_state.get("bq_previous_visit_at"), str(st.session_state.get("bq_current_visit_started_at", ""))


def get_reviewed_change_keys() -> set[str]:
    """Return change ids the current user has explicitly reviewed."""
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = client.table("reviewed_changes").select("change_key").eq("user_id", uid).execute().data or []
            return {str(x.get("change_key")) for x in data if x.get("change_key")}
        except Exception:
            st.session_state["bq_review_state_migration_needed"] = True
            return set()
    init_db()
    with _db_connect() as conn:
        rows = conn.execute("SELECT change_key FROM reviewed_changes").fetchall()
    return {str(r[0]) for r in rows}


def mark_change_reviewed(change_key: str) -> None:
    key = str(change_key or "").strip()
    if not key:
        return
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            client.table("reviewed_changes").upsert({"user_id": uid, "change_key": key}, on_conflict="user_id,change_key").execute()
        except Exception:
            st.session_state["bq_review_state_migration_needed"] = True
        return
    init_db()
    with _db_connect() as conn:
        conn.execute("INSERT OR IGNORE INTO reviewed_changes(change_key) VALUES(?)", (key,))



def save_recommendation_records(records: list[dict[str, Any]]) -> None:
    """Idempotently freeze daily model finalists before future outcomes are known."""
    if not records:
        return
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        for rec in records:
            payload = {"user_id": uid, **rec}
            try:
                client.table("recommendation_ledger").upsert(
                    payload, on_conflict="user_id,record_id"
                ).execute()
            except Exception:
                st.session_state["bq_recommendation_ledger_migration_needed"] = True
                return
        return

    init_db()
    cols = [
        "record_id","symbol","name","horizon_type","model_version","profile","market",
        "rank","entry_price","gate","score","confidence","evidence_count","why_now",
        "primary_catalyst","captured_date","captured_at","snapshot_json",
    ]
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT OR IGNORE INTO recommendation_ledger({','.join(cols)}) VALUES ({placeholders})"
    with _db_connect() as conn:
        for rec in records:
            conn.execute(sql, tuple(rec.get(c) for c in cols))


def get_recommendation_records(limit: int = 500) -> pd.DataFrame:
    cols = [
        "record_id","symbol","name","horizon_type","model_version","profile","market",
        "rank","entry_price","gate","score","confidence","evidence_count","why_now",
        "primary_catalyst","captured_date","captured_at","snapshot_json",
    ]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = (
                client.table("recommendation_ledger").select(",".join(cols))
                .eq("user_id", uid).order("captured_at", desc=True).limit(int(limit))
                .execute().data or []
            )
            return pd.DataFrame(data, columns=cols)
        except Exception:
            st.session_state["bq_recommendation_ledger_migration_needed"] = True
            return pd.DataFrame(columns=cols)

    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query(
            f"SELECT {','.join(cols)} FROM recommendation_ledger ORDER BY captured_at DESC LIMIT ?",
            conn, params=(int(limit),)
        )


def save_recommendation_outcomes(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        for row in rows:
            payload = {"user_id": uid, **row}
            try:
                client.table("recommendation_outcomes").upsert(
                    payload, on_conflict="user_id,record_id,horizon"
                ).execute()
            except Exception:
                st.session_state["bq_recommendation_ledger_migration_needed"] = True
                return
        return

    init_db()
    cols = [
        "record_id","symbol","horizon","trading_days","evaluated_date","evaluated_price",
        "return_pct","positive","gain_10","loss_10","evaluated_at",
    ]
    placeholders = ",".join(["?"] * len(cols))
    sql = (
        f"INSERT INTO recommendation_outcomes({','.join(cols)}) VALUES ({placeholders}) "
        "ON CONFLICT(record_id,horizon) DO UPDATE SET "
        "evaluated_date=excluded.evaluated_date,evaluated_price=excluded.evaluated_price,"
        "return_pct=excluded.return_pct,positive=excluded.positive,gain_10=excluded.gain_10,"
        "loss_10=excluded.loss_10,evaluated_at=excluded.evaluated_at"
    )
    with _db_connect() as conn:
        for row in rows:
            vals = []
            for c in cols:
                v = row.get(c)
                if c in {"positive","gain_10","loss_10"}:
                    v = 1 if bool(v) else 0
                vals.append(v)
            conn.execute(sql, tuple(vals))


def get_recommendation_outcomes(limit: int = 2000) -> pd.DataFrame:
    cols = [
        "record_id","symbol","horizon","trading_days","evaluated_date","evaluated_price",
        "return_pct","positive","gain_10","loss_10","evaluated_at",
    ]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = (
                client.table("recommendation_outcomes").select(",".join(cols))
                .eq("user_id", uid).order("evaluated_at", desc=True).limit(int(limit))
                .execute().data or []
            )
            return pd.DataFrame(data, columns=cols)
        except Exception:
            st.session_state["bq_recommendation_ledger_migration_needed"] = True
            return pd.DataFrame(columns=cols)

    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query(
            f"SELECT {','.join(cols)} FROM recommendation_outcomes ORDER BY evaluated_at DESC LIMIT ?",
            conn, params=(int(limit),)
        )


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ledger_history(symbol: str, start_date: str) -> pd.DataFrame:
    """Fetch raw price history needed to evaluate an already-frozen recommendation."""
    try:
        start = (pd.Timestamp(start_date) - pd.Timedelta(days=7)).date().isoformat()
        hist = yf.Ticker(symbol).history(
            start=start, interval="1d", auto_adjust=True, actions=False
        )
        if hist is None or hist.empty or "Close" not in hist:
            return pd.DataFrame()
        return hist[["Close"]].dropna()
    except Exception:
        return pd.DataFrame()


def refresh_due_recommendation_outcomes(max_records: int = 12) -> int:
    """Evaluate mature recommendations without changing their original snapshot."""
    recs = get_recommendation_records(limit=500)
    if recs.empty:
        return 0
    existing = get_recommendation_outcomes(limit=5000)
    existing_keys = set()
    if not existing.empty:
        existing_keys = set(zip(existing["record_id"].astype(str), existing["horizon"].astype(str)))

    now = pd.Timestamp.now(tz="UTC")
    # Oldest first: they are most likely to have due outcomes.
    work = recs.sort_values("captured_date").copy()
    evaluated_rows: list[dict[str, Any]] = []
    checked = 0
    for _, rec in work.iterrows():
        if checked >= int(max_records):
            break
        horizon_type = str(rec.get("horizon_type"))
        wanted = ["1m","3m","6m"] if horizon_type == "short" else ["6m","1y","2y"]
        if all((str(rec["record_id"]), h) in existing_keys for h in wanted):
            continue

        age_days = (now.tz_localize(None).normalize() - pd.Timestamp(str(rec["captured_date"])[:10])).days
        min_age = 28 if horizon_type == "short" else 180
        if age_days < min_age:
            continue

        checked += 1
        hist = fetch_ledger_history(str(rec["symbol"]), str(rec["captured_date"]))
        if hist.empty:
            continue
        rows = evaluate_record_from_history(rec.to_dict(), hist, as_of=now)
        for row in rows:
            if (str(row["record_id"]), str(row["horizon"])) not in existing_keys:
                evaluated_rows.append(row)

    if evaluated_rows:
        save_recommendation_outcomes(evaluated_rows)
    return len(evaluated_rows)


def _cloud_watchlist() -> pd.DataFrame:
    client = _supabase_client(); uid = current_user_id()
    if client is None or not uid:
        return pd.DataFrame(columns=["symbol", "note", "target_price", "signal_score_threshold", "signal_score_move", "signal_daily_drop", "breaker_min_score", "breaker_min_quality", "breaker_min_risk", "breaker_max_score_drop", "added_at"])
    try:
        cols = "symbol,note,target_price,signal_score_threshold,signal_score_move,signal_daily_drop,breaker_min_score,breaker_min_quality,breaker_min_risk,breaker_max_score_drop,added_at"
        res = client.table("watchlist").select(cols).eq("user_id", uid).order("added_at", desc=True).execute()
        return pd.DataFrame(res.data or [], columns=cols.split(","))
    except Exception as exc:
        # Backward-compatible read if v2.21 Supabase migration has not been run yet.
        try:
            legacy_cols = "symbol,note,target_price,signal_score_threshold,signal_score_move,signal_daily_drop,added_at"
            res = client.table("watchlist").select(legacy_cols).eq("user_id", uid).order("added_at", desc=True).execute()
            df = pd.DataFrame(res.data or [], columns=legacy_cols.split(","))
            for col in ["breaker_min_score", "breaker_min_quality", "breaker_min_risk", "breaker_max_score_drop"]:
                df[col] = 0.0
            st.session_state["bq_case_breaker_migration_needed"] = True
            return df
        except Exception:
            st.session_state["bq_cloud_error"] = str(exc)
            return pd.DataFrame(columns=["symbol", "note", "target_price", "signal_score_threshold", "signal_score_move", "signal_daily_drop", "breaker_min_score", "breaker_min_quality", "breaker_min_risk", "breaker_max_score_drop", "added_at"])


def get_watchlist() -> pd.DataFrame:
    if cloud_enabled() and current_user_id():
        return _cloud_watchlist()
    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query("SELECT symbol, note, target_price, signal_score_threshold, signal_score_move, signal_daily_drop, breaker_min_score, breaker_min_quality, breaker_min_risk, breaker_max_score_drop, added_at FROM watchlist ORDER BY added_at DESC", conn)


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
    breaker_min_score: float = 0.0,
    breaker_min_quality: float = 0.0,
    breaker_min_risk: float = 0.0,
    breaker_max_score_drop: float = 0.0,
) -> None:
    target = None if target_price is None or not np.isfinite(target_price) or target_price <= 0 else float(target_price)
    score_threshold = float(np.clip(signal_score_threshold, 0, 100))
    score_move = float(np.clip(signal_score_move, 1, 50))
    daily_drop = float(np.clip(signal_daily_drop, 1, 50))
    breaker_min_score = float(np.clip(breaker_min_score, 0, 100))
    breaker_min_quality = float(np.clip(breaker_min_quality, 0, 100))
    breaker_min_risk = float(np.clip(breaker_min_risk, 0, 100))
    breaker_max_score_drop = float(np.clip(breaker_max_score_drop, 0, 100))
    client = _supabase_client(); uid = current_user_id()
    payload = {
        "note": note.strip(), "target_price": target,
        "signal_score_threshold": score_threshold,
        "signal_score_move": score_move,
        "signal_daily_drop": daily_drop,
        "breaker_min_score": breaker_min_score,
        "breaker_min_quality": breaker_min_quality,
        "breaker_min_risk": breaker_min_risk,
        "breaker_max_score_drop": breaker_max_score_drop,
    }
    if client is not None and uid:
        try:
            client.table("watchlist").update(payload).eq("user_id", uid).eq("symbol", symbol).execute()
        except Exception as exc:
            # Preserve existing watchlist edits on an older Supabase schema, but case-breakers
            # require the v2.21 migration before they can be stored in the cloud.
            legacy_payload = {k: payload[k] for k in ["note", "target_price", "signal_score_threshold", "signal_score_move", "signal_daily_drop"]}
            client.table("watchlist").update(legacy_payload).eq("user_id", uid).eq("symbol", symbol).execute()
            st.session_state["bq_case_breaker_migration_needed"] = True
            st.session_state["bq_cloud_error"] = f"Case-breaker-regler kunde inte sparas i molnet ännu: {exc}"
        return
    init_db()
    with _db_connect() as conn:
        conn.execute(
            "UPDATE watchlist SET note=?, target_price=?, signal_score_threshold=?, signal_score_move=?, signal_daily_drop=?, breaker_min_score=?, breaker_min_quality=?, breaker_min_risk=?, breaker_max_score_drop=? WHERE symbol=?",
            (note.strip(), target, score_threshold, score_move, daily_drop, breaker_min_score, breaker_min_quality, breaker_min_risk, breaker_max_score_drop, symbol),
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


def get_score_history(symbol: str, profile: str) -> pd.DataFrame:
    """Return chronological stored snapshots for Case Journal. Gracefully supports older schemas."""
    client = _supabase_client(); uid = current_user_id()
    fields = "score,valuation,quality,setup,income,risk,coverage,captured_date,created_at"
    columns = ["score", "valuation", "quality", "setup", "income", "risk", "coverage", "captured_date", "created_at"]
    try:
        if client is not None and uid:
            try:
                data = client.table("score_history").select(fields).eq("user_id", uid).eq("symbol", symbol).eq("profile", profile).order("captured_date").execute().data or []
            except Exception:
                data = client.table("score_history").select("score,captured_date,created_at").eq("user_id", uid).eq("symbol", symbol).eq("profile", profile).order("captured_date").execute().data or []
            return pd.DataFrame(data)
        init_db()
        with _db_connect() as conn:
            rows = conn.execute(
                "SELECT score,valuation,quality,setup,income,risk,coverage,substr(captured_at,1,10),captured_at FROM score_history WHERE symbol=? AND profile=? ORDER BY captured_at",
                (symbol, profile),
            ).fetchall()
        return pd.DataFrame(rows, columns=columns)
    except Exception:
        return pd.DataFrame(columns=columns)


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


def plain_finance_text(value: Any) -> str:
    """Make model-generated finance labels readable without changing calculations."""
    text = str(value if value is not None else "—")
    replacements = [
        ("value trap", "värdefälla"),
        ("Value Trap", "Risk för värdefälla"),
        ("mispricing", "möjlig felprissättning"),
        ("Mispricing", "Prisbedömning"),
        ("inflection", "förändring i utvecklingen"),
        ("Inflection", "Förändring i utvecklingen"),
        ("katalysator", "händelse som kan ändra marknadens syn"),
        ("Katalysator", "Händelse som kan ändra marknadens syn"),
        ("estimatrevideringar", "ändrade vinstprognoser från analytiker"),
        ("estimatrevidering", "ändrad vinstprognos från analytiker"),
        ("EPS-estimatrevideringar", "ändringar i analytikernas vinstprognoser per aktie"),
        ("EPS-estimat", "vinstprognos per aktie"),
        ("EPS", "vinst per aktie"),
        ("FCF", "fritt kassaflöde"),
        ("CAGR", "genomsnittlig årlig förändring"),
        ("evidens", "underlag"),
        ("Evidence", "Underlag"),
        ("Confidence", "Hur bra underlaget är"),
        ("case-breaker", "sak som skulle få bedömningen att ändras"),
        ("Case-breaker", "Sak som skulle få bedömningen att ändras"),
        ("gate", "kontroll"),
        ("Gate", "Kontroll"),
        ("bear", "svagt scenario"),
        ("Bear", "Svagt scenario"),
        ("base", "grundscenario"),
        ("Base", "Grundscenario"),
        ("bull", "starkt scenario"),
        ("Bull", "Starkt scenario"),
        ("hurdle", "krav"),
        ("Hurdle", "Krav"),
        ("proxy", "ungefärligt mått"),
        ("Proxy", "Ungefärligt mått"),
        ("momentum", "kursstyrka den senaste tiden"),
        ("Momentum", "Kursstyrka den senaste tiden"),
    ]
    for old,new in replacements:
        text=text.replace(old,new)
    return text


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
**Största fall från en tidigare topp:** {beginner_term("drawdown")}.  
**Vinst/förlust-kvot:** {beginner_term("profit factor")}.  
**ATR:** {beginner_term("ATR")}.  
**Hur mycket kursen svänger:** {beginner_term("volatilitet")}.  
**Hur lätt aktien är att köpa och sälja:** {beginner_term("likviditet")}.  
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
            qrp = _num(r.get("QRP Score"))
            if qrp >= 75:
                st.success("Enkelt förklarat: bolaget ser just nu ut att kombinera god kvalitet med ett ganska rimligt pris. Det är värt en djupare kontroll, inte ett automatiskt köp.")
            elif qrp >= 60:
                st.info("Enkelt förklarat: flera delar ser bra ut, men pris, kvalitet eller risk är inte tillräckligt starka för ett tydligt grönt ljus ännu.")
            else:
                st.warning("Enkelt förklarat: Borsify ser för många frågetecken i pris, kvalitet eller risk för att kalla detta ett starkt långsiktigt fynd just nu.")


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
    combo_series = ideas.get("Kombinationssignal", pd.Series(dtype=str)).astype(str)
    strong_combos = int(combo_series.isin(["Ovanligt intressant kombination", "Kvalitetsbolag i fokus", "Möjlig återhämtningsidé", "Kortsiktigt läge i fokus"]).sum())
    st.caption(f"{len(ideas)} aktier matchades · {passed} klarar Borsifys första kontroll · {strong_combos} har en tydlig kombination av extern uppmärksamhet och Borsify-data. Upptäcktsstyrka betyder hur brett och nyligen aktien nämnts – inte förväntad avkastning.")

    if strong_combos:
        st.markdown("### Kombinationer värda att läsa först")
        st.write("Här lyfts bara aktier där ett externt uppslag sammanfaller med något som redan syns i Borsifys egna siffror. Media eller forum får fortfarande **inte** höja Borsify Score.")
        combo_view = ideas[combo_series.isin(["Ovanligt intressant kombination", "Kvalitetsbolag i fokus", "Möjlig återhämtningsidé", "Kortsiktigt läge i fokus"])].head(5)
        for _, cr in combo_view.iterrows():
            with st.container(border=True):
                cc1, cc2 = st.columns([3.5, 1])
                cc1.markdown(f"**{cr.get('Namn','')} · {cr.get('Ticker','')}**")
                cc1.write(f"**{cr.get('Kombinationssignal','')}** — {cr.get('Kombinationsförklaring','')}")
                event = str(cr.get("Huvudhändelse", "Övrigt / oklart"))
                cc1.caption(f"Varför aktien syns just nu: **{event}**")
                impact = str(cr.get("Case Impact", "Oklart om caset förändrats"))
                cc1.caption(f"Påverkan på caset: **{impact}**")
                prio = _num(cr.get('Idéprioritet'))
                cc2.metric("Läs först", f"{prio:.0f}/100" if np.isfinite(prio) else "—")
        st.caption("Läs först är endast en kö-prioritering för externa uppslag: 72 % Borsify Score + 28 % upptäcktsstyrka. Den är inte en ny investeringsscore eller avkastningsprognos.")

    st.markdown("### Alla matchade uppslag")
    for _, r in ideas.head(12).iterrows():
        status = str(r.get("Borsify-granskning", ""))
        with st.container(border=True):
            a, b, c = st.columns([3.2, 1, 1.25])
            a.markdown(f"### {r.get('Namn','')} · {r.get('Ticker','')}")
            media_sources = int(r.get("Mediekällor", 0) or 0)
            forum_sources = int(r.get("Forumkällor", 0) or 0)
            pulse = str(r.get("Mediepuls", ""))
            recent24 = int(r.get("Omnämnanden 24h", 0) or 0)
            pulse_text = f" · {pulse}" if pulse else ""
            a.caption(f"{int(r.get('Antal omnämnanden',0))} uppslag · {recent24} senaste 24 h · {media_sources} mediekälla/källor · {forum_sources} forumkälla/källor{pulse_text}")
            b.metric("Borsify", f"{_num(r.get('Borsify Score')):.0f}/100" if np.isfinite(_num(r.get('Borsify Score'))) else "—")
            c.metric("Kontroll", status)
            st.write(str(r.get("Förklaring", "")))
            event_label = str(r.get("Huvudhändelse", "Övrigt / oklart"))
            event_expl = str(r.get("Händelseförklaring", ""))
            st.markdown(f"**Varför uppmärksammas aktien?** {event_label}")
            if event_expl:
                st.caption(event_expl)
            impact_label = str(r.get("Case Impact", "Oklart om caset förändrats"))
            impact_expl = str(r.get("Case Impact Förklaring", ""))
            impact_level_num = _num(r.get("Case Impact Nivå", 0))
            impact_level = int(impact_level_num) if np.isfinite(impact_level_num) else 0
            if impact_level >= 3 and "risk" in impact_label.lower():
                st.warning(f"**Ändrar detta investeringscaset? {impact_label}.** {impact_expl}")
            elif impact_level >= 3:
                st.info(f"**Ändrar detta investeringscaset? {impact_label}.** {impact_expl}")
            else:
                st.caption(f"**Ändrar detta investeringscaset? {impact_label}.** {impact_expl}")
            combo_label = str(r.get("Kombinationssignal", ""))
            combo_expl = str(r.get("Kombinationsförklaring", ""))
            if combo_label and combo_label != "Ingen särskild kombination":
                st.success(f"**{combo_label}:** {combo_expl}")
            else:
                st.caption(combo_expl)
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
                        event_types = h.get("event_types") or []
                        event_text = " / ".join(str(x) for x in event_types[:2])
                        label = f"{source} · {category}" if category else source
                        if event_text:
                            label += f" · {event_text}"
                        if link.startswith("http"):
                            st.markdown(f"- [{title}]({link}) · {label}")
                        else:
                            st.write(f"• {title} · {label}")

    with st.expander("Så ska mediabevakningen tolkas"):
        st.write("Borsify försöker hitta **uppslag**, inte följa flocken. Mediepuls visar om uppmärksamheten har ökat det senaste dygnet jämfört med den senaste veckan. Det är inte ett köp- eller säljsentiment. Flera oberoende mediekällor ger högre upptäcktsstyrka än många inlägg från ett enda forum. Ett bolag kan ändå sorteras bort direkt om nyckeltalen är svaga. Spekulativa forumkällor får lägre vikt och kan aldrig ensamma ge maximal upptäcktsstyrka.")
        st.write("**Kombinationssignal** betyder bara att två separata saker råkar sammanfalla: Borsifys egen analys ser något intressant och externa källor har samtidigt börjat uppmärksamma bolaget. Det gör aktien värd att läsa om tidigare i kön, men det är fortfarande ingen köpsignal.")
        st.write("**Varför uppmärksammas aktien?** Borsify klassificerar rubrikerna i enkla händelsetyper som rapport, prognos, riktkurs, insiderhandel, order, förvärv, utdelning, emission eller vinstvarning. Klassningen hjälper dig att förstå vad du ska läsa först – den avgör inte om nyheten är positiv eller negativ.")
        st.write("**Ändrar detta investeringscaset?** Case Impact skiljer händelser som kan ändra bolagets vinst, risk eller finansiering från sådant som främst är åsikter eller marknadsbrus. När rubriken inte räcker för att avgöra riktningen säger Borsify uttryckligen att informationen måste verifieras i originalkällan.")
        st.caption("Bevakningen bygger på publika flöden. Paywall-innehåll läses inte och rubrikklassningen är en första sortering, inte ett verifierat faktapåstående om bolaget. Läs originalkällan innan du drar slutsatser.")


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
                    price_text = fmt_price_with_sek(r)
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
    c2.metric("Pris", fmt_price_with_sek(row), fmt_pct(row.get("Dagsförändring")))
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
        if coverage < .60: st.warning(f"Underlaget är bara {coverage:.0%} komplett. Flera viktiga bolagsuppgifter saknas, så Borsifys betyg är mer osäkert än vanligt.")
        else: st.caption(f"Datatäckning i kärnmodellen: {coverage:.0%}.")
    price_date = str(row.get("Prisdatum") or "—")
    fundamental_at = str(row.get("Fundamental hämtad") or "—")
    st.caption(f"Senaste data · kurs från: {price_date} · bolagsdata hämtad: {fundamental_at}. Tiden visar när Borsify hämtade uppgifterna. Vissa siffror kan komma från en äldre bolagsrapport.")

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


def render_quick_change_target(scored: pd.DataFrame, signal_history: pd.DataFrame, profile: str) -> None:
    """Inline destination for actions from Nytt sedan sist.

    Streamlit tabs cannot be switched reliably from a button, so the destination
    is rendered immediately on the overview instead of pretending navigation occurred.
    """
    ticker = str(st.session_state.get("bq_quick_open_ticker") or "").strip()
    mode = str(st.session_state.get("bq_quick_open_mode") or "").strip()
    if not ticker or not mode:
        return
    with st.container(border=True):
        h1, h2 = st.columns([5, 1])
        h1.markdown(f"### Öppnad från Nytt sedan sist · {ticker}")
        if h2.button("Stäng", key=f"quick_close_{ticker}_{mode}", use_container_width=True):
            st.session_state.pop("bq_quick_open_ticker", None)
            st.session_state.pop("bq_quick_open_mode", None)
            st.rerun()

        row_df = scored[scored["Ticker"].astype(str) == ticker].head(1) if not scored.empty else pd.DataFrame()
        if mode == "analysis":
            if row_df.empty:
                st.info("Aktien finns inte i den aktuella analyskörningen. Byt marknad/universum eller öppna den från bevakningslistan.")
            else:
                render_detail(row_df.iloc[0], profile, key_prefix=f"quick_{ticker}")
        elif mode == "journal":
            if row_df.empty:
                st.info("Case Journal kan visas när aktien finns i den aktuella analysen eller bevakningen.")
            else:
                wr = row_df.iloc[0]
                hist = get_score_history(ticker, profile)
                current_case = {
                    "score": _num(wr.get("Borsify Score")),
                    "valuation": _num(wr.get("Värdering")),
                    "quality": _num(wr.get("Kvalitet")),
                    "setup": _num(wr.get("Marknadsläge")),
                    "income": _num(wr.get("Utdelning")),
                    "risk": _num(wr.get("Risk")),
                    "coverage": _num(wr.get("Datatäckning")),
                }
                journal = assess_case_change(hist, current_case)
                st.markdown("**Case Journal · vad har förändrats?**")
                delta = _num(journal.get("score_delta"))
                delta_text = f"{delta:+.1f} poäng sedan start" if np.isfinite(delta) else "historiken byggs upp"
                st.write(f"**{journal.get('status', 'Historiken byggs upp')}** · {delta_text}")
                for change in journal.get("changes", []):
                    st.write(f"• {change}")
                jt = journal_table(hist)
                if len(jt) >= 2:
                    st.dataframe(jt, use_container_width=True, hide_index=True)
                else:
                    st.caption("Efter fler sparade analyser visas utvecklingen här.")
        elif mode == "signal":
            hist = signal_history[signal_history["symbol"].astype(str) == ticker].copy() if not signal_history.empty else pd.DataFrame()
            st.markdown("**Signalhistorik**")
            if hist.empty:
                st.info("Ingen sparad signalhistorik hittades för aktien.")
            else:
                for _, sig in hist.sort_values(["created_at"], ascending=False).head(12).iterrows():
                    read_label = "Läst" if bool(sig.get("is_read")) else "Oläst"
                    st.markdown(f"**{sig.get('kind','Signal')} · {sig.get('occurred_date','')} · {read_label}**")
                    st.write(str(sig.get("text") or ""))



def _market_label_for_ticker(symbol: str) -> str:
    s = str(symbol or "").upper()
    suffix_map = {
        ".ST": "Sverige", ".CO": "Danmark", ".OL": "Norge", ".HE": "Finland",
        ".DE": "Tyskland", ".L": "Storbritannien", ".TO": "Kanada", ".V": "Kanada",
        ".PA": "Frankrike", ".AS": "Nederländerna", ".BR": "Belgien",
        ".MI": "Italien", ".MC": "Spanien", ".SW": "Schweiz", ".LS": "Portugal",
    }
    for suffix, country in suffix_map.items():
        if s.endswith(suffix):
            return country
    return "USA"


def render_horizon_toplists(scored: pd.DataFrame, market: str) -> None:
    st.markdown("## 🌍 Borsify Topplistor")
    st.caption(
        "Borsify visar bara aktier som klarar köpkraven och har ett tillräckligt bra beslutsunderlag. "
        "Ett högt aktiebetyg räcker alltså inte om viktig data saknas eller riskbilden är oklar. "
        "När marknaden är svag höjs köpkraven automatiskt. En stark marknad får däremot aldrig sänka grundkraven. "
        "Varje kort förklarar varför aktien är intressant, "
        "varför den är aktuell nu, den största risken och vad som skulle få Borsify att ändra uppfattning. "
        "För kortare handel visas också relativ styrka och möjlig uppsida i förhållande till risk. "
        "Om ingen aktie är tillräckligt stark visas inget köp."
    )
    avanza_catalog = load_avanza_universe(AVANZA_UNIVERSE_PATH)
    if not avanza_catalog.empty:
        summary = breadth_summary(avanza_catalog)
        with st.expander(f"Marknadstäckning · {summary['total']} aktier · {summary['countries']} länder", expanded=False):
            st.dataframe(coverage_table(avanza_catalog), use_container_width=True, hide_index=True)
            st.caption("Kärna = tidigare kuraterat universum. Bred tillägg = nya kandidater i Avanza Universe v1. Katalogen är inte verifierad som en komplett Avanza-lista ännu.")
    if "Universe QC" in scored.columns:
        qsum = quality_summary(scored)
        with st.expander("✅ Kontroll av börsdata · denna körning", expanded=False):
            q1,q2,q3 = st.columns(3)
            q1.metric("Verifierade", qsum["verified"])
            q2.metric("Delvis verifierade", qsum["partial"])
            q3.metric("Hårt exkluderade", int(st.session_state.get("bq_qc_hard_rejected", 0)))
            country_q = scored.copy()
            country_q["Land"] = country_q["Ticker"].astype(str).map(_market_label_for_ticker)
            rows=[]
            for country,g in country_q.groupby("Land"):
                qs=quality_summary(g)
                rows.append({
                    "Land":country,
                    "Verifierade":qs["verified"],
                    "Delvis verifierade":qs["partial"],
                    "Analyserbara":qs["verified"]+qs["partial"],
                })
            if rows:
                st.dataframe(pd.DataFrame(rows).sort_values(["Analyserbara","Land"],ascending=[False,True]), use_container_width=True, hide_index=True)
            st.caption(
                "Den här kontrollen bedömer bara om Borsify har tillräckligt bra data för att jämföra aktien med andra. "
                "Den säger inte om aktien är ett bra köp. Aktier med trasig kursdata eller för kort historik tas bort automatiskt."
            )
    persistent_qc = get_universe_qc_states()
    if not persistent_qc.empty:
        psum = quarantine_summary(persistent_qc)
        with st.expander("🛡️ Datakontroll över tid · fel & karantän", expanded=False):
            p1,p2,p3,p4 = st.columns(4)
            p1.metric("Tickers med historik", psum["total"])
            p2.metric("I karantän", psum["quarantined"])
            p3.metric("Med felserie", psum["failing"])
            p4.metric("Hoppades över nu", int(st.session_state.get("bq_qc_skipped_quarantine", 0)))
            health_ratio = float(st.session_state.get("bq_qc_scan_health", 1.0))
            provider_ok = bool(st.session_state.get("bq_qc_provider_healthy", True))
            provider_rule = str(st.session_state.get("bq_qc_provider_rule", ""))
            st.caption(
                f"Senaste datahämtningen lyckades för {health_ratio:.0%} av aktierna. "
                + ("Tillräckligt många fungerade för att Borsify ska kunna bedöma enskilda fel."
                   if provider_ok else
                   "Så få aktier fungerade att Borsify misstänker problem hos datakällan. Saknade aktier får därför ingen felmarkering eller karantän på grund av den här körningen.")
                + (f" Säkerhetsregel: {provider_rule}." if provider_rule else "")
            )
            quarantine_rows = persistent_qc[persistent_qc.apply(is_quarantined, axis=1)].copy()
            if not quarantine_rows.empty:
                show = quarantine_rows[[
                    "symbol","failure_streak","last_verified_at","last_reason","quarantine_until"
                ]].rename(columns={
                    "symbol":"Ticker","failure_streak":"Fel i följd",
                    "last_verified_at":"Senast verifierad","last_reason":"Senaste problem",
                    "quarantine_until":"Karantän till",
                })
                st.dataframe(show, use_container_width=True, hide_index=True)
            else:
                st.success("Ingen ticker ligger i aktiv karantän.")
            st.caption(
                "En aktie måste misslyckas vid tre separata dagar innan Borsify tillfälligt slutar försöka läsa in den i sju dagar. "
                "Om problemet verkar ligga hos datakällan räknas det inte som ett fel på aktien."
            )
    if st.session_state.get("bq_qc_state_migration_needed"):
        st.warning("Supabase saknar v2.45-tabellerna för persistent Universe QC. Kör den nya SQL-migreringen för permanent molnlagring.")
    if market == "Alla marknader":
        st.caption(
            "Topp 3 över alla marknader Borsify stöder just nu. "
            "Datatäckningen omfattar Borsifys 15 Avanza-inspirerade direktmarknader. "
            "Listan är ännu inte en komplett scanning av varje aktie som kan handlas hos Avanza."
        )
    else:
        st.warning(
            f"Du har filtrerat marknaden till {market}. Topplistorna nedan avser därför {market}. "
            "Välj **Alla marknader** i vänstermenyn för Borsifys globala ranking."
        )

    available_countries = sorted({
        _market_label_for_ticker(sym) for sym in scored.get("Ticker", pd.Series(dtype=str)).astype(str).tolist()
    })
    selected_countries = st.multiselect(
        "Filtrera Topplistor på land",
        options=available_countries,
        default=available_countries,
        help="Välj ett eller flera länder. Alla fyra Top 3-listorna räknas om direkt inom de valda länderna.",
        key="toplist_country_filter",
    )
    if selected_countries:
        toplist_base = scored[
            scored["Ticker"].astype(str).map(_market_label_for_ticker).isin(selected_countries)
        ].copy()
    else:
        toplist_base = scored.iloc[0:0].copy()
        st.info("Välj minst ett land för att visa Topplistor.")

    sections = [
        ("⚡ Bästa köp · 1–2 dagar", "day", "Daytrade Score",
         "Mycket kort sikt baserad på dagsdata – inte en realtids- eller intradagssignal. Borsify vill se styrka, tillräcklig handel och en tydlig riskplan, men försöker samtidigt undvika aktier som redan rusat så mycket att ett nytt köp riskerar att komma för sent."),
        ("📈 Bästa köp · 1 vecka–3 månader", "medium", "Mellan Score",
         "Borsify tittar på hur kursen gått de senaste 1–3 månaderna och väger ihop det med bolagets kvalitet, prisnivå och risk. En aktie som redan gått extremt långt kan stoppas trots ett högt betyg."),
        ("🏗️ Bästa köp · 1–5 år", "long", "Lång Score",
         "För flera års ägande väger bolagets kvalitet, prisnivå och risk betydligt tyngre än korta kursrörelser."),
        ("♾️ Bästa köp · mycket lång sikt", "lifetime", "Livstid Score",
         "Här krävs extra hög och uthållig kvalitet, god lönsamhet och en robust ekonomi. Det betyder inte att aktien ska ägas för alltid – den måste fortsätta förtjäna sin plats."),
    ]
    for title, horizon, score_col, caption in sections:
        st.markdown(f"### {title}")
        st.caption(caption)
        top3 = top_three(toplist_base, horizon)
        if top3.empty:
            st.info(
                "Inget köpcase är både tillräckligt starkt och tillräckligt väl underbyggt för den här horisonten just nu. "
                "Borsify lämnar hellre platsen tom än visar ett case med för svagt underlag."
            )
            continue
        cols = st.columns(3)
        for rank, (col, (_, row)) in enumerate(zip(cols, top3.iterrows()), start=1):
            with col:
                with st.container(border=True):
                    st.markdown(f"### {rank}. {row.get('Namn', row.get('Ticker'))}")
                    st.caption(f"{row.get('Ticker','—')} · {_market_label_for_ticker(row.get('Ticker',''))}")
                    price = _num(row.get("Pris"))
                    ccy = str(row.get("Valuta","") or "")
                    if np.isfinite(price):
                        st.markdown(f"**{price:.2f} {ccy}**")
                    score = _num(row.get(score_col))
                    if np.isfinite(score):
                        st.metric("Borsifys huvudbetyg", f"{score:.0f}/100")
                    if str(row.get("Köpfilter","")) == "KÖPCASE":
                        st.success("KÖPCASE")

                    readiness = _num(row.get("Case Readiness"))
                    readiness_status = str(row.get("Case Readiness status","") or "")
                    if readiness_status:
                        st.markdown("**Hur bra är beslutsunderlaget?**")
                        if np.isfinite(readiness) and readiness >= 78:
                            st.success(readiness_status)
                        else:
                            st.info(readiness_status)
                        st.caption(
                            "Detaljpoängen för underlaget finns under ”Visa siffrorna bakom bedömningen”."
                        )

                    trust_status = str(row.get("Data Trust status","") or "")
                    if trust_status:
                        st.markdown("**Datakoll**")
                        if trust_status == "GOTT UNDERLAG":
                            st.success(trust_status)
                        elif trust_status == "STOPP":
                            st.error(trust_status)
                        else:
                            st.warning(trust_status)
                        st.caption(
                            f"Källa: {row.get('Data Trust källa','Yahoo Finance via yfinance')} · "
                            f"kursdatum: {row.get('Data Trust kursdatum','—')} · "
                            f"bolagsdata hämtad: {row.get('Data Trust bolagsdata hämtad','—')}"
                        )
                        trust_warn = str(row.get("Data Trust varningar","") or "")
                        if trust_warn and trust_warn != "inga tydliga datavarningar":
                            st.caption("Datavarning: " + trust_warn)

                    st.markdown("**Varför köpa?**")
                    st.write(str(row.get("Varför köpa","—")))
                    st.markdown("**Varför just nu?**")
                    st.write(str(row.get("Varför nu","—")))
                    st.markdown("**Största risken**")
                    st.write(str(row.get("Största risk","—")))
                    st.markdown("**Vad skulle få Borsify att ändra sig?**")
                    st.write(str(row.get("Vad ändrar Borsifys syn","—")))

                    if horizon in {"day","medium"}:
                        liq_status = str(row.get("Likviditetskontroll","") or "")
                        liq_text = str(row.get("Likviditet förklaring","") or "")
                        if liq_status:
                            st.markdown("**Går aktien rimligt att handla?**")
                            if liq_status == "GODTAGBAR HANDEL":
                                st.success(liq_status)
                            elif liq_status == "TUNNARE HANDEL":
                                st.warning(liq_status)
                            else:
                                st.error(liq_status)
                            if liq_text:
                                st.write(liq_text)
                            st.caption(
                                "Borsify använder dagsdata här – inte realtid. Aktuell spread och orderboksdjup kan därför inte verifieras."
                            )

                    market_status = str(row.get("Marknadsläge","") or "")
                    market_text = str(row.get("Marknadsläge text","") or "")
                    if market_status:
                        st.markdown("**Marknadsläget**")
                        if market_status == "STARK":
                            st.success("STARK MARKNAD")
                        elif market_status in {"SVAG","MYCKET SVAG"}:
                            st.warning(market_status + " MARKNAD" if market_status == "SVAG" else "MYCKET SVAG MARKNAD")
                        elif market_status == "NEUTRAL":
                            st.info("NEUTRAL MARKNAD")
                        else:
                            st.info("FÖR LITE UNDERLAG")
                        if market_text:
                            st.write(market_text)

                    if horizon in {"day","medium"}:
                        rel_score = _num(row.get("Relativ styrka"))
                        rel_text = str(row.get("Relativ styrka text","") or "")
                        rel_expl = str(row.get("Relativ styrka förklaring","") or "")
                        rel_basis = str(row.get("Relativ styrka underlag","") or "")
                        st.markdown("**Jämfört med marknaden och sektorn**")
                        if rel_score >= 68:
                            st.success(rel_text or "Starkare än jämförelsen")
                        elif rel_score < 45:
                            st.warning(rel_text or "Svagare än jämförelsen")
                        else:
                            st.info(rel_text or "Ungefär i nivå med jämförelsen")
                        if rel_expl:
                            st.write(rel_expl)
                        if rel_basis:
                            st.caption("Jämförelsen bygger på " + rel_basis + " i den aktuella Borsify-körningen.")

                    rr_plan = row.get("RR plan") if isinstance(row.get("RR plan"), dict) else {}
                    rr_status = str(rr_plan.get("RR status","") or "")
                    if horizon in {"day","medium"} and rr_status:
                        st.markdown("**Risk jämfört med möjlig uppsida**")
                        if rr_status in {"ATTRAKTIVT","GODKÄNT"}:
                            st.success(f"{rr_status}")
                        elif rr_status in {"SVAGT","DÅLIGT"}:
                            st.warning(f"{rr_status}")
                        else:
                            st.info(rr_status)

                        entry_low = _num(rr_plan.get("Entry låg"))
                        entry_high = _num(rr_plan.get("Entry hög"))
                        stop_level = _num(rr_plan.get("Stop"))
                        target1 = _num(rr_plan.get("Mål 1"))
                        target2 = _num(rr_plan.get("Mål 2"))
                        rr1 = _num(rr_plan.get("RR 1"))
                        ccy = str(row.get("Valuta","") or "")
                        if np.isfinite(entry_low) and np.isfinite(entry_high):
                            st.write(f"Rimligt köpområde enligt modellen: **{entry_low:.2f}–{entry_high:.2f} {ccy}**")
                        if np.isfinite(stop_level):
                            st.write(f"Analysen anses fel under ungefär: **{stop_level:.2f} {ccy}**")
                        if np.isfinite(target1):
                            target_text=f"Första tidigare motståndsnivå: **{target1:.2f} {ccy}**"
                            if np.isfinite(target2):
                                target_text += f" · nästa: **{target2:.2f} {ccy}**"
                            st.write(target_text)
                        if np.isfinite(rr1):
                            st.write(f"Möjlig uppsida per riskenhet: **{rr1:.1f} gånger**")
                        st.caption(str(rr_plan.get("RR förklaring","")))

                    buy_position = str(row.get("Köpläge","") or "")
                    if buy_position == "VAR FÖRSIKTIG":
                        st.warning("⚠️ **Har aktien redan gått långt?** " + str(row.get("Köplägesförklaring","")))
                    elif buy_position == "FÖR SENT ATT JAGA?":
                        st.warning("⚠️ **Risk att köpa efter en stor uppgång:** " + str(row.get("Köplägesförklaring","")))

                    with st.expander("Visa siffrorna bakom bedömningen", expanded=False):
                        st.metric("Borsifys betyg för tidshorisonten", f"{score:.0f}/100" if np.isfinite(score) else "—")
                        gate_support = str(row.get("Köpfilter stöd","") or "")
                        if gate_support:
                            st.caption(f"Det som stödjer köpcaset: {gate_support}")
                        readiness_strengths = str(row.get("Case Readiness styrkor","") or "")
                        readiness_gaps = str(row.get("Case Readiness luckor","") or "")
                        readiness_points = str(row.get("Case Readiness datapunkter","") or "")
                        readiness_confirm = str(row.get("Case Readiness bekräftelser","") or "")
                        if readiness_strengths:
                            st.caption("Styrkor i underlaget: " + readiness_strengths)
                        if readiness_gaps and readiness_gaps != "inga större luckor upptäckta":
                            st.caption("Luckor i underlaget: " + readiness_gaps)
                        if readiness_points or readiness_confirm:
                            st.caption(
                                "Underlagskontroll: "
                                + (f"{readiness_points} viktiga datapunkter" if readiness_points else "")
                                + (f" · {readiness_confirm} delar bekräftar caset" if readiness_confirm else "")
                            )
                        st.write(str(row.get("Horisontförklaring","—")))
                        qc = str(row.get("Universe QC","") or "")
                        if qc:
                            qc_score = _num(row.get("Universe QC Score"))
                            st.caption(f"Datakvalitet: {qc}" + (f" · {qc_score:.0f}/100" if np.isfinite(qc_score) else ""))
                        if horizon == "day":
                            st.caption(
                                f"Idag {fmt_pct(row.get('Dagsförändring'))} · handelsaktivitet {fmt_num(row.get('Volymkvot'),2)} gånger normal · RSI {fmt_num(row.get('RSI14'),0)}"
                            )
                        elif horizon == "medium":
                            st.caption(f"1 månad {fmt_pct(row.get('1 mån'))} · 3 månader {fmt_pct(row.get('3 mån'))}")
                        if horizon in {"day","medium"}:
                            liq_turnover = _num(row.get("Likviditet omsättning MSEK"))
                            if np.isfinite(liq_turnover):
                                st.caption(f"Normal daglig handelsomsättning: cirka {liq_turnover:.1f} MSEK.")
                            liq_limit = str(row.get("Likviditet begränsning","") or "")
                            if liq_limit:
                                st.caption("Begränsning: " + liq_limit)

                        market_required = _num(row.get("Marknadskrav"))
                        market_adjustment = _num(row.get("Marknadsläge justering"))
                        if np.isfinite(market_required):
                            market_bits=[f"aktuellt köpkrav {market_required:.0f}/100"]
                            if np.isfinite(market_adjustment) and market_adjustment > 0:
                                market_bits.append(f"{market_adjustment:.0f} extra poäng på grund av svag marknad")
                            st.caption("Marknadskontroll: " + " · ".join(market_bits))

                        if horizon in {"day","medium"}:
                            rel_m3 = _num(row.get("Relativ marknad 3 mån"))
                            rel_s3 = _num(row.get("Relativ sektor 3 mån"))
                            sec3 = _num(row.get("Sektorstyrka 3 mån"))
                            rel_bits=[]
                            if np.isfinite(rel_m3):
                                rel_bits.append(f"mot marknaden 3 mån {rel_m3:+.1%}")
                            if np.isfinite(rel_s3):
                                rel_bits.append(f"mot sektorn 3 mån {rel_s3:+.1%}")
                            if np.isfinite(sec3):
                                rel_bits.append(f"sektorn mot marknaden {sec3:+.1%}")
                            if rel_bits:
                                st.caption("Relativ jämförelse: " + " · ".join(rel_bits))

                        if horizon in {"day","medium"} and rr_plan:
                            atr = _num(rr_plan.get("ATR14"))
                            risk_pct = _num(rr_plan.get("Risk %"))
                            rr2 = _num(rr_plan.get("RR 2"))
                            extra=[]
                            if np.isfinite(atr):
                                extra.append(f"normal dagsrörelse {atr:.2f} {ccy}")
                            if np.isfinite(risk_pct):
                                extra.append(f"avstånd till fel-nivå {risk_pct:.1%}")
                            if np.isfinite(rr2):
                                extra.append(f"uppsida/risk till nästa motstånd {rr2:.1f}x")
                            if extra:
                                st.caption(" · ".join(extra))
                        else:
                            st.caption(
                                f"Bolagskvalitet {fmt_num(row.get('Kvalitet'),0)}/100 · Risk {fmt_num(row.get('Risk'),0)}/100 · Prisnivå {fmt_num(row.get('Värdering'),0)}/100"
                            )

        # Also surface the strongest candidates that are close to, but do not yet
        # meet, the real buy requirements. They are never promoted to KÖPCASE.
        near_base = add_horizon_scores(toplist_base)
        near = near_buy_candidates(near_base, horizon, limit=3)
        if not near.empty:
            with st.expander(f"👀 Nära köpsignal · {len(near)} att bevaka", expanded=False):
                st.caption(
                    "Det här är inte köp. Borsify visar aktier som ligger nära de köpkrav som gäller just nu och förklarar vad som fortfarande saknas. "
                    "I en svag marknad kan en aktie därför hamna här trots att den hade klarat de vanliga grundkraven. Aktier med allvarliga risk- eller dataproblem visas inte här."
                )
                for _, candidate in near.iterrows():
                    st.markdown(f"**{candidate.get('Namn', candidate.get('Ticker','—'))} · {candidate.get('Ticker','—')}**")
                    st.write("**Vad saknas?** " + str(candidate.get("Vad saknas","—")))
                    st.caption(
                        f"Borsifys betyg: {fmt_num(candidate.get(score_col),0)}/100 · "
                        f"köpgräns {fmt_num(candidate.get('Köpfilter gräns'),0)}/100"
                    )
                    st.divider()


def _holding_status_style(row: pd.Series) -> list[str]:
    status = str(row.get("Status",""))
    bg = {
        "BEHÅLL": "background-color: rgba(46, 160, 67, 0.20)",
        "BEVAKA": "background-color: rgba(255, 193, 7, 0.22)",
        "VINSTSÄKRA?": "background-color: rgba(255, 152, 0, 0.24)",
        "OMPRÖVA": "background-color: rgba(220, 53, 69, 0.24)",
    }.get(status, "")
    return [bg] * len(row)


def render_holdings_portfolio(scored: pd.DataFrame, profile: str) -> None:
    st.markdown("## 💼 Mina aktieköp · säljkoll")
    st.caption(
        "Lägg in vad du köpt och till vilken kurs. Borsify jämför inköpskursen med dagens data och visar "
        "BEHÅLL, BEVAKA, VINSTSÄKRA? eller OMPRÖVA. Det är en modellbaserad beslutsindikator, inte personlig finansiell rådgivning."
    )

    with st.expander("＋ Lägg till ett aktieköp", expanded=False):
        with st.form("add_holding_form", clear_on_submit=True):
            c1,c2,c3,c4 = st.columns([1.25,1,1,.9])
            symbol = c1.text_input("Ticker", placeholder="t.ex. BUFAB.ST")
            purchase_price = c2.number_input("Köpkurs", min_value=0.0, value=0.0, step=1.0)
            quantity = c3.number_input("Antal", min_value=0.0, value=1.0, step=1.0)
            purchase_date = c4.date_input("Köpdatum")
            note = st.text_input("Anteckning", placeholder="Valfritt")
            submitted = st.form_submit_button("Spara aktieköp", type="primary")
            if submitted:
                if not symbol.strip() or purchase_price <= 0 or quantity <= 0:
                    st.warning("Ange ticker, köpkurs över 0 och antal över 0.")
                else:
                    add_holding(symbol, purchase_price, quantity, purchase_date.isoformat(), note)
                    st.success("Aktieköpet sparades.")
                    st.rerun()

    holdings = get_holdings()
    if holdings.empty:
        st.info("Du har inte lagt in några aktieköp ännu.")
        return

    symbols = holdings["symbol"].astype(str).str.upper().tolist()
    current = scored[scored["Ticker"].astype(str).str.upper().isin(symbols)].copy()
    missing = [s for s in symbols if s not in set(current["Ticker"].astype(str).str.upper())]
    if missing:
        extra_raw, _ = scan_universe(list(dict.fromkeys(missing)))
        if not extra_raw.empty:
            extra_raw, _, _ = add_sek_conversions(extra_raw)
            extra = add_scores(extra_raw, profile)
            current = pd.concat([current, extra], ignore_index=True)

    lookup = {str(r["Ticker"]).upper(): r for _,r in current.iterrows()}
    rows=[]
    for _,h in holdings.iterrows():
        sym=str(h["symbol"]).upper()
        row=lookup.get(sym)
        if row is None:
            rows.append({
                "ID": int(h["holding_id"]), "Aktie": sym, "Köpkurs": h["purchase_price"],
                "Aktuell kurs": np.nan, "Utveckling": np.nan, "Värde": np.nan,
                "Status": "DATA SAKNAS", "Borsify råd": "Aktuell marknadsdata kunde inte hämtas", "Skäl": "—"
            })
            continue
        assessment=assess_holding(h["purchase_price"], row)
        now=_num(row.get("Pris")); qty=_num(h.get("quantity"))
        rows.append({
            "ID": int(h["holding_id"]),
            "Aktie": f"{row.get('Namn',sym)} · {sym}",
            "Köpdatum": h.get("purchase_date",""),
            "Köpkurs": float(h["purchase_price"]),
            "Aktuell kurs": now,
            "Valuta": row.get("Valuta",""),
            "Antal": qty,
            "Utveckling": assessment["Utveckling"],
            "Värde": now*qty if np.isfinite(now) and np.isfinite(qty) else np.nan,
            "Status": assessment["Status"],
            "Borsify råd": assessment["Borsify råd"],
            "Skäl": assessment["Skäl"],
        })
    table=pd.DataFrame(rows)
    display=table.drop(columns=["ID"]).copy()
    if "Utveckling" in display:
        display["Utveckling"] = display["Utveckling"].map(lambda x: "—" if not np.isfinite(_num(x)) else f"{x:+.1%}")
    for col in ["Köpkurs","Aktuell kurs","Värde"]:
        if col in display:
            display[col] = display[col].map(lambda x: "—" if not np.isfinite(_num(x)) else f"{x:,.2f}".replace(",", " "))
    st.dataframe(display.style.apply(_holding_status_style, axis=1), use_container_width=True, hide_index=True)

    with st.expander("Ta bort ett registrerat köp", expanded=False):
        opts={f"{r['Aktie']} · {r.get('Köpdatum','')}": int(r["ID"]) for _,r in table.iterrows()}
        choice=st.selectbox("Välj rad", list(opts), key="holding_delete_choice")
        if st.button("Ta bort köp", key="delete_holding_btn"):
            delete_holding(opts[choice]); st.rerun()

    if st.session_state.get("bq_holdings_migration_needed"):
        st.warning("Supabase saknar holdings-tabellen för v2.41.0. Kör den nya SQL-migreringen för permanent molnsynk.")



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
    market: str,
    benchmark_name: str,
) -> None:
    """Ren startsida: vad är intressant, varför och vad bör jag se upp med?"""
    best = daily_shortlist.iloc[0] if not daily_shortlist.empty else None

    st.markdown("## Dagens bästa möjligheter")
    st.caption(
        "Borsify börjar med högst tre kandidater. Resten av analysen finns längre ned när du behöver den."
    )
    if daily_shortlist.empty:
        st.info("Ingen kandidat är tillräckligt stark i dagens urval.")
    else:
        focus_cases = daily_shortlist.head(3)
        cols = st.columns(len(focus_cases))
        for rank, (col, (_, case)) in enumerate(zip(cols, focus_cases.iterrows()), start=1):
            with col:
                with st.container(border=True):
                    st.caption(f"#{rank} · {case.get('Prioritet','')}")
                    st.markdown(f"### {case.get('Namn', case.get('Ticker',''))}")
                    st.caption(f"{case.get('Ticker','—')} · {case.get('Sektor','—')}")
                    st.metric("Borsify", f"{_num(case.get('Borsify Score')):.0f}/100")
                    st.markdown("**Varför den är intressant**")
                    st.write(str(case.get("Varför idag","—")))
                    st.markdown("**Kontrollera före beslut**")
                    st.write(str(case.get("Kontrollera","—")))
                    st.caption(
                        f"Kursdatum {case.get('Prisdatum','—')} · datakoll {case.get('Data Trust status','—')}"
                    )

    with st.expander("Visa bästa köp efter tidshorisont", expanded=False):
        render_horizon_toplists(scored, market)

    st.divider()
    high_priority = int((daily_shortlist["Prioritet"] == "Hög").sum()) if not daily_shortlist.empty else 0
    today = datetime.now().date().isoformat()
    today_signals = signal_history[signal_history["occurred_date"].astype(str) == today] if not signal_history.empty else pd.DataFrame()

    # Dagens fokus: en kort prioriterad arbetslista som samlar nya kandidater,
    # förändringar i bevakade case och nya Radar-signaler. Den ändrar inga scores.
    watch_changes: list[dict[str, Any]] = []
    if not watch_df.empty:
        for _, wr in watch_df.iterrows():
            sym = str(wr.get("Ticker", ""))
            if not sym:
                continue
            hist = get_score_history(sym, profile)
            current_case = {
                "score": _num(wr.get("Borsify Score")),
                "valuation": _num(wr.get("Värdering")),
                "quality": _num(wr.get("Kvalitet")),
                "setup": _num(wr.get("Marknadsläge")),
                "income": _num(wr.get("Utdelning")),
                "risk": _num(wr.get("Risk")),
                "coverage": _num(wr.get("Datatäckning")),
            }
            journal = assess_case_change(hist, current_case)
            # Bara riktiga förändringar ska konkurrera om dagens fokus.
            if str(journal.get("tone")) in {"negative", "positive"}:
                changes = journal.get("changes") or []
                watch_changes.append({
                    "ticker": sym,
                    "name": str(wr.get("Namn") or sym),
                    "tone": journal.get("tone"),
                    "status": journal.get("status"),
                    "score_delta": journal.get("score_delta"),
                    "summary": changes[0] if changes else journal.get("status"),
                    "changed_at": (str(hist.iloc[-1].get("created_at") or hist.iloc[-1].get("captured_date")) if not hist.empty else None),
                })

    candidate_rows = daily_shortlist.head(5).to_dict("records") if not daily_shortlist.empty else []
    signal_rows = today_signals.sort_values(["priority", "created_at"], ascending=[False, False]).head(8).to_dict("records") if not today_signals.empty else []
    focus_now = datetime.now()
    focus_items = build_daily_focus(candidate_rows, watch_changes, signal_rows, limit=3, now=focus_now)
    focus_meta = focus_context(focus_now)

    previous_visit, _current_visit = visit_context()
    reviewed_change_keys = get_reviewed_change_keys()
    new_since = build_since_last_visit(
        previous_visit,
        signals=signal_history.to_dict("records") if not signal_history.empty else [],
        watch_changes=watch_changes,
        reviewed_keys=reviewed_change_keys,
        limit=3,
    )
    st.markdown("## Nytt sedan sist")
    st.caption(visit_label(previous_visit, focus_now) + ". Här visas bara tidsstämplade förändringar – inte sådant du redan har sett.")
    if previous_visit is None:
        st.info("Första besöket registrerat. Från nästa besök kan Borsify skilja på tidigare information och sådant som faktiskt har tillkommit sedan dess.")
    elif not new_since:
        st.success("Inga nya tidsstämplade signaler eller tydliga förändringar i dina bevakade case sedan förra besöket.")
    else:
        for item in new_since:
            with st.container(border=True):
                left, right = st.columns([3, 1])
                ticker = str(item.get("ticker", ""))
                change_id = str(item.get("key", ""))
                left.markdown(f"**{item.get('name', ticker)} · {item.get('headline','Ny förändring')}**")
                left.write(str(item.get('why', '')))
                right.caption(str(item.get('kind', 'Nytt')))
                right.caption(ticker)
                a1, a2 = st.columns([1, 1])
                target = str(item.get("target") or "analysis")
                action_label = "Öppna Case Journal" if target == "journal" else "Öppna signalhistorik"
                if a1.button(action_label, key=f"since_open_{change_id}", use_container_width=True):
                    st.session_state["bq_quick_open_ticker"] = ticker
                    st.session_state["bq_quick_open_mode"] = target
                    st.rerun()
                if a2.button("Markera som genomgången", key=f"since_review_{change_id}", use_container_width=True):
                    mark_change_reviewed(change_id)
                    st.rerun()
        render_quick_change_target(scored, signal_history, profile)
    if st.session_state.get("bq_visit_state_migration_needed"):
        st.caption("Molnkontot saknar ännu v2.25-tabellen för senaste besök. Funktionen fungerar fullt ut efter den färdiga Supabase-migreringen; övriga delar av Borsify påverkas inte.")
    if st.session_state.get("bq_review_state_migration_needed"):
        st.caption("Molnkontot saknar ännu v2.26-tabellen för genomgångna förändringar. Knapparna fungerar lokalt; kör den färdiga Supabase-migreringen för permanent molnsynk.")

    st.markdown(f"## {focus_meta['title']}")
    st.caption(f"{focus_meta['intro']} Högst tre saker visas. Prioriteringen är en läsordning – inte en köp- eller säljlista.")
    if not focus_items:
        st.info("Inget nytt sticker ut just nu. Det är också ett resultat: du behöver inte leta fram en affär bara för att börsen är öppen.")
    else:
        cols = st.columns(len(focus_items))
        for col, item in zip(cols, focus_items):
            with col:
                with st.container(border=True):
                    freshness = str(item.get("freshness") or "").strip()
                    label = str(item.get("kind", "Fokus")) + (f" · {freshness}" if freshness else "")
                    st.caption(label)
                    st.markdown(f"### {item.get('name', item.get('ticker',''))}")
                    if item.get("name") != item.get("ticker"):
                        st.caption(str(item.get("ticker", "")))
                    st.markdown(f"**{item.get('headline','')}**")
                    st.write(str(item.get("why", "")))
                    st.caption(f"Gör så här: {item.get('action','Öppna analysen och kontrollera caset.')}")

    s1, s2, s3 = st.columns(3)
    s1.metric("Fler med hög prioritet", high_priority)
    s2.metric("Nya Radar-signaler", unread_signals)
    s3.metric("Bevakade aktier", len(watch_df))

    if len(daily_shortlist) > 1:
        st.markdown("### Fler aktier värda en titt")
        compact = daily_shortlist.iloc[1:5][["Ticker", "Namn", "Pris", "Valuta", "Pris SEK", "Dagsförändring", "Borsify Score", "Dagens relevans", "Prioritet"]].copy()
        st.dataframe(
            compact, use_container_width=True, hide_index=True,
            column_config={
                "Borsify Score": st.column_config.ProgressColumn("Borsify", min_value=0, max_value=100, format="%.0f"),
                "Dagens relevans": st.column_config.ProgressColumn("Idag", min_value=0, max_value=100, format="%.0f"),
                "Pris": st.column_config.NumberColumn("Kurs", format="%.2f"),
                "Dagsförändring": st.column_config.NumberColumn("Idag %", format="%.2f%%"),
            },
        )

    with st.expander("Min portfölj och säljkontroll", expanded=False):
        render_holdings_portfolio(scored, profile)

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
        st.write(f"Marknad: {market} · strategi: {profile} · analyserade: {len(scored)} · efter filter: {len(filtered)} · senaste kursdag: {latest_price_date} · körtid: {elapsed:.1f} s")
        scan_metrics = st.session_state.get("bq_scan_metrics", {})
        if isinstance(scan_metrics, dict) and scan_metrics:
            st.write(
                "Scanning: "
                f"kursdel {float(scan_metrics.get('price_seconds',0) or 0):.1f} s · "
                f"bolagsdata {float(scan_metrics.get('fundamental_seconds',0) or 0):.1f} s · "
                f"{int(scan_metrics.get('fundamental_persistent_cache',0) or 0)} cacheträffar · "
                f"{int(scan_metrics.get('fundamental_yahoo',0) or 0)} nya Yahoo-anrop"
            )
            st.caption(
                "Tiderna mäts i den aktuella körningen. De är diagnostik, inte ett löfte om en viss framtida laddtid."
            )

        validation = st.session_state.get("bq_prefilter_validation", {})
        if isinstance(validation, dict) and validation:
            st.markdown("**Test av framtida snabbare scanning**")
            retention = _num(validation.get("retention"))
            pool_fraction = _num(validation.get("fraction"))
            if np.isfinite(retention):
                st.write(
                    f"En billig första gallring till cirka {pool_fraction:.0%} av aktierna "
                    f"hade behållit {int(validation.get('retained',0))} av "
                    f"{int(validation.get('targets',0))} slutliga toppkandidater "
                    f"i den här körningen ({retention:.0%})."
                )
            missed = validation.get("missed") or []
            if missed:
                st.warning(
                    "Gallringen hade missat: " + ", ".join(map(str, missed))
                    + ". Därför används den inte för att styra dagens analys."
                )
            else:
                st.success(
                    "Ingen av dagens slutliga toppkandidater hade missats i simuleringen."
                )

            validation_history = get_prefilter_validation_history(
                DB_PATH, market=market, limit=10
            )
            readiness = activation_readiness(validation_history, minimum_runs=5)
            if bool(readiness.get("ready")):
                st.success(
                    "Historiken är tillräckligt stabil för att senare prova gallringen "
                    "i ett kontrollerat prestandatest. Den är fortfarande inte aktiverad."
                )
            else:
                st.caption(
                    "Aktivering: " + str(readiness.get("status","För lite historik"))
                    + ". Borsify kräver minst fem separata körningar och mycket hög träff innan "
                    "några fundamental-anrop får tas bort."
                )
        if idx:
            st.write(f"{benchmark_name}: {idx['index']:.2f} ({fmt_pct(idx.get('daily'))})")
        st.caption(f"Borsify v{APP_VERSION}. Kurser och bolagsuppgifter kan ibland vara fördröjda eller saknas.")




def save_ai_usage(request_id: str, symbol: str, model: str, input_tokens: int, output_tokens: int, cost_usd: float) -> None:
    """Persist successful AI usage. Cloud persistence is per signed-in user; SQLite is the safe fallback."""
    rid = str(request_id or "").strip()
    if not rid:
        rid = f"local-{datetime.now().isoformat(timespec='microseconds')}-{symbol}"
    payload = {
        "request_id": rid,
        "symbol": str(symbol or ""),
        "model": str(model or ""),
        "input_tokens": int(input_tokens or 0),
        "output_tokens": int(output_tokens or 0),
        "cost_usd": float(cost_usd or 0.0),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            client.table("ai_usage").upsert(
                {"user_id": uid, **payload},
                on_conflict="user_id,request_id",
            ).execute()
            return
        except Exception:
            st.session_state["bq_ai_usage_migration_needed"] = True

    init_db()
    with _db_connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO ai_usage(request_id,symbol,model,input_tokens,output_tokens,cost_usd,created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (
                payload["request_id"], payload["symbol"], payload["model"],
                payload["input_tokens"], payload["output_tokens"], payload["cost_usd"], payload["created_at"],
            ),
        )


def get_ai_usage_month() -> dict[str, float]:
    """Return current calendar month's usage totals without estimating missing requests."""
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            rows = (
                client.table("ai_usage")
                .select("input_tokens,output_tokens,cost_usd,created_at")
                .eq("user_id", uid)
                .gte("created_at", month_start)
                .execute().data or []
            )
            return {
                "requests": float(len(rows)),
                "input_tokens": float(sum(int(r.get("input_tokens") or 0) for r in rows)),
                "output_tokens": float(sum(int(r.get("output_tokens") or 0) for r in rows)),
                "cost_usd": float(sum(float(r.get("cost_usd") or 0.0) for r in rows)),
            }
        except Exception:
            st.session_state["bq_ai_usage_migration_needed"] = True

    init_db()
    with _db_connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0), COALESCE(SUM(cost_usd),0) "
            "FROM ai_usage WHERE created_at >= ?",
            (month_start,),
        ).fetchone()
    return {
        "requests": float(row[0] or 0),
        "input_tokens": float(row[1] or 0),
        "output_tokens": float(row[2] or 0),
        "cost_usd": float(row[3] or 0.0),
    }


def ai_cost_sek(cost_usd: float) -> float:
    """Convert the estimated USD API cost to SEK using Borsify's cached Yahoo FX rate when available."""
    try:
        rates = fetch_fx_rates_to_sek(("USD",))
        usdsek = _num(rates.get("USD"))
        if np.isfinite(usdsek) and usdsek > 0:
            return float(cost_usd) * usdsek
    except Exception:
        pass
    return math.nan


def render_ai_cost_meter() -> None:
    usage = get_ai_usage_month()
    cost_usd = float(usage.get("cost_usd", 0.0))
    cost_sek = ai_cost_sek(cost_usd)
    requests = int(usage.get("requests", 0))
    req_label = "fråga" if requests == 1 else "frågor"
    if np.isfinite(cost_sek):
        st.caption(f"AI denna månad: **≈ {cost_sek:.2f} kr** · {requests} {req_label}")
    else:
        st.caption(f"AI denna månad: **{format_cost_usd(cost_usd)}** · {requests} {req_label}")
    with st.expander("Visa AI-kostnadsdetaljer", expanded=False):
        st.caption(
            f"Beräknad API-kostnad: {format_cost_usd(cost_usd)}. "
            "Mätaren bygger på faktisk tokenanvändning i lyckade AI-anrop och den standardtaxa som finns i aktuell Borsify-version."
        )



def _case_ai_api_key() -> str:
    try:
        return str(st.secrets.get("OPENAI_API_KEY", "") or "").strip()
    except Exception:
        return ""


def _case_ai_model() -> str:
    try:
        return str(st.secrets.get("OPENAI_MODEL", "gpt-5.6-luna") or "gpt-5.6-luna").strip()
    except Exception:
        return "gpt-5.6-luna"


def ask_borsify_ai(case: pd.Series | dict[str, Any], horizon: str, question: str) -> tuple[str, str, dict[str, Any]]:
    """Ask the configured OpenAI model and record actual token usage for the cost meter."""
    key = _case_ai_api_key()
    if not key or OpenAI is None:
        return local_case_explanation(case, horizon), "local", {}

    model = _case_ai_model()
    try:
        client = OpenAI(api_key=key)
        response = client.responses.create(
            model=model,
            instructions=build_case_ai_instructions(),
            input=build_case_ai_input(case, horizon, question),
            max_output_tokens=700,
        )
        text = str(getattr(response, "output_text", "") or "").strip()
        if not text:
            return local_case_explanation(case, horizon), "local", {}

        input_tokens, output_tokens = token_usage(response)
        usage_cost = estimate_usage_cost(model, input_tokens, output_tokens)
        request_id = str(getattr(response, "id", "") or "")
        symbol = str(case.get("Ticker", "") or "")
        save_ai_usage(
            request_id, symbol, usage_cost.model,
            usage_cost.input_tokens, usage_cost.output_tokens, usage_cost.cost_usd,
        )
        meta = {
            "model": usage_cost.model,
            "input_tokens": usage_cost.input_tokens,
            "output_tokens": usage_cost.output_tokens,
            "cost_usd": usage_cost.cost_usd,
        }
        return text, "ai", meta
    except Exception as exc:
        fallback = local_case_explanation(case, horizon)
        return fallback + f"\n\n_AI-tjänsten kunde inte nås ({type(exc).__name__})._", "local", {}



def render_recommendation_price(case: pd.Series | dict[str, Any]) -> None:
    """Show latest available market price without Streamlit metric truncation."""
    price = _num(case.get("Pris"))
    daily = _num(case.get("Dagsförändring"))
    currency = str(case.get("Valuta", "") or "").strip()
    price_date = str(case.get("Prisdatum", "") or "").strip()

    if np.isfinite(price):
        # Swedish presentation, while preserving the source currency.
        price_text = f"{price:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
        ccy_text = f" {currency}" if currency else ""
        parts = [f"**Aktuell kurs:** {price_text}{ccy_text}"]
        if np.isfinite(daily):
            parts.append(f"**idag:** {daily:+.1%}".replace(".", ","))
        if price_date and price_date != "—":
            parts.append(f"kursdag {price_date}")
        st.markdown(" · ".join(parts))
    else:
        st.markdown("**Aktuell kurs:** —")
        st.caption("Aktuell kurs saknas i tillgänglig data.")





def render_case_plan(case: pd.Series | dict[str, Any]) -> None:
    thesis = str(case.get("Case Plan Tes", "") or "").strip()
    if not thesis:
        return
    with st.expander("🧭 Case-plan · vad måste hända härifrån?", expanded=False):
        st.markdown(f"**Tes**  \n{thesis}")
        st.markdown(f"**Det som bekräftar caset**  \n{case.get('Case Plan Bekräftelse','—')}")
        st.markdown(f"**Varningssignal**  \n{case.get('Case Plan Varning','—')}")
        st.markdown(f"**Det som skulle kunna få Borsify att ändra uppfattning**  \n{case.get('Case Plan Breaker','—')}")
        st.markdown(f"**Nästa kontrollpunkt**  \n{case.get('Case Plan Nästa kontroll','—')}")
        st.markdown(f"**Hur priset påverkar bedömningen**  \n{case.get('Case Plan Prisregel','—')}")
        st.caption(
            "Case-planen är en regelbaserad uppföljningsplan från aktuell Borsify-data. "
            "Den är inte en riktkurs, sannolikhet eller personlig köp-/säljrekommendation."
        )


def render_recommendation_relevance(case: pd.Series | dict[str, Any]) -> None:
    status = str(case.get("Relevans nu", "") or "").strip()
    explanation = str(case.get("Relevans förklaring", "") or "").strip()
    if not status:
        return

    if status == "Caset har stärkts":
        st.success(f"**Relevans nu: {status}**")
    elif status == "Fortfarande relevant":
        st.info(f"**Relevans nu: {status}**")
    elif status == "Mindre attraktivt än vid signal":
        st.warning(f"**Relevans nu: {status}**")
    elif status == "Caset har försvagats":
        st.warning(f"**Relevans nu: {status}**")
    else:
        st.caption(f"**Relevans nu: {status}**")

    if explanation:
        st.caption(explanation)


def render_case_ai_qa(case: pd.Series | dict[str, Any], horizon: str, rank: int) -> None:
    ticker = str(case.get("Ticker", "case"))
    safe_ticker = re.sub(r"[^A-Za-z0-9_-]+", "_", ticker)
    scope = f"{horizon}_{safe_ticker}_{rank}"
    history_key = f"case_ai_history_{scope}"

    with st.expander("💬 Fråga Borsify AI om rekommendationen", expanded=False):
        st.caption(
            "Fråga varför caset lyfts, vad som talar emot det eller vad som skulle få Borsify att ändra uppfattning. "
            "AI:n får den faktiska Borsify-datan för just detta case – inte en fri instruktion att hitta på nya bolagsfakta."
        )

        if not _case_ai_api_key():
            st.info(
                "AI-frågor är förberedda men OpenAI är inte aktiverat i denna deployment. "
                "Lägg `OPENAI_API_KEY` i Streamlit Secrets. Utan nyckel visas bara ett regelbaserat reservsvar."
            )

        render_ai_cost_meter()

        history = st.session_state.setdefault(history_key, [])
        for item in history[-4:]:
            st.markdown(f"**Du:** {item['q']}")
            st.markdown(f"**Borsify AI:** {item['a']}")

        default_example = (
            "Varför rekommenderar du den här aktien när den redan ligger så högt?"
            if horizon == "long"
            else "Varför är detta ett kortsiktigt case trots att aktien redan har gått starkt?"
        )
        with st.form(f"case_ai_form_{scope}", clear_on_submit=True):
            question = st.text_input(
                "Din fråga",
                placeholder=default_example,
                key=f"case_ai_question_{scope}",
            )
            submitted = st.form_submit_button("Fråga AI")

        if submitted:
            q = str(question or "").strip()
            if not q:
                st.warning("Skriv en fråga först.")
            else:
                with st.spinner("Borsify AI granskar caset…"):
                    answer, mode, usage_meta = ask_borsify_ai(case, horizon, q)
                history.append({"q": q, "a": answer, "mode": mode, "usage": usage_meta})
                st.session_state[history_key] = history[-8:]
                st.markdown(f"**Du:** {q}")
                label = "Borsify AI" if mode == "ai" else "Borsify · reservsvar"
                st.markdown(f"**{label}:** {answer}")
                if mode == "ai" and usage_meta:
                    one_usd = float(usage_meta.get("cost_usd", 0.0))
                    one_sek = ai_cost_sek(one_usd)
                    token_total = int(usage_meta.get("input_tokens", 0)) + int(usage_meta.get("output_tokens", 0))
                    if np.isfinite(one_sek):
                        st.caption(f"AI-kostnad för svaret: ≈ {one_sek:.3f} kr".replace(".", ","))
                    else:
                        st.caption(f"AI-kostnad för svaret: {format_cost_usd(one_usd)}")
                    with st.expander("Visa token- och kostnadsdetaljer", expanded=False):
                        st.caption(
                            f"{token_total:,} tokens · {format_cost_usd(one_usd)} · modell {usage_meta.get('model','—')}".replace(",", " ")
                        )
                    render_ai_cost_meter()
                elif mode != "ai":
                    st.caption("Reservsvaret är regelbaserat och ska inte förväxlas med ett AI-svar.")


def render_edge_lab(default_symbol: str, universe_symbols: list[str], benchmark_symbol: str | None = "^OMXS30", benchmark_name: str = "OMXS30") -> None:
    st.subheader("Historiskt test · har Borsifys signaler fungerat tidigare?")
    st.caption("Här testar Borsify sina regler på historiska kurser. Frågan är enkel: om samma köpsignaler hade kommit tidigare, hur hade de gått? Historik kan inte förutsäga framtiden, men den kan avslöja regler som verkar för svaga.")
    render_beginner_glossary("edge_terms")
    st.caption(
        "Här testar Borsify sina köpsignaler på gamla kursdata. Testet använder bara information som fanns just då. "
        "Det gör testet mer rättvist och minskar risken att framtida information råkar smyga sig in. "
        "Du kan också räkna med kostnader för köp och försäljning."
    )

    with st.expander("⚡ Daytrader 1–2 dagar · validering av köpmodellen", expanded=True):
        st.caption(
            "Borsify räknar först fram en köpsignal efter att en börsdag är slut. Testköpet sker sedan vid nästa "
            "börsdags öppning. Därefter kontrolleras hur aktien gått efter 1 och 2 handelsdagar. "
            "På så sätt får testet inte använda ett pris som det i verkligheten inte hade kunnat köpa till."
        )
        st.warning(
            "Testet är nära den riktiga Daytrader-modellen men inte exakt samma. En liten del av den riktiga modellen "
            "använder bolagsdata som vi ännu inte har sparad historik för. Därför ersätts den delen med historisk "
            "kurs- och handelsdata i testet."
        )
        d1,d2,d3 = st.columns([1.5,1,1])
        dt_symbol = d1.text_input(
            "Ticker · Daytrader",
            value=default_symbol or "INVE-B.ST",
            key="daytrade_validation_symbol",
        ).strip().upper()
        dt_years = d2.slider("Historik · Daytrader", 3, 10, 7, key="daytrade_validation_years")
        dt_cost = d3.number_input(
            "Kostnad för köp + försäljning (bps)",
            min_value=0.0, max_value=200.0, value=20.0, step=5.0,
            help="Här räknar Borsify med avgifter och att köp/sälj inte alltid sker till exakt bästa pris. 20 bps betyder totalt 0,20 %.",
            key="daytrade_validation_cost",
        )
        run_daytrade_validation = st.button(
            "Validera Daytrader 1–2 dagar",
            type="primary",
            key="run_daytrade_validation",
        )
        if run_daytrade_validation and dt_symbol:
            try:
                dt_hist = yf.download(
                    dt_symbol, period=f"{dt_years}y", interval="1d",
                    auto_adjust=True, progress=False, threads=False
                )
            except Exception as exc:
                st.error(f"Kunde inte hämta historik för Daytrader-testet: {exc}")
                dt_hist = pd.DataFrame()

            if dt_hist is None or dt_hist.empty:
                st.warning("För lite historik för Daytrader-validering.")
            else:
                pit_day = build_point_in_time_daytrade(dt_hist)
                if pit_day.empty:
                    st.warning("Historiken saknar Open/Close-data som krävs för ett kausalt 1–2-dagarstest.")
                else:
                    comparison = compare_horizons(
                        pit_day,
                        roundtrip_cost_bps=float(dt_cost),
                        min_train_days=min(504, max(252, int(len(pit_day)*.45))),
                        test_days=126,
                    )
                    if not comparison.empty:
                        display_cmp = comparison.copy().rename(columns={
                            "Netto median":"Median efter kostnader",
                            "Träffsäkerhet":"Andel positiva affärer",
                            "Median över baseline":"Skillnad mot en vanlig börsdag",
                            "Vinst/förlust-kvot":"Vinst/förlust-kvot",
                        })
                        for c in ["Median efter kostnader","Andel positiva affärer","Skillnad mot en vanlig börsdag"]:
                            display_cmp[c] = pd.to_numeric(display_cmp[c],errors="coerce")
                        st.dataframe(
                            display_cmp.style.format({
                                "Median efter kostnader":"{:.2%}",
                                "Andel positiva affärer":"{:.1%}",
                                "Skillnad mot en vanlig börsdag":"{:.2%}",
                                "Vinst/förlust-kvot":"{:.2f}",
                            }),
                            use_container_width=True,
                            hide_index=True,
                        )

                    for h in (1,2):
                        stats = evaluate_daytrade(pit_day,h,float(dt_cost))
                        wf = walk_forward_fixed_gate(
                            pit_day,h,float(dt_cost),
                            min_train_days=min(504, max(252, int(len(pit_day)*.45))),
                            test_days=126,
                        )
                        grade = validation_grade(stats,wf)
                        st.markdown(f"**{h} handelsdag{'ar' if h==2 else ''}: {grade['status']}**")
                        st.caption(grade["message"])
                        if int(stats.get("signals",0) or 0) > 0:
                            a,b,c,d = st.columns(4)
                            a.metric("Signaler", int(stats.get("signals",0)))
                            b.metric("Median efter kostnader", f"{float(stats.get('net_median',0)):.2%}")
                            c.metric("Andel positiva affärer", f"{float(stats.get('hit_rate',0)):.1%}")
                            pf = float(stats.get("profit_factor")) if np.isfinite(_num(stats.get("profit_factor"))) else np.nan
                            d.metric("Vinst/förlust-kvot", f"{pf:.2f}" if np.isfinite(pf) else "—")
                        if isinstance(wf,pd.DataFrame) and not wf.empty:
                            with st.expander(f"Visa testperioderna · {h} dag{'ar' if h==2 else ''}", expanded=False):
                                wf_show=wf.copy().rename(columns={
                                    "TestStart":"Period från",
                                    "TestEnd":"Period till",
                                    "Signals":"Köpsignaler",
                                    "NetMedian":"Median efter kostnader",
                                    "HitRate":"Andel positiva affärer",
                                    "MedianExcess":"Skillnad mot vanlig börsdag",
                                })
                                st.dataframe(
                                    wf_show.style.format({
                                        "Median efter kostnader":"{:.2%}",
                                        "Andel positiva affärer":"{:.1%}",
                                        "Skillnad mot vanlig börsdag":"{:.2%}",
                                    }),
                                    use_container_width=True,
                                    hide_index=True,
                                )

                    st.caption(
                        "Borsify ändrar inte reglerna mellan testperioderna för att få ett snyggare resultat. "
                        "Samma köpgräns används hela vägen. Det gör testet tuffare men mer trovärdigt."
                    )
                    st.caption(
                        "Det finns fortfarande begränsningar. Vi testar dagens lista av aktier bakåt i tiden, "
                        "vi vet inte exakt vilka aktier som gick att handla hos Avanza varje historisk dag, och "
                        "vi har inte gamla orderböcker som visar exakt vilket köp- eller säljpris man hade fått."
                    )

    with st.expander("🌍 Testa Daytrader på flera aktier och länder", expanded=True):
        st.caption(
            "Ett bra resultat i en enda aktie räcker inte. Här testar Borsify samma Daytrader-regel på många "
            "aktier samtidigt för att se om mönstret verkar fungera brett – inte bara i några enstaka vinnare."
        )
        uv1,uv2,uv3,uv4 = st.columns([1.2,1,1,1])
        max_universe_test = min(40, max(5, len(universe_symbols)))
        uv_count = uv1.slider(
            "Antal aktier att testa",
            5, max_universe_test, min(25,max_universe_test), step=5,
            help="Fler aktier ger ett bättre underlag men tar längre tid att hämta.",
            key="daytrade_universe_count",
        )
        uv_years = uv2.slider("Antal år bakåt", 3, 10, 7, key="daytrade_universe_years")
        uv_horizon = uv3.selectbox(
            "Hur länge ägs aktien?",
            [1,2], index=1,
            format_func=lambda x: f"{x} handelsdag" + ("" if x==1 else "ar"),
            key="daytrade_universe_horizon",
        )
        uv_cost = uv4.number_input(
            "Köp + sälj (%)",
            min_value=0.0,max_value=2.0,value=0.20,step=0.05,
            help="Exempel: 0,20 % betyder att Borsify drar bort totalt 0,20 % för avgifter och sämre köp/säljpris.",
            key="daytrade_universe_cost_pct",
        )
        run_universe_validation = st.button(
            "Testa Daytrader på flera aktier",
            type="primary",
            key="run_daytrade_universe_validation",
        )
        if run_universe_validation:
            test_symbols=list(dict.fromkeys(universe_symbols))[:int(uv_count)]
            if len(test_symbols) < 5:
                st.info("Välj ett universum med minst 5 aktier för att göra ett brett test.")
            else:
                with st.spinner(f"Hämtar historik och testar {len(test_symbols)} aktier…"):
                    try:
                        uv_data=yf.download(
                            tickers=test_symbols,
                            period=f"{int(uv_years)}y",
                            interval="1d",
                            auto_adjust=True,
                            actions=False,
                            group_by="ticker",
                            threads=True,
                            progress=False,
                        )
                    except Exception as exc:
                        uv_data=pd.DataFrame()
                        st.error(f"Kunde inte hämta historiken: {exc}")
                histories=split_downloaded_histories(uv_data,test_symbols)
                if len(histories) < 3:
                    st.warning("För få aktier fick användbar historik. Prova igen senare eller välj ett mindre universum.")
                else:
                    per_symbol,by_country,summary=validate_universe(
                        histories,
                        horizon_days=int(uv_horizon),
                        roundtrip_cost_bps=float(uv_cost)*100.0,
                        country_fn=_market_label_for_ticker,
                    )
                    label,message=universe_validation_label(summary)
                    st.markdown(f"### {label}")
                    st.caption(message)
                    u1,u2,u3,u4=st.columns(4)
                    u1.metric("Aktier testade", int(summary.get("symbols_tested",0)))
                    u2.metric("Aktier med köpsignaler", int(summary.get("symbols_with_signals",0)))
                    u3.metric("Historiska köpsignaler", int(summary.get("signals",0)))
                    med=_num(summary.get("median_net"))
                    u4.metric("Median efter kostnader", f"{med:.2%}" if np.isfinite(med) else "—")

                    if not by_country.empty:
                        st.markdown("**Resultat per land**")
                        country_show=by_country.copy()
                        st.dataframe(
                            country_show.style.format({
                                "Median efter kostnader":"{:.2%}",
                                "Andel positiva affärer":"{:.1%}",
                            }),
                            use_container_width=True,
                            hide_index=True,
                        )

                    if not per_symbol.empty:
                        with st.expander("Visa resultat för varje aktie", expanded=False):
                            per_show=per_symbol.sort_values(
                                ["Median efter kostnader","Signaler"],ascending=[False,False]
                            )
                            st.dataframe(
                                per_show.style.format({
                                    "Median efter kostnader":"{:.2%}",
                                    "Andel positiva affärer":"{:.1%}",
                                    "Skillnad mot vanlig dag":"{:.2%}",
                                    "Vinst/förlust-kvot":"{:.2f}",
                                }),
                                use_container_width=True,
                                hide_index=True,
                            )
                    st.caption(
                        "Ett positivt historiskt resultat betyder inte att nästa affär går med vinst. "
                        "Det här testet används för att kontrollera om Borsifys regel verkar hålla över många aktier, "
                        "inte för att lova framtida avkastning."
                    )

    with st.expander("Kortsiktiga köp · historiskt test", expanded=False):
        st.caption(
            "Detta test återskapar bara de delar av Short Alpha 2.0 som faktiskt kan rekonstrueras historiskt: "
            "relativ styrka, trend, momentum och handelsaktivitet. Historiska estimatrevideringar och katalysatorer "
            "backfylls inte, eftersom Borsify ännu saknar point-in-time-historik för dem."
        )
        sa1, sa2, sa3 = st.columns([1.5, 1, 1])
        short_symbol = sa1.text_input(
            "Ticker · Short Alpha",
            value=default_symbol or "INVE-B.ST",
            key="short_edge_symbol",
        ).strip().upper()
        short_years = sa2.slider("Historik · Short Alpha", 3, 10, 7, key="short_edge_years")
        short_spacing = sa3.selectbox(
            "Minsta avstånd mellan signaler",
            [10, 21, 42, 63],
            index=1,
            format_func=lambda x: f"{x} börsdagar",
            key="short_edge_spacing",
        )
        run_short_edge = st.button("Testa kortsiktiga köp historiskt", type="primary", key="run_short_edge")

        if run_short_edge and short_symbol:
            try:
                short_hist = yf.download(
                    short_symbol, period=f"{short_years}y", interval="1d",
                    auto_adjust=True, progress=False, threads=False
                )
                short_bench = (
                    yf.download(
                        benchmark_symbol, period=f"{short_years}y", interval="1d",
                        auto_adjust=True, progress=False, threads=False
                    ) if benchmark_symbol else pd.DataFrame()
                )
            except Exception as exc:
                st.error(f"Kunde inte hämta historik för testet: {exc}")
                short_hist = pd.DataFrame()
                short_bench = pd.DataFrame()

            def _edge_flat_frame(frame: pd.DataFrame, symbol_hint: str) -> pd.DataFrame:
                if frame is None or frame.empty:
                    return pd.DataFrame()
                out = frame.copy()
                if isinstance(out.columns, pd.MultiIndex):
                    # yfinance may return either field/ticker or ticker/field orientation.
                    fields = {"Open", "High", "Low", "Close", "Adj Close", "Volume"}
                    level0 = set(map(str, out.columns.get_level_values(0)))
                    level1 = set(map(str, out.columns.get_level_values(1)))
                    if "Close" in level0:
                        out.columns = out.columns.get_level_values(0)
                    elif "Close" in level1:
                        out.columns = out.columns.get_level_values(1)
                return out.loc[:, ~out.columns.duplicated()].copy()

            short_hist = _edge_flat_frame(short_hist, short_symbol)
            short_bench = _edge_flat_frame(short_bench, benchmark_symbol or "")

            if short_hist.empty or "Close" not in short_hist:
                st.warning("Det finns för lite kurshistorik för att göra ett bra test.")
            else:
                bench_close = (
                    short_bench["Close"].dropna().astype(float)
                    if not short_bench.empty and "Close" in short_bench else None
                )
                pit = build_point_in_time_short_signals(short_hist, bench_close)
                pit = add_forward_returns(pit)
                threshold_table = evaluate_thresholds(
                    pit, thresholds=[55, 60, 65, 70, 75, 80], spacing_days=int(short_spacing)
                )
                wf_short = walk_forward_threshold_test(
                    pit, min_train_days=min(504, max(252, int(len(pit) * .45))),
                    test_days=126, thresholds=[55, 60, 65, 70, 75, 80]
                )
                short_summary = summarize_edge(threshold_table, wf_short)

                status = str(short_summary.get("status", "Otillräcklig data"))
                if status == "Historiskt lovande – ej bevisad alpha":
                    st.success(status)
                elif status == "Ingen tydlig historisk edge":
                    st.warning(status)
                else:
                    st.info(status)
                st.caption(str(short_summary.get("message", "")))

                if "best_threshold" in short_summary:
                    sm1, sm2, sm3, sm4 = st.columns(4)
                    sm1.metric("Bäst historisk tröskel", f"{short_summary['best_threshold']:.0f}")
                    sm2.metric("Median 3m", f"{short_summary['median_3m']:+.1%}")
                    sm3.metric("Träff 3m", f"{short_summary['hit_rate_3m']:.0%}")
                    wf_med = short_summary.get("walk_forward_median_3m", np.nan)
                    sm4.metric("Median i senare testperioder · 3 mån", f"{wf_med:+.1%}" if np.isfinite(wf_med) else "—")

                if not threshold_table.empty:
                    show = threshold_table.copy()
                    show["Median %"] = (show["MedianReturn"] * 100).round(1)
                    show["Snitt %"] = (show["MeanReturn"] * 100).round(1)
                    show["Träff %"] = (show["HitRate"] * 100).round(0)
                    show["≥ +10 %"] = (show["GainRate10"] * 100).round(0)
                    show["≤ −10 %"] = (show["LossRate10"] * 100).round(0)
                    show = show.rename(columns={
                        "Threshold": "Min proxy",
                        "Horizon": "Utfall",
                        "Signals": "Signaler",
                    })
                    st.markdown("#### Trösklar och framtida utfall")
                    st.dataframe(
                        show[["Min proxy", "Utfall", "Signaler", "Median %", "Snitt %", "Träff %", "≥ +10 %", "≤ −10 %"]],
                        use_container_width=True, hide_index=True,
                    )

                if not wf_short.empty:
                    st.markdown("#### Test i flera tidsperioder · reglerna bestäms från äldre data")
                    wf_show = wf_short.copy()
                    wf_show["Train median 3m %"] = (wf_show["TrainMedian3m"] * 100).round(1)
                    wf_show["Test median 3m %"] = (wf_show["TestMedian3m"] * 100).round(1)
                    wf_show["Test träff %"] = (wf_show["TestHitRate3m"] * 100).round(0)
                    wf_show = wf_show.rename(columns={
                        "TrainEnd": "Träning t.o.m.",
                        "TestStart": "Test från",
                        "TestEnd": "Test t.o.m.",
                        "ChosenThreshold": "Vald tröskel",
                        "TestSignals": "Testsignaler",
                    })
                    st.dataframe(
                        wf_show[["Träning t.o.m.", "Test från", "Test t.o.m.", "Vald tröskel", "Testsignaler", "Train median 3m %", "Test median 3m %", "Test träff %"]],
                        use_container_width=True, hide_index=True,
                    )

                st.markdown("#### Vilka tekniska delar verkar bära?")
                component_name = st.selectbox(
                    "Delsignal",
                    ["Relative", "Trend", "Momentum", "Participation"],
                    format_func=lambda x: {
                        "Relative": "Relativ styrka",
                        "Trend": "Trend",
                        "Momentum": "Momentum",
                        "Participation": "Handelsaktivitet",
                    }.get(x, x),
                    key="short_edge_component",
                )
                buckets = component_bucket_analysis(pit, component_name, "3m")
                if buckets.empty:
                    st.caption("För få observationer för kvartilanalys.")
                else:
                    bucket_show = buckets.copy()
                    bucket_show["Median 3m %"] = (bucket_show["MedianReturn"] * 100).round(1)
                    bucket_show["Träff %"] = (bucket_show["HitRate"] * 100).round(0)
                    st.dataframe(
                        bucket_show[["Bucket", "Signals", "Median 3m %", "Träff %"]],
                        use_container_width=True, hide_index=True,
                    )

                veto = pit["FallingKnifeVeto"].fillna(False)
                valid = pit["ShortProxy"].notna()
                if valid.any():
                    st.caption(
                        f"Anti-falling-knife-filtret stoppade {int(veto[valid].sum())} av "
                        f"{int(valid.sum())} historiska dagsobservationer från att få proxy över 54."
                    )

                st.warning(
                    "Begränsning: detta validerar inte hela live-modellen. Estimatrevideringar och katalysatorer "
                    "ingår först när Borsify har sparat verklig point-in-time-historik för dem. Resultatet ska därför "
                    "användas för att justera de tekniska delarna – inte som bevis för framtida avkastning."
                )

    with st.expander("Tidigare rekommendationer · hur gick de?", expanded=False):
        st.caption(
            "Borsify fryser nu de fem kort- och långsiktiga finalisterna per modellversion/dag. "
            "Även svagare finalister sparas för att undvika att framtida utvärdering bara innehåller vinnarna."
        )
        recs = get_recommendation_records(limit=500)
        outs = get_recommendation_outcomes(limit=5000)

        if st.button("Uppdatera mogna utfall", key="refresh_recommendation_outcomes"):
            with st.spinner("Kontrollerar rekommendationer vars mätperiod har löpt ut…"):
                added = refresh_due_recommendation_outcomes(max_records=40)
            st.success(f"{added} nya utfall sparades." if added else "Inga nya utfall var mogna ännu.")
            recs = get_recommendation_records(limit=500)
            outs = get_recommendation_outcomes(limit=5000)

        if recs.empty:
            st.info("Det finns inga sparade rekommendationer att följa upp ännu. Listan fylls automatiskt när Borsify används.")
        else:
            l1, l2, l3, l4 = st.columns(4)
            l1.metric("Frysta case", len(recs))
            l2.metric("Kortsiktiga", int((recs["horizon_type"] == "short").sum()))
            l3.metric("Långsiktiga", int((recs["horizon_type"] == "long").sum()))
            l4.metric("Mätta utfall", len(outs))

            latest = recs.head(20).copy()
            latest["Typ"] = latest["horizon_type"].map({"short":"1–6 mån","long":"Lång sikt"})
            latest["Pris"] = pd.to_numeric(latest["entry_price"], errors="coerce").round(2)
            latest["Score"] = pd.to_numeric(latest["score"], errors="coerce").round(1)
            latest["Confidence"] = pd.to_numeric(latest["confidence"], errors="coerce").round(0)
            st.markdown("#### Senaste frysta modellbeslut")
            st.dataframe(
                latest.rename(columns={
                    "captured_date":"Datum","symbol":"Ticker","name":"Bolag","rank":"Rank",
                    "gate":"Bedömning","model_version":"Version",
                })[["Datum","Typ","Ticker","Bolag","Rank","Pris","Bedömning","Score","Confidence","Version"]],
                use_container_width=True, hide_index=True,
            )

            summary = outcome_summary(recs, outs)
            st.markdown("#### Utfall hittills")
            if summary.get("evaluated", 0):
                o1, o2, o3, o4 = st.columns(4)
                o1.metric("Mätta observationer", int(summary["evaluated"]))
                o2.metric("Medianutfall", f"{summary['median_return']:+.1%}")
                o3.metric("Positiva", f"{summary['hit_rate']:.0%}")
                o4.metric("≥ +10 %", f"{summary['gain_10_rate']:.0%}")
                st.caption(str(summary["message"]))

                horizon_options = sorted(outs["horizon"].dropna().astype(str).unique().tolist())
                if horizon_options:
                    chosen_h = st.selectbox(
                        "Kalibrera bedömningar mot utfall",
                        horizon_options,
                        key="ledger_calibration_horizon",
                    )
                    cal = calibration_by_gate(recs, outs, chosen_h)
                    if not cal.empty:
                        cal_show = cal.copy()
                        cal_show["Median %"] = (cal_show["MedianReturn"] * 100).round(1)
                        cal_show["Snitt %"] = (cal_show["MeanReturn"] * 100).round(1)
                        cal_show["Positiva %"] = (cal_show["HitRate"] * 100).round(0)
                        cal_show["≥ +10 %"] = (cal_show["Gain10"] * 100).round(0)
                        cal_show["≤ −10 %"] = (cal_show["Loss10"] * 100).round(0)
                        st.dataframe(
                            cal_show[["Gate","Antal","Median %","Snitt %","Positiva %","≥ +10 %","≤ −10 %"]],
                            use_container_width=True, hide_index=True,
                        )

                    st.markdown("#### Vad har Borsify lärt sig hittills?")
                    st.caption(
                        f"Borsify jämför bara grupper med minst {MIN_COHORT} mogna utfall. "
                        "Det här är historiska observationer från Borsifys egna frysta rekommendationer – inte bevis på framtida avkastning."
                    )
                    learned = learning_summary(recs, outs, chosen_h)
                    if learned.get("status") == "För lite historik":
                        st.info(str(learned.get("text","För lite historik.")))
                    elif learned.get("status") == "Möjligt historiskt mönster":
                        st.success(str(learned.get("text","")))
                    else:
                        st.info(str(learned.get("text","")))

                    score_check = score_band_monotonicity(recs, outs, chosen_h)
                    if score_check.get("status") != "För lite underlag":
                        if str(score_check.get("status","")).startswith("Varning"):
                            st.warning(str(score_check["status"]))
                        else:
                            st.caption("Kontroll av Borsifys betyg: " + str(score_check["status"]) + ".")

                    tables = learning_tables(recs, outs, chosen_h)
                    table_choice = st.selectbox(
                        "Jämför historiska utfall efter",
                        ["Bedömning","Score","Underlag","Sektor","Modellversion"],
                        key="recommendation_learning_dimension",
                    )
                    learn_table = tables.get(table_choice, pd.DataFrame())
                    if learn_table.empty:
                        st.caption("Det finns ännu inget användbart underlag för den här uppdelningen.")
                    else:
                        show = learn_table.copy()
                        show["Median %"] = (show["Median"] * 100).round(1)
                        show["Positiva %"] = (show["Positiva"] * 100).round(0)
                        show["Minst +10 %"] = (show["Minst +10 %"] * 100).round(0)
                        show["Högst −10 %"] = (show["Högst −10 %"] * 100).round(0)
                        show["Underlag"] = show["Tillräckligt underlag"].map(
                            {True:"Kan börja jämföras", False:"För få utfall"}
                        )
                        st.dataframe(
                            show[["Grupp","Antal","Median %","Positiva %","Minst +10 %","Högst −10 %","Underlag"]],
                            use_container_width=True, hide_index=True,
                        )
                    st.caption(data_limits_note(recs))
                    st.warning(
                        "Borsify ändrar inte vikter eller köpgränser automatiskt utifrån den här tabellen. "
                        "Små historiska skillnader kan bero på slump, marknadsläge eller att samma bolag förekommer flera gånger."
                    )
            else:
                st.info(
                    "Inga utfall har hunnit mogna ännu. Kortsiktiga case börjar kunna mätas efter cirka en månad; "
                    "långsiktiga case först efter cirka sex månader."
                )

            st.warning(
                "Ledgern ska användas för kalibrering, inte för att automatiskt optimera på ett litet sample. "
                "Borsify ändrar inte modellvikter utifrån dessa utfall ännu."
            )

    st.divider()
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
    m5.metric("Vinst/förlust-kvot", f"{pf:.2f}" if np.isfinite(pf) else "—", help=beginner_term("profit factor"))

    edge_win = summary["win_rate"] - summary["baseline_win_rate"]
    edge_med = summary["median_return"] - summary["baseline_median_return"]
    if int(summary["signals"]) < 30:
        st.warning("Litet stickprov. Under 30 signaler är för tunt för att dra starka slutsatser.")
    elif edge_win > .05 and edge_med > 0:
        st.success(f"Den här signalen har varit bättre än en enkel jämförelse för {symbol} i just detta historiska test: +{edge_win:.1%} högre andel positiva affärer och {edge_med:+.2%} bättre medianresultat. Det betyder inte att signalen kommer fungera framöver.")
    elif edge_win < 0 and edge_med <= 0:
        st.error("Den valda signalen har inte varit bättre än den enkla jämförelsen i detta test. Därför finns det inget bra stöd för att ge signalen större betydelse i Borsify.")
    else:
        st.info("Resultatet är blandat. Vi behöver testa fler aktier och olika typer av börsperioder innan signalen kan få större betydelse.")

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

    st.markdown("**Det historiska testet kan ännu inte återskapa allt:** det saknar bland annat gamla bolagsuppgifter, historiska analytikerändringar, skatt och exakt information om vilket pris en riktig order hade gått igenom till. Resultatet ska därför ses som ett test av modellen – inte som en exakt kopia av verklig handel.")

    st.divider()
    st.subheader("Marknadsregim · när fungerar signalen?")
    st.caption("Borsify delar också upp testet efter hur börsen mådde just då: stark, neutral eller svag. Bedömningen bygger bara på kursinformation som fanns den dagen. På så sätt kan vi se om signalen bara fungerar när börsen redan går bra.")
    try:
        benchmark_hist = yf.download(benchmark_symbol, period=period, interval="1d", auto_adjust=False, progress=False, threads=False) if benchmark_symbol else pd.DataFrame()
    except Exception:
        benchmark_hist = pd.DataFrame()
    regime_hist = build_market_regime_history(benchmark_hist)
    regime_summary = summarize_backtest_by_regime(tech, regime_hist, score_col, threshold, horizon)
    if regime_summary.empty:
        st.info("Kunde inte bygga tillräcklig historik för jämförelseindexet i regimtestet just nu.")
    else:
        display_regime = regime_summary.copy()
        display_regime["Träffsäkerhet %"] = (display_regime["win_rate"] * 100).round(1)
        display_regime["Jämförelse %"] = (display_regime["baseline_win_rate"] * 100).round(1)
        display_regime["Median %"] = (display_regime["median_return"] * 100).round(2)
        display_regime["Skillnad mot jämförelse %"] = (display_regime["median_excess"] * 100).round(2)
        display_regime = display_regime.rename(columns={"regime":"Regim","signals":"Signaler","profit_factor":"Vinst/förlust-kvot"})
        st.dataframe(display_regime[["Regim","Signaler","Träffsäkerhet %","Jämförelse %","Median %","Skillnad mot jämförelse %","Vinst/förlust-kvot"]], use_container_width=True, hide_index=True)
        enough = regime_summary[regime_summary["signals"] >= 20].copy()
        if not enough.empty:
            best_regime = enough.sort_values(["median_excess","win_rate"], ascending=False).iloc[0]
            worst_regime = enough.sort_values(["median_excess","win_rate"], ascending=True).iloc[0]
            st.info(f"Starkast historiskt i detta test: **{best_regime['regime']}** med median-edge {best_regime['median_excess']:+.2%}. Svagast: **{worst_regime['regime']}** med {worst_regime['median_excess']:+.2%}. Detta är diagnostik, inte ett bevis på framtida edge.")
        else:
            st.warning("För få signaler per regim för att jämförelsen ska vara robust.")

    st.divider()
    st.subheader("Test i senare perioder · fungerar signalen även på data den inte byggdes på?")
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
        st.info("Det finns inte tillräckligt mycket historik för det här upplägget. Välj fler år bakåt eller kortare testperioder.")
    elif int(wf.get("signals", 0)) == 0:
        st.warning("I de senare testperioderna kom inga köpsignaler alls. Det kan betyda att regeln är för snäv eller fungerar för ojämnt över tid.")
    else:
        w1, w2, w3, w4, w5, w6 = st.columns(6)
        w1.metric("Testfönster", int(wf["folds"]))
        w2.metric("Köpsignaler i nya testperioder", int(wf["signals"]))
        w3.metric("Positiva affärer i nya testperioder", f"{wf['win_rate']:.1%}", f"vs {wf['baseline_win_rate']:.1%}")
        w4.metric("Median i nya testperioder", f"{wf['median_return']:.2%}", f"edge {wf['median_excess']:+.2%}")
        w5.metric("Vinst/förlust-kvot", f"{wf['profit_factor']:.2f}" if np.isfinite(wf['profit_factor']) else "—", help=beginner_term("profit factor"))
        w6.metric("Positiva testfönster", f"{wf['positive_fold_share']:.0%}" if np.isfinite(wf['positive_fold_share']) else "—")
        if wf["signals"] < 20 or int(wf.get("eligible_folds", 0)) < 3:
            st.warning("Out-of-sample-stickprovet är fortfarande tunt. Resultatet ska inte användas för att höja produktionsvikten ännu.")
        elif wf["median_excess"] > 0 and wf["win_rate"] > wf["baseline_win_rate"] and wf["positive_fold_share"] >= .60:
            st.success("Signalen fungerade relativt bra även i senare testperioder: medianresultatet var bättre än jämförelsen och en större andel affärer gick åt rätt håll. Det är ett positivt tecken, men inget löfte om framtida vinst.")
        elif wf["median_excess"] <= 0 and wf["win_rate"] <= wf["baseline_win_rate"]:
            st.error("Signalen blir tydligt sämre i senare testperioder. Det tyder på att regeln kan ha passat den äldre historiken för bra och därför inte bör få större betydelse i Borsify ännu.")
        else:
            st.info("Resultatet varierar mellan testperioderna. Regeln bör fortfarande ses som oprövad tills fler senare perioder visar samma mönster.")
        if float(wf.get("threshold_std", 0.0)) >= 10:
            st.warning(f"Den valda tröskeln är instabil mellan träningsfönstren (standardavvikelse {wf['threshold_std']:.1f} scorepoäng). Det är ett möjligt tecken på parameterkänslighet.")
        folds = wf.get("fold_table")
        if isinstance(folds, pd.DataFrame) and not folds.empty:
            st.markdown("#### Resultat i varje senare testperiod")
            fw = folds.copy()
            fw["Positiva affärer %"] = (fw["test_win_rate"] * 100).round(1)
            fw["Jämförelse %"] = (fw["test_baseline_win_rate"] * 100).round(1)
            fw["Median %"] = (fw["test_median_return"] * 100).round(2)
            fw["Skillnad mot jämförelse %"] = (fw["test_median_excess"] * 100).round(2)
            fw = fw.rename(columns={"test_start":"Test från","test_end":"Test till","threshold":"Vald tröskel","test_signals":"Signaler"})
            st.dataframe(fw[["Test från","Test till","Vald tröskel","Signaler","Positiva affärer %","Jämförelse %","Median %","Skillnad mot jämförelse %"]], use_container_width=True, hide_index=True)

        st.markdown("#### Vad händer när vi räknar med köp- och säljkostnader?")
        st.caption("Här räknar Borsify bara med affärer från de senare testperioderna och drar av kostnaden för varje köp och försäljning. Det är fortfarande en förenklad simulering, inte verklig handel.")
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
            f3.metric("Vinst/förlust-kvot efter kostnader", f"{friction['net_profit_factor']:.2f}" if np.isfinite(friction['net_profit_factor']) else "—")
            f4.metric("Sekventiell kapitalutveckling", f"{friction['compounded_return']:+.1%}")
            f5.metric("Största fall från topp", f"{friction['max_drawdown']:.1%}", help=beginner_term("drawdown"))
            if friction["net_median_return"] <= 0 or (np.isfinite(friction["net_profit_factor"]) and friction["net_profit_factor"] < 1.0):
                st.error("När köp- och säljkostnader räknas med försvinner fördelen i testet. Då ska det positiva resultatet före kostnader inte användas som argument för att ge signalen större betydelse.")
            elif friction["net_median_return"] > 0 and (not np.isfinite(friction["net_profit_factor"]) or friction["net_profit_factor"] >= 1.2):
                st.success("Signalen behåller positivt nettoresultat efter valda kostnader i detta out-of-sample-test. Det är ett bättre robusthetstecken än bruttoresultatet, men fortfarande inte ett live-validerat handelsresultat.")
            else:
                st.info("Signalen är fortfarande positiv efter våra antagna kostnader, men marginalen är liten. Ett något sämre verkligt köp- eller säljpris kan räcka för att fördelen ska försvinna.")

    st.divider()
    st.subheader("Universumtest · fungerar signalen över många aktier?")
    st.caption("Det här är ett hårdare test än en enda ticker. Samma tekniska signal körs över det valda marknadsuniversumet och jämförs med respektive akties normala framtida avkastning. Fundamenta används fortfarande inte historiskt.")
    uc1, uc2, uc3 = st.columns(3)
    uni_threshold = uc1.slider("Min score · universum", 40, 90, threshold, 5, key="edge_uni_threshold")
    uni_horizon = uc2.selectbox("Utfall · universum", [5, 10, 20], index=[5,10,20].index(horizon), format_func=lambda x: f"{x} börsdagar", key="edge_uni_horizon")
    uni_years = uc3.slider("Historik · universum", 2, 10, min(years, 5), key="edge_uni_years")
    max_available = max(1, len(universe_symbols))
    min_test = min(10, max_available)
    max_symbols = st.slider("Antal aktier i universumtest", min_test, max_available, min(50, max_available), 1 if max_available < 10 else 5, key="edge_uni_count")
    run_universe = st.button("Testa på många aktier", type="primary", key="run_universe_edge")
    if run_universe:
        symbols = [str(x).upper() for x in universe_symbols[:max_symbols]]
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
            q5.metric("Vinst/förlust-kvot", f"{uni['profit_factor']:.2f}" if np.isfinite(uni['profit_factor']) else "—")
            q6.metric("Aktier där signalen slog jämförelsen", f"{uni['positive_edge_share']:.0%}")
            if uni["signals"] < 100 or uni["symbols_with_signals"] < 10:
                st.warning("Stickprovet är fortfarande begränsat. Jag skulle inte ändra produktionsmodellen på detta resultat ensamt.")
            elif uni["median_excess"] > 0 and uni["win_rate"] > uni["baseline_win_rate"] and uni["positive_edge_share"] >= .55:
                st.success("Signalen har gett ett positivt historiskt resultat i många av de testade aktierna. Det är bättre stöd än ett bra resultat i bara en aktie, men testet är fortfarande en förenklad simulering.")
            elif uni["median_excess"] <= 0 and uni["win_rate"] <= uni["baseline_win_rate"]:
                st.error("Signalen misslyckas med att slå baslinjen brett. Det talar emot att ge den högre vikt i modellen utan omdesign.")
            else:
                st.info("Resultatet är blandat mellan aktier. Det tyder på att signalen kan vara regim- eller bolagsberoende snarare än robust över hela marknaden.")
            per_symbol = uni.get("per_symbol")
            if isinstance(per_symbol, pd.DataFrame) and not per_symbol.empty:
                st.markdown("#### Resultat per aktie")
                shown_uni = per_symbol.copy()
                shown_uni["Träffsäkerhet"] = (shown_uni["win_rate"] * 100).round(1)
                shown_uni["Jämförelse %"] = (shown_uni["baseline_win_rate"] * 100).round(1)
                shown_uni["Median %"] = (shown_uni["median_return"] * 100).round(2)
                shown_uni["Skillnad mot jämförelse %"] = (shown_uni["median_excess"] * 100).round(2)
                shown_uni = shown_uni.rename(columns={"symbol":"Ticker","signals":"Signaler"})
                st.dataframe(shown_uni[["Ticker","Signaler","Träffsäkerhet","Jämförelse %","Median %","Skillnad mot jämförelse %"]].sort_values(["Skillnad mot jämförelse %","Signaler"], ascending=[False,False]), use_container_width=True, hide_index=True)

            st.markdown("#### Portföljtest · flera samtidiga positioner")
            st.caption("Här låtsas Borsify att alla affärer delar på samma pengar. Om flera köpsignaler kommer samma dag prioriteras de högst rankade. Pengar som redan är placerade kan inte användas igen förrän affären är avslutad. Det gör simuleringen mer lik hur en riktig portfölj skulle fungera.")
            pc1, pc2, pc3, pc4 = st.columns(4)
            portfolio_max_positions = pc1.slider("Max samtidiga positioner", 1, 15, 5, 1, key="edge_portfolio_max_positions")
            portfolio_position_pct = pc2.slider("Max allokering per position", 5, 100, 20, 5, key="edge_portfolio_position_pct")
            portfolio_commission = pc3.number_input("Portfölj · courtage t/r (bps)", min_value=0.0, max_value=200.0, value=10.0, step=5.0, key="edge_portfolio_commission")
            portfolio_execution = pc4.number_input("Portfölj · spread/slippage t/r (bps)", min_value=0.0, max_value=300.0, value=20.0, step=5.0, key="edge_portfolio_execution")

            use_risk_sizing = st.toggle("Anpassa köpets storlek efter hur mycket aktien brukar svänga", value=True, key="edge_portfolio_risk_sizing", help="Aktier som brukar svänga mycket får en mindre plats i den simulerade portföljen.")
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
                pp4.metric("Största fall från topp", f"{portfolio['max_drawdown']:.1%}", help=beginner_term("drawdown"))
                pp5.metric("Snittexponering", f"{portfolio['avg_exposure']:.0%}")
                pp6.metric("Vinst/förlust-kvot", f"{portfolio['profit_factor']:.2f}" if np.isfinite(portfolio['profit_factor']) else "—", help=beginner_term("profit factor"))
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

                    if benchmark_symbol:
                        st.markdown(f"#### Borsify mot {benchmark_name} · samma tidsperiod")
                    else:
                        st.markdown("#### Jämförelse med marknaden")
                        st.info("Det nordiska urvalet innehåller aktier från Danmark, Norge och Finland. Därför visar Borsify ingen enda marknadsjämförelse här – en sådan jämförelse skulle lätt bli missvisande.")
                    try:
                        bench_raw = yf.download(benchmark_symbol, start=pd.Timestamp(eq.index.min()).date().isoformat(), end=(pd.Timestamp(eq.index.max()) + pd.Timedelta(days=2)).date().isoformat(), interval="1d", auto_adjust=False, progress=False, threads=False) if benchmark_symbol else pd.DataFrame()
                    except Exception:
                        bench_raw = pd.DataFrame()
                    bench_close = _download_close_series(bench_raw, benchmark_symbol or "")
                    if not bench_close.empty:
                        compare_index = pd.DatetimeIndex(pd.to_datetime(eq.index)).tz_localize(None)
                        bench_aligned = bench_close.reindex(compare_index).ffill().bfill()
                        if bench_aligned.notna().sum() >= 2 and _num(bench_aligned.iloc[0]) > 0:
                            bq_index = pd.to_numeric(eq["equity"], errors="coerce") / _num(eq["equity"].iloc[0]) * 100
                            omx_index = bench_aligned / _num(bench_aligned.iloc[0]) * 100
                            comparison = pd.DataFrame({"Borsify": bq_index.values, benchmark_name: omx_index.values}, index=compare_index)
                            st.line_chart(comparison, use_container_width=True)
                            bq_stats = _performance_stats(pd.Series(bq_index.values, index=compare_index))
                            omx_stats = _performance_stats(pd.Series(omx_index.values, index=compare_index))
                            bm1, bm2, bm3, bm4 = st.columns(4)
                            bm1.metric("Borsify total", f"{bq_stats['return']:+.1%}" if np.isfinite(bq_stats['return']) else "—", f"{benchmark_name} {omx_stats['return']:+.1%}" if np.isfinite(omx_stats['return']) else None)
                            bm2.metric("Genomsnittlig utveckling per år", f"{bq_stats['cagr']:+.1%}" if np.isfinite(bq_stats['cagr']) else "—", f"{benchmark_name} {omx_stats['cagr']:+.1%}" if np.isfinite(omx_stats['cagr']) else None, help="Ungefär vilken årlig tillväxttakt som skulle ge samma totalresultat över perioden.")
                            bm3.metric("Max fall från topp", f"{bq_stats['max_drawdown']:.1%}" if np.isfinite(bq_stats['max_drawdown']) else "—", f"{benchmark_name} {omx_stats['max_drawdown']:.1%}" if np.isfinite(omx_stats['max_drawdown']) else None, help=beginner_term("drawdown"))
                            bm4.metric("Avkastning i förhållande till svängningar", f"{bq_stats['sharpe']:.2f}" if np.isfinite(bq_stats['sharpe']) else "—", f"{benchmark_name} {omx_stats['sharpe']:.2f}" if np.isfinite(omx_stats['sharpe']) else None, help=beginner_term("Sharpe"))
                            excess = bq_stats["return"] - omx_stats["return"] if np.isfinite(bq_stats["return"]) and np.isfinite(omx_stats["return"]) else np.nan
                            if np.isfinite(excess):
                                if excess > .02:
                                    st.success(f"Enkelt uttryckt: i den här historiska simuleringen gick Borsify cirka {excess:+.1%} bättre än jämförelsen totalt. Titta också på hur stora fallen varit längs vägen – hög avkastning är mindre imponerande om risken varit mycket större.")
                                elif excess < -.02:
                                    st.warning(f"Enkelt uttryckt: i den här historiska simuleringen gav Borsify cirka {abs(excess):.1%} sämre total avkastning än {benchmark_name}. Då hade ett enkelt indexalternativ varit bättre under samma period.")
                                else:
                                    st.info(f"Enkelt uttryckt: Borsify och {benchmark_name} gav ungefär samma totalresultat under perioden. Då blir det extra viktigt att jämföra hur stora fallen varit och hur mycket handeln kostat.")
                            st.caption(f"Borsify och {benchmark_name} startas båda på värdet 100 för att göra utvecklingen lätt att jämföra. Utdelningar kan saknas i jämförelsen, så resultatet är ungefärligt.")
                    else:
                        st.info("Borsify kunde inte hämta marknadsdata för exakt samma period. Därför visas ingen marknadsjämförelse i den här körningen.")

                rejected = int(portfolio.get("rejected_capacity", 0))
                if rejected > 0:
                    st.caption(f"{rejected} signaler kunde inte öppnas eftersom portföljen redan var full eller saknade ledigt kapital. Det är avsiktligt: universumsignaler får inte låtsas använda samma kapital flera gånger samtidigt.")
                if portfolio["total_return"] <= 0 or (np.isfinite(portfolio["profit_factor"]) and portfolio["profit_factor"] < 1.0):
                    st.error("När signalerna konkurrerar om samma kapitalpool håller strategin inte ihop med dessa antaganden. Ett bra signaltest är alltså inte tillräckligt för att motivera modellen.")
                elif portfolio["max_drawdown"] <= -.25:
                    st.warning("Den simulerade portföljen har gått med vinst historiskt, men den har också haft stora fall från tidigare toppar. Risken behöver därför förbättras innan resultatet kan ses som stabilt.")
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
                benchmark_uni = yf.download(benchmark_symbol, period=period, interval="1d", auto_adjust=False, progress=False, threads=False) if benchmark_symbol else pd.DataFrame()
            except Exception:
                benchmark_uni = pd.DataFrame()
            regime_uni_hist = build_market_regime_history(benchmark_uni)
            regime_uni = summarize_universe_backtest_by_regime(histories, regime_uni_hist, score_col_uni, uni_threshold, uni_horizon)
            if regime_uni.empty:
                st.info("Ingen tillräcklig regimdata kunde byggas för universumtestet.")
            else:
                ru = regime_uni.copy()
                ru["Träffsäkerhet %"] = (ru["win_rate"] * 100).round(1)
                ru["Jämförelse %"] = (ru["baseline_win_rate"] * 100).round(1)
                ru["Median %"] = (ru["median_return"] * 100).round(2)
                ru["Skillnad mot jämförelse %"] = (ru["median_excess"] * 100).round(2)
                ru = ru.rename(columns={"regime":"Regim","symbols_with_signals":"Aktier","signals":"Signaler","profit_factor":"Vinst/förlust-kvot"})
                st.dataframe(ru[["Regim","Aktier","Signaler","Träffsäkerhet %","Jämförelse %","Median %","Skillnad mot jämförelse %","Vinst/förlust-kvot"]], use_container_width=True, hide_index=True)
                robust = regime_uni[(regime_uni["signals"] >= 100) & (regime_uni["symbols_with_signals"] >= 10)]
                if len(robust) >= 2:
                    spread = float(robust["median_excess"].max() - robust["median_excess"].min())
                    if spread >= .02:
                        st.warning("Signalen är tydligt regimberoende i universumtestet. Det talar för att Borsify senare bör justera SWING/REVERSAL-kraven efter marknadsläget i stället för att använda samma tröskel hela tiden.")
                    else:
                        st.success("Signalen ser ganska jämn ut i de olika typer av börsperioder där det finns tillräckligt med historik. Det är positivt, men vi behöver fortfarande kontrollera köp- och säljkostnader och senare testperioder.")


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
    avanza_universe_df = load_avanza_universe(AVANZA_UNIVERSE_PATH)

    with st.sidebar:
        st.header("Hitta aktier")
        st.markdown("### Vad letar du efter?")
        discovery_intent = st.selectbox(
            "Mitt mål", DISCOVERY_INTENTS, index=0,
            help="Välj med vanliga ord. Borsify översätter målet till en ranking bakom kulisserna.",
        )
        st.caption(intent_plain_text(discovery_intent))

        market = st.selectbox("Marknad", list(MARKET_CONFIGS), index=list(MARKET_CONFIGS).index("Alla marknader"), help="Byt land/region. Borsify använder samma grundmodell men jämför bolag inom det valda universumet.")
        if market == "Sverige":
            universe = st.radio("Universum", ["OMXS30", "Sverige bred", "Egen lista"], index=1)
            custom = st.text_area("Tickers", value="INVE-B.ST, VOLV-B.ST, SAND.ST, EVO.ST", height=100) if universe == "Egen lista" else ""
            if universe == "Sverige bred":
                st.caption(f"{len(file_universe_symbols)} svenska aktier i nuvarande universum.")
        else:
            custom = ""
            country_map = {
                "Norden exkl. Sverige": ["Danmark","Norge","Finland"],
                "Alla marknader": sorted(avanza_universe_df["Land"].unique().tolist()) if not avanza_universe_df.empty else [],
            }
            countries_for_market = country_map.get(market, [market])
            universe_mode = st.radio(
                "Universum",
                ["Snabbt kärnurval", "Brett universum (beta)"],
                index=0,
                help="Brett universum använder Borsifys växande Avanza-inspirerade katalog. Första körningen kan ta längre tid eftersom fler bolag måste kontrolleras.",
            )
            broad_universe = universe_mode == "Brett universum (beta)"
            universe = universe_mode
            if not avanza_universe_df.empty:
                candidate_count = len(universe_symbols(avanza_universe_df, countries_for_market, broad=broad_universe))
                st.caption(f"{candidate_count} aktier i valt universum över {len(countries_for_market)} land/länder.")
            else:
                st.caption("Brett universum kunde inte läsas. Borsify använder reservlistan.")

        with st.expander("Fler filter", expanded=False):
            profile = st.selectbox("Borsify-strategi", list(PROFILE_WEIGHTS), index=0, help="Påverkar grundscoren. Om du är osäker kan Balanserad vara kvar.")
            default_cap = 5.0 if market == "Sverige" else 0.0
            default_turnover = 5.0 if market == "Sverige" else 0.0
            min_market_cap = st.number_input("Min börsvärde (mdr SEK)", 0.0, value=default_cap, step=1.0, help="Utländska börsvärden räknas om till SEK med senaste tillgängliga valutakurs. Lämna 0 om du inte vill filtrera på storlek.")
            min_turnover = st.number_input("Min omsättning/dag (miljoner SEK)", 0.0, value=default_turnover, step=1.0, help="Även utländsk handel räknas om till SEK så att filtret blir jämförbart mellan marknader.")
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

    market_config = MARKET_CONFIGS.get(market, {})
    benchmark_symbol = market_config.get("benchmark")
    benchmark_name = market_config.get("benchmark_name", "Jämförelseindex")

    if market == "Sverige":
        symbols = OMXS30_TICKERS if universe == "OMXS30" else (file_universe_symbols if universe == "Sverige bred" else parse_symbols(custom))
    else:
        country_map = {
            "Norden exkl. Sverige": ["Danmark","Norge","Finland"],
            "Alla marknader": sorted(avanza_universe_df["Land"].unique().tolist()) if not avanza_universe_df.empty else [],
        }
        countries_for_market = country_map.get(market, [market])
        if not avanza_universe_df.empty:
            symbols = universe_symbols(avanza_universe_df, countries_for_market, broad=(universe == "Brett universum (beta)"))
        else:
            symbols = MARKET_UNIVERSES[market]
    if refresh: st.cache_data.clear()
    if not symbols: st.warning("Ange minst en ticker."); st.stop()

    qc_states_before = get_universe_qc_states()
    quarantine_symbols = active_quarantine_symbols(qc_states_before)
    retry_quarantine = st.sidebar.checkbox(
        "Omtesta karantän denna körning",
        value=False,
        help="Normalt hoppas återkommande problemtickers över i 7 dagar. Slå på detta om du vill tvinga fram ett nytt test nu.",
    )
    requested_symbols = list(dict.fromkeys(symbols))
    if retry_quarantine:
        scan_symbols = requested_symbols
    else:
        scan_symbols = [sym for sym in requested_symbols if str(sym).upper() not in quarantine_symbols]
    skipped_quarantine = [sym for sym in requested_symbols if sym not in scan_symbols]
    st.session_state["bq_qc_skipped_quarantine"] = int(len(skipped_quarantine))

    if not scan_symbols:
        st.warning("Alla valda tickers ligger just nu i QC-karantän. Aktivera 'Omtesta karantän denna körning' för att prova dem igen.")
        st.stop()

    start = time.perf_counter()
    with st.spinner(f"Borsify analyserar {len(scan_symbols)} aktier…"):
        raw_df, errors = scan_universe(scan_symbols)
    if raw_df.empty:
        st.error("Ingen marknadsdata kunde hämtas. Yahoo Finance kan tillfälligt begränsa anrop.")
        if errors: st.code("\n".join(errors[:12]))
        st.stop()

    raw_df, fx_rates, missing_fx = add_sek_conversions(raw_df)
    if missing_fx:
        errors.append("Valutaomräkning saknas för: " + ", ".join(missing_fx))

    raw_df = apply_universe_quality(raw_df)
    qc_all_fetched = raw_df.copy()
    raw_df, qc_rejected = filter_rankable_universe(raw_df)
    st.session_state["bq_qc_hard_rejected"] = int(len(qc_rejected))

    # Persist at most one equivalent QC observation per ticker/day, so Streamlit
    # reruns do not manufacture failure streaks. Provider-wide outages are guarded
    # against: missing fetches only count as strikes when enough of the batch worked.
    prior_lookup = {
        str(r.get("symbol") or "").upper(): r
        for _, r in qc_states_before.iterrows()
    } if not qc_states_before.empty else {}
    fetched_symbols = set(qc_all_fetched.get("Ticker", pd.Series(dtype=str)).astype(str).str.upper().tolist())
    health = scan_health(len(fetched_symbols), len(scan_symbols))
    st.session_state["bq_qc_scan_health"] = float(health["success_ratio"])
    st.session_state["bq_qc_provider_healthy"] = bool(health["provider_healthy_enough"])
    st.session_state["bq_qc_provider_rule"] = str(health.get("provider_health_rule") or "")

    for _, qc_row in qc_all_fetched.iterrows():
        sym = str(qc_row.get("Ticker") or "").upper()
        status = str(qc_row.get("Universe QC") or "")
        outcome = "verified" if status == "VERIFIERAD" else ("partial" if status == "DELVIS VERIFIERAD" else "hard_failure")
        prev = prior_lookup.get(sym)
        if should_record_qc_outcome(prev, outcome):
            state = evolve_qc_state(
                prev, symbol=sym, outcome=outcome,
                reason=str(qc_row.get("Universe QC Problem") or ""),
                count_failure=True,
            )
            save_universe_qc_state(state, outcome, counted_failure=(outcome == "hard_failure"))
            prior_lookup[sym] = state

    missing_fetch_symbols = [str(sym).upper() for sym in scan_symbols if str(sym).upper() not in fetched_symbols]
    for sym in missing_fetch_symbols:
        prev = prior_lookup.get(sym)
        if not should_record_qc_outcome(prev, "hard_failure" if health["provider_healthy_enough"] else "transient_failure"):
            continue
        counted = bool(health["provider_healthy_enough"])
        outcome = "hard_failure" if counted else "transient_failure"
        state = evolve_qc_state(
            prev, symbol=sym, outcome=outcome,
            reason=("ingen kurshistorik kunde verifieras" if counted else "brett datakällefel misstänks – ingen QC-strike"),
            count_failure=counted,
        )
        save_universe_qc_state(state, outcome, counted_failure=counted)
        prior_lookup[sym] = state

    if not qc_rejected.empty:
        for _, rejected_row in qc_rejected.iterrows():
            errors.append(
                f"{rejected_row.get('Ticker','?')}: Universe QC exkluderad · "
                f"{rejected_row.get('Universe QC Problem','otillräcklig datakvalitet')}"
            )
    if raw_df.empty:
        st.error("Ingen aktie hade tillräcklig marknadsdatakvalitet för ranking.")
        st.stop()

    scored = add_scores(raw_df, profile)
    scored = add_data_trust(scored)
    save_score_history(scored, profile)

    # v2.64: validate a possible future price-only prefilter against the full
    # analysis. This does NOT reduce today's Yahoo calls or change rankings.
    try:
        validation_targets: set[str] = set(
            scored.sort_values(["Borsify Score","Datatäckning"],ascending=[False,False])
            .head(5)["Ticker"].astype(str).tolist()
        )
        for validation_horizon in ("day","medium","long","lifetime"):
            validation_top = top_three(scored, validation_horizon)
            if not validation_top.empty:
                validation_targets.update(validation_top["Ticker"].astype(str).tolist())
        prefilter_validation = validate_candidate_pool(
            scored, validation_targets, fraction=.60, minimum=80
        )
        save_prefilter_validation(
            DB_PATH, market, prefilter_validation, APP_VERSION
        )
        st.session_state["bq_prefilter_validation"] = prefilter_validation
    except Exception:
        st.session_state["bq_prefilter_validation"] = {}

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
    top = filtered.head(top_n).copy(); daily_shortlist = build_daily_shortlist(filtered, profile, limit=min(5, len(filtered)))
    elapsed = time.perf_counter() - start
    if market == "Alla marknader":
        st.caption("Jämförelse med världsmarknaden: Borsify använder fonden VT, som äger aktier från många olika länder, för att få en enkel jämförelse. Det hjälper dig att se om Borsifys resultat varit bättre eller sämre än världsmarknaden i stort. Jämförelsen är ungefärlig, inte ett facit.")

    price_dates = sorted({str(x) for x in raw_df.get("Prisdatum", pd.Series(dtype=str)).dropna().tolist() if str(x) != "—"})
    latest_price_date = price_dates[-1] if price_dates else "—"
    idx = fetch_index_snapshot(benchmark_symbol) if benchmark_symbol else {}
    market_note = f" · {benchmark_name} {idx['index']:.0f} ({fmt_pct(idx.get('daily'))})" if idx else ""
    fx_note = ""
    if market != "Sverige":
        converted = int(pd.to_numeric(raw_df.get("Pris SEK", pd.Series(dtype=float)), errors="coerce").notna().sum())
        fx_note = f" · SEK-omräkning {converted}/{len(raw_df)} aktier"
    st.caption(f"{len(raw_df)} aktier analyserade · {len(filtered)} kvar efter dina val · kursdata {latest_price_date}{market_note}{fx_note}")
    scan_metrics = st.session_state.get("bq_scan_metrics", {})
    if isinstance(scan_metrics, dict) and scan_metrics:
        cache_hits = int(scan_metrics.get("fundamental_persistent_cache", 0) or 0)
        yahoo_fund = int(scan_metrics.get("fundamental_yahoo", 0) or 0)
        rejected_early = int(scan_metrics.get("price_rejected_before_fundamentals", 0) or 0)
        st.caption(
            f"Bolagsdata denna körning: {cache_hits} från 24-timmarscache · {yahoo_fund} nya Yahoo-hämtningar"
            + (f" · {rejected_early} aktier stoppades redan på kursdata" if rejected_early else "")
        )
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

    page = st.radio(
        "Välj vy",
        ["Överblick", "Upptäck", f"Bevakning ({len(watch_df_global)})", "Analysera", "Metod"],
        horizontal=True,
        label_visibility="collapsed",
        key="main_page",
    )
    if page == "Överblick":
        render_overview(daily_shortlist, filtered, scored, watch_df_global, signal_history_global, unread_signals, profile, idx, elapsed, latest_price_date, market, benchmark_name)
    elif page == "Upptäck":
        st.caption(
            "Fördjupad kandidatgranskning körs först när du öppnar Upptäck. "
            "Det gör startsidan snabbare utan att ta bort analysen."
        )
        with st.spinner("Fördjupar de starkaste kandidaterna…"):
            deep_longlist = build_deep_longlist(
                filtered, pool_size=min(6, len(filtered)), limit=min(5, len(filtered))
            )
            deep_longlist = add_data_trust(deep_longlist)
            short_longlist = build_short_term_longlist(
                filtered, idx, pool_size=min(8, len(filtered)), limit=min(5, len(filtered))
            )
            short_longlist = add_data_trust(short_longlist)

        # Freeze only analyses that were actually run. This preserves point-in-time
        # history without forcing every homepage visit to perform deep Yahoo requests.
        ledger_records = build_recommendation_records(
            short_longlist, "short", APP_VERSION, profile, market, max_records=5
        ) + build_recommendation_records(
            deep_longlist, "long", APP_VERSION, profile, market, max_records=5
        )
        save_recommendation_records(ledger_records)

        try:
            relevance_ledger = get_recommendation_records(limit=500)
            relevance_date = pd.Timestamp.now(tz="UTC").date().isoformat()
            short_longlist = apply_recommendation_relevance(
                short_longlist, relevance_ledger, "short", profile, market, relevance_date
            )
            deep_longlist = apply_recommendation_relevance(
                deep_longlist, relevance_ledger, "long", profile, market, relevance_date
            )
        except Exception:
            pass

        try:
            short_longlist = apply_case_plans(short_longlist, "short")
            deep_longlist = apply_case_plans(deep_longlist, "long")
        except Exception:
            pass

        try:
            refresh_due_recommendation_outcomes(max_records=6)
        except Exception:
            pass

        discover_daily, discover_ideas, discover_radar = st.tabs(["Dagens fynd", "Idéflöde", f"Radar ({unread_signals})"])
        with discover_daily:
            st.info(f"Du letar efter: **{discovery_intent}**. {intent_plain_text(discovery_intent)}")

            st.subheader("Bästa kortsiktiga case · 1–6 månader")
            st.caption("För kortsiktiga köp vill Borsify se flera saker samtidigt: att kursen utvecklas bra jämfört med marknaden, att trenden ser positiv ut och att handeln i aktien är aktiv. Om färska vinstprognoser eller tydliga kommande händelser finns vägs de också in. Ett stort kursfall räcker inte för att aktien ska bli ett köpcase.")
            if short_longlist.empty:
                st.info("Ingen kortsiktig kandidat kunde analyseras.")
            else:
                for rank, (_, case) in enumerate(short_longlist.iterrows(), start=1):
                    with st.container(border=True):
                        s1, s2 = st.columns([4.0, 1.0])
                        s1.markdown(f"### {rank}. {case.get('Namn', case.get('Ticker'))} · {case.get('Ticker')}")
                        s1.caption(f"{case.get('Sektor','—')} · horisont cirka 1–6 månader")
                        short_score = _num(case.get("Short Alpha Score"))
                        s2.metric("Borsifys huvudbetyg", f"{short_score:.0f}/100" if np.isfinite(short_score) else "—")
                        short_conf = _num(case.get("Short Alpha Confidence"))
                        short_confirm = int(_num(case.get("Short Confirmation Count"))) if np.isfinite(_num(case.get("Short Confirmation Count"))) else 0
                        if np.isfinite(short_conf) and short_conf >= 75 and short_confirm >= 4:
                            st.caption("**Underlag:** gott · flera separata delar bekräftar caset")
                        elif np.isfinite(short_conf) and short_conf >= 55:
                            st.caption("**Underlag:** användbart men inte komplett")
                        else:
                            st.caption("**Underlag:** begränsat – kontrollera datan extra noga")
                        render_recommendation_price(case)
                        render_recommendation_relevance(case)
                        gate = str(case.get("Short Alpha Gate", "Svag kortsiktig signal"))
                        if gate == "Kortsiktigt toppcase":
                            st.success(gate)
                        elif gate == "Starkt kortsiktigt case":
                            st.info(gate)
                        elif gate == "Ej kortsiktigt toppcase":
                            st.warning(gate)
                        else:
                            st.caption(gate)
                        st.markdown("**VARFÖR NU?**")
                        st.write(str(case.get("Short Why Now", "Ingen stark kombination av bekräftande signaler.")))
                        x1, x2 = st.columns(2)
                        with x1:
                            st.markdown("**Vad kan få marknaden att ändra syn?**")
                            st.write(plain_finance_text(f"{case.get('Catalyst Signal','Ingen tydlig händelse verifierad')} · {case.get('Inflection Signal','För lite data om förändringar')}"))
                            if str(case.get("Primary Catalyst", "Ingen verifierad")) != "Ingen verifierad":
                                st.caption(plain_finance_text(f"{case.get('Primary Catalyst')} · {case.get('Catalyst Timing','—')}"))
                        with x2:
                            st.markdown("**Viktigaste motargumentet**")
                            st.write(plain_finance_text(case.get("Short Counterargument", "—")))
                        cautions = str(case.get("Short Cautions", "—"))
                        vetoes = str(case.get("Short Vetoes", "—"))
                        if vetoes != "—":
                            st.warning(f"Det här kan stoppa köpcaset: {plain_finance_text(vetoes)}")
                        elif cautions != "—":
                            st.caption(f"Det här behöver kontrolleras: {plain_finance_text(cautions)}")
                        with st.expander("Visa kortsiktiga delsignaler och underlag"):
                            st.write({
                                "Underlagets detaljpoäng": case.get("Short Alpha Confidence", "—"),
                                "Antal separata bekräftelser": case.get("Short Confirmation Count", "—"),
                                "Relativ styrka": case.get("Short Relative Strength", "—"),
                                "Trend": case.get("Short Trend", "—"),
                                "Kursstyrka den senaste tiden": case.get("Short Momentum", "—"),
                                "Handelsaktivitet": case.get("Short Participation", "—"),
                                "Ändringar i vinstprognoser": plain_finance_text(case.get("Short Revisions", "—")),
                                "Händelse som kan ändra marknadens syn": plain_finance_text(case.get("Short Catalyst", "—")),
                                "Underlag för den händelsen": plain_finance_text(case.get("Catalyst Evidence", "—")),
                            })
                        render_case_plan(case)
                        render_case_ai_qa(case, "short", rank)

            st.divider()

            st.subheader("Bästa långsiktiga case · flerårig djupkontroll")
            st.caption("Borsify väljer först ut starka långsiktiga kandidater. Därefter krävs stöd från flera olika håll: bolagets utveckling över flera år, om något nyligen blivit bättre eller sämre, om priset verkar rimligt och om det finns en tydlig händelse som kan ändra marknadens syn. En allvarlig varning eller för lite data kan stoppa ett toppcase.")
            if deep_longlist.empty:
                st.info("Ingen kandidat kunde djupkontrolleras.")
            else:
                for rank, (_, case) in enumerate(deep_longlist.iterrows(), start=1):
                    with st.container(border=True):
                        a, b = st.columns([4.0, 1.0])
                        a.markdown(f"### {rank}. {case.get('Namn', case.get('Ticker'))} · {case.get('Ticker')}")
                        a.caption(f"{case.get('Sektor','—')} · flerårsdata t.o.m. {case.get('Rapportdatum','—')}")
                        invest_score = _num(case.get("INVEST Score"))
                        b.metric("Borsifys huvudbetyg", f"{invest_score:.0f}/100" if np.isfinite(invest_score) else "—")
                        trap = _num(case.get('Value Trap Risk')); conf = _num(case.get('Deep Confidence'))
                        infl = _num(case.get('Inflection Score'))
                        case_conf_preview = _num(case.get("Case Confidence"))
                        evidence_preview = int(_num(case.get("Case Evidence Count"))) if np.isfinite(_num(case.get("Case Evidence Count"))) else 0
                        if np.isfinite(case_conf_preview) and case_conf_preview >= 75 and evidence_preview >= 4:
                            st.caption("**Underlag:** gott · flera oberoende delar stödjer caset")
                        elif np.isfinite(conf) and conf >= 55:
                            st.caption("**Underlag:** användbart men kräver fortsatt kontroll")
                        else:
                            st.caption("**Underlag:** begränsat")
                        with st.expander("Visa delbedömningar"):
                            st.write({
                                "Risk för värdefälla": round(trap,1) if np.isfinite(trap) else "—",
                                "Förändringsbedömning": round(infl,1) if np.isfinite(infl) else "—",
                                "Prisbedömning": plain_finance_text(case.get("Mispricing Signal","—")),
                                "Underlagets detaljpoäng": round(conf,1) if np.isfinite(conf) else "—",
                                "Oberoende stöd": evidence_preview,
                            })
                        render_recommendation_price(case)
                        render_recommendation_relevance(case)
                        gate = plain_finance_text(case.get('Djupkontroll','Otillräcklig data'))
                        signal = plain_finance_text(case.get('Inflection Signal','För lite data om förändringar'))
                        if gate == "Klarar djupkontroll": st.success(f"{gate} · {signal}")
                        elif gate in {"Avstå tills vidare", "Hög value-trap-risk"}: st.error(f"{gate} · {signal}")
                        elif gate == "Otillräcklig data": st.warning(f"{gate} · {signal}")
                        else: st.info(f"{gate} · {signal}")
                        case_gate = plain_finance_text(case.get("Case Gate", "Bevaka"))
                        case_conf = _num(case.get("Case Confidence"))
                        evidence_count = int(_num(case.get("Case Evidence Count"))) if np.isfinite(_num(case.get("Case Evidence Count"))) else 0
                        if case_gate == "Toppcase":
                            st.success(f"🏆 **{case_gate}** · flera oberoende stöd")
                        elif case_gate == "Starkt case":
                            st.success(f"**{case_gate}** · flera delar stödjer samma slutsats")
                        elif case_gate in {"Ej toppcase", "Bevaka – motbevis finns"}:
                            st.warning(f"**{case_gate}**")
                        else:
                            st.info(f"**{case_gate}**")
                        st.caption("Detaljer om hur många stöd och hur komplett underlaget är finns under delbedömningarna.")
                        trust_status = str(case.get("Data Trust status","") or "")
                        if trust_status:
                            st.markdown("**Datakoll**")
                            trust_line = (
                                f"{trust_status} · källa: {case.get('Data Trust källa','Yahoo Finance via yfinance')} · "
                                f"kurs: {case.get('Data Trust kursdatum','—')} · {case.get('Data Trust rapportstatus','Rapportdatum saknas')}"
                            )
                            if trust_status == "GOTT UNDERLAG":
                                st.success(trust_line)
                            elif trust_status == "STOPP":
                                st.error(trust_line)
                            else:
                                st.warning(trust_line)

                        earnings_quality_status = str(case.get("Vinstkvalitet status","") or "")
                        earnings_quality_score = _num(case.get("Vinstkvalitet"))
                        if earnings_quality_status:
                            st.markdown("**Blir vinsten faktiskt pengar?**")
                            if earnings_quality_status == "STARK VINSTKVALITET":
                                st.success(
                                    f"{earnings_quality_status}"
                                )
                            elif earnings_quality_status in {"SVAG VINSTKVALITET","KRÄVER KONTROLL"}:
                                st.warning(
                                    f"{earnings_quality_status}"
                                )
                            else:
                                st.info(
                                    f"{earnings_quality_status}"
                                )
                            eq_warn = str(case.get("Vinstkvalitet varningar","") or "")
                            if eq_warn and eq_warn != "inga tydliga varningssignaler i tillgängliga data":
                                st.caption(eq_warn)
                            st.caption(
                                "Borsify jämför redovisad vinst med verkligt kassaflöde och kontrollerar om kundfordringar eller lager växer snabbare än försäljningen."
                            )

                        operating_change = str(case.get("Operativ förändring","") or "")
                        operating_quality = _num(case.get("Operativ förändringskvalitet"))
                        if operating_change:
                            st.markdown("**Vad förändras i själva bolaget?**")
                            if operating_change == "Bred fundamental förbättring":
                                st.success(f"{operating_change}")
                            elif operating_change in {"Bred fundamental försämring","Övervägande försämring"}:
                                st.warning(f"{operating_change}")
                            else:
                                st.info(f"{operating_change}")
                            conflict_text = str(case.get("Förändringskonflikt","") or "")
                            if conflict_text and not conflict_text.startswith("Ingen tydlig konflikt"):
                                st.warning(conflict_text)
                            st.caption("Detta bygger på observerad försäljning, marginal, vinst, kassaflöde och skuld när uppgifterna finns – separat från analytikernas prognoser.")
                        st.markdown("**VARFÖR NU?**")
                        st.write(plain_finance_text(case.get('Catalyst Why Now') or case.get('Varför nu','Borsify kan inte verifiera någon tydlig ny förändring just nu.')))
                        cat_signal = plain_finance_text(case.get("Catalyst Signal", "Ingen tydlig händelse som kan ändra marknadens syn har verifierats"))
                        cat_conf = _num(case.get("Catalyst Confidence"))
                        if cat_signal == "Tydlig möjlig katalysator":
                            st.success(f"**Det som kan ändra marknadens syn:** {case.get('Primary Catalyst','—')} · {case.get('Catalyst Timing','—')}")
                        elif cat_signal == "Ny risk måste verifieras först":
                            st.warning(f"**Kommande händelse eller risk:** {cat_signal}. {case.get('Catalyst Warnings','')}")
                        else:
                            st.info(f"**Det som kan ändra marknadens syn:** {cat_signal} · {case.get('Primary Catalyst','—')} · {case.get('Catalyst Timing','—')}")
                        st.caption(plain_finance_text(case.get("Catalyst Evidence", "Det finns för lite data om kommande händelser.")))
                        st.markdown("**VAD VERKAR PRISET KRÄVA?**")
                        base_req = _num(case.get("Implied EPS CAGR @ exit P/E 20"))
                        verified_growth = _num(case.get("Verifierad tillväxtproxy"))
                        if np.isfinite(base_req):
                            st.write(
                                f"Om du vill ha ungefär 10 % avkastning per år och aktien värderas till P/E 20 om fem år, behöver vinsten per aktie växa ungefär **{base_req:.1%} per år**. "
                                + (f"Den tillväxt Borsify faktiskt kan belägga ({case.get('Tillväxtkälla','—')}) är **{verified_growth:.1%}**." if np.isfinite(verified_growth) else "Borsify saknar tillräckligt bra tillväxtdata för att jämföra med detta.")
                            )
                        else:
                            st.write("Borsify saknar tillräcklig värderingsdata för att räkna ut vilken framtida vinsttillväxt dagens aktiepris verkar kräva.")
                        st.write(f"**Verkar aktien felprissatt?** {plain_finance_text(case.get('Mispricing Signal','Kan inte bedömas'))}. {plain_finance_text(case.get('Varför marknaden kan ha fel 2.0',''))}")
                        if case.get("Inflection Gate Note"):
                            st.warning(plain_finance_text(case.get("Inflection Gate Note")))
                        if case.get("Mispricing Gate Note"):
                            st.warning(plain_finance_text(case.get("Mispricing Gate Note")))
                        st.markdown("**TRE MÖJLIGA FRAMTIDSBILDER**")
                        if str(case.get("Scenario Status", "")) == "OK":
                            s1, s2, s3, s4 = st.columns(4)
                            s1.metric("Svagt scenario", fmt_pct(case.get("Bear upside")), help=f"Antagande: EPS-tillväxt {fmt_pct(case.get('Bear EPS growth'))}, exit P/E {_num(case.get('Bear exit P/E')):.1f}")
                            s2.metric("Grundscenario", fmt_pct(case.get("Base upside")), help=f"Antagande: EPS-tillväxt {fmt_pct(case.get('Base EPS growth'))}, exit P/E {_num(case.get('Base exit P/E')):.1f}")
                            s3.metric("Starkt scenario", fmt_pct(case.get("Bull upside")), help=f"Antagande: EPS-tillväxt {fmt_pct(case.get('Bull EPS growth'))}, exit P/E {_num(case.get('Bull exit P/E')):.1f}")
                            asym = _num(case.get("Scenario Asymmetry"))
                            s4.metric("Uppsida jämfört med nedsida", f"{asym:.1f}×" if np.isfinite(asym) else "—", help="Jämför möjlig uppsida i grundscenariot med möjlig nedsida i det svaga scenariot. Det är bara en förenklad jämförelse, inte en sannolikhet.")
                            st.caption(plain_finance_text(f"{case.get('Scenario Verdict','—')} · {case.get('Scenario Risk Label','—')}. Det här är möjliga framtidsbilder – inte kursmål eller en prognos."))
                        else:
                            st.info("Framtidsbilder: " + plain_finance_text(case.get('Scenario Note','Otillräcklig data')))
                        if str(case.get("Case Vetoes", "")).strip() and str(case.get("Case Vetoes")) != "inga hårda motbevis i gate-modellen":
                            st.warning("**Det här kan stoppa eller sänka köpcaset:** " + plain_finance_text(case.get("Case Vetoes")))
                        x1, x2, x3 = st.columns(3)
                        x1.markdown("**Varför marknaden kan ha fel**"); x1.write(str(case.get('Varför marknaden kan ha fel','—')))
                        x2.markdown("**Vad data stödjer**"); x2.write(str(case.get('Fleråriga styrkor','—')) + "\n\n" + str(case.get('Positiva förändringar','—')))
                        x3.markdown("**Starkaste argumentet emot**"); x3.write(plain_finance_text(case.get("Devil's Advocate",'—')) + "\n\n" + plain_finance_text(case.get('Negativa förändringar','—')))
                        with st.expander("Visa flerårsdata + färska förändringar"):
                            st.write({
                                "Försäljning · genomsnittlig förändring per år": fmt_pct(case.get("Omsättning CAGR")),
                                "Vinst · genomsnittlig förändring per år": fmt_pct(case.get("Vinst CAGR")),
                                "Fritt kassaflöde · genomsnittlig förändring per år": fmt_pct(case.get("FCF CAGR")),
                                "Flerårig marginalförändring": fmt_pct(case.get("Rörelsemarginal trend")),
                                "Skuldförändring": fmt_pct(case.get("Skuldförändring")),
                                "Andel år med positivt fritt kassaflöde": fmt_pct(case.get("Positiv FCF-andel")),
                                "Försäljning jämfört med samma kvartal förra året": fmt_pct(case.get("Omsättning YoY senaste kvartal")),
                                "Omsättningsacceleration": fmt_pct(case.get("Omsättning acceleration")),
                                "Marginal YoY-förändring": fmt_pct(case.get("Marginal YoY förändring")),
                                "Fritt kassaflöde jämfört med samma kvartal förra året": fmt_pct(case.get("FCF YoY senaste kvartal")),
                                "Andel senaste kvartal med försäljningstillväxt": fmt_pct(case.get("Senaste kvartal positiv omsättning YoY andel")),
                                "Andel senaste kvartal med positivt fritt kassaflöde": fmt_pct(case.get("Senaste kvartal positiv FCF andel")),
                                "Skuld/nettoskuld jämfört med för ett år sedan": fmt_pct(case.get("Senaste skuld/nettoskuld YoY")),
                                "Operativ förändring": str(case.get("Operativ förändring","—")),
                                "Vinstkvalitet": str(case.get("Vinstkvalitet status","—")),
                                "Kassaflöde / redovisad vinst, senaste": fmt_num(case.get("Kassaflöde/vinst senaste"),2),
                                "Kassaflöde / redovisad vinst, median": fmt_num(case.get("Kassaflöde/vinst median"),2),
                                "Fritt kassaflöde / vinst, median": fmt_num(case.get("FCF/vinst median"),2),
                                "Förändring kundfordringar relativt försäljning": fmt_pct(case.get("Kundfordringar/omsättning trend")),
                                "Förändring lager relativt försäljning": fmt_pct(case.get("Lager/omsättning trend")),
                                "Konflikt mellan bolagsdata och analytiker": str(case.get("Förändringskonflikt","—")),
                                "Förändring i analytikernas vinstprognos per aktie": fmt_pct(case.get("EPS-estimat förändring")),
                                "Vinstprognosen jämförs med": case.get("EPS-estimat jämförelseperiod", "—"),
                                "Balans mellan höjda och sänkta vinstprognoser": fmt_pct(case.get("EPS-revisionsbalans")),
                                "Senaste vinst per aktie jämfört med förväntan": fmt_pct(case.get("Senaste EPS-överraskning")),
                                "Krav på årlig vinsttillväxt om P/E är 15 om fem år": fmt_pct(case.get("Implied EPS CAGR @ exit P/E 15")),
                                "Krav på årlig vinsttillväxt om P/E är 20 om fem år": fmt_pct(case.get("Implied EPS CAGR @ exit P/E 20")),
                                "Krav på årlig vinsttillväxt om P/E är 25 om fem år": fmt_pct(case.get("Implied EPS CAGR @ exit P/E 25")),
                                "Krav på tillväxt i fritt kassaflöde": fmt_pct(case.get("FCF growth hurdle")),
                                "Tillväxt Borsify faktiskt kan se": fmt_pct(case.get("Verifierad tillväxtproxy")),
                                "Tillväxtkälla": case.get("Tillväxtkälla", "—"),
                                "Det som talar för att priset kan vara fel": case.get("Mispricing Evidence", "—"),
                                "Det som talar emot att priset är fel": case.get("Mispricing Cautions", "—"),
                                "Slutlig kontroll": case.get("Case Gate", "—"),
                                "Oberoende stöd": case.get("Case Supports", "—"),
                                "Neutrala/oklara delar": case.get("Case Neutrals", "—"),
                                "Hårda motbevis": case.get("Case Vetoes", "—"),
                                "Hur bra underlaget är": case.get("Case Confidence", "—"),
                                "Finns en händelse som kan ändra marknadens syn?": case.get("Catalyst Signal", "—"),
                                "Viktigaste möjliga händelsen": case.get("Primary Catalyst", "—"),
                                "Ungefär när kan den hända?": case.get("Catalyst Timing", "—"),
                                "Vad skulle den kunna förändra?": case.get("Catalyst Effect", "—"),
                                "Underlag för händelsen": case.get("Catalyst Evidence", "—"),
                                "Osäkerheter kring händelsen": case.get("Catalyst Warnings", "—"),
                                "Svagt scenario · vinsttillväxt per aktie": fmt_pct(case.get("Bear EPS growth")),
                                "Svagt scenario · P/E om fem år": case.get("Bear exit P/E", "—"),
                                "Svagt scenario · möjlig utveckling": fmt_pct(case.get("Bear upside")),
                                "Grundscenario · vinsttillväxt per aktie": fmt_pct(case.get("Base EPS growth")),
                                "Grundscenario · P/E om fem år": case.get("Base exit P/E", "—"),
                                "Grundscenario · möjlig utveckling": fmt_pct(case.get("Base upside")),
                                "Starkt scenario · vinsttillväxt per aktie": fmt_pct(case.get("Bull EPS growth")),
                                "Starkt scenario · P/E om fem år": case.get("Bull exit P/E", "—"),
                                "Starkt scenario · möjlig utveckling": fmt_pct(case.get("Bull upside")),
                                "Uppsida jämfört med nedsida": case.get("Scenario Asymmetry", "—"),
                                "Fleråriga varningar": case.get("Fleråriga varningar", "—"),
                            })
                        render_case_plan(case)
                        render_case_ai_qa(case, "long", rank)
                st.caption("Ett lågt aktiepris eller lågt P/E räcker inte. Borsify kan sänka ett bolag om pengar in och ut, lönsamhet, försäljning, skuld eller färska prognoser utvecklas åt fel håll. Analysen kräver flera olika styrkor samtidigt och låter tydliga varningar väga tungt. De tre framtidsbilderna är exempel på vad som kan hända – inte kursmål eller sannolikheter.")

            st.divider()
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
                        with h3:
                            render_recommendation_price(case)
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
                quick_cols = ["Ticker", "Namn", "Pris", "Valuta", "Pris SEK", "Dagsförändring", "Prisdatum", "Borsify Score", "INVEST Score", "SWING Score", "REVERSAL Score", "Dagens relevans", "Prioritet", "Score Δ", "Värdering", "Kvalitet", "Marknadsläge", "Risk", "Riskflaggor"]
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

    elif page.startswith("Bevakning"):
        st.subheader("Min bevakning")
        watch_meta = watch_meta_global
        watched = watched_global
        if st.session_state.get("bq_case_breaker_migration_needed"):
            st.info("Regler för när du ska tänka om fungerar i appen, men databasen behöver uppdateras innan de kan sparas permanent i molnet. Övrig bevakning fungerar som tidigare.")
        if not watched:
            st.info("Bevakningslistan är tom. Lägg till en aktie från detaljanalysen.")
        else:
            st.markdown("#### Case Alert · intern utveckling + nya bolagshändelser")
            st.caption("Bevakningen kopplar ihop dina egna anteckningar, dina regler för när du ska tänka om och nyhetsrubriker. Nyheter ändrar aldrig Borsifys betyg automatiskt. Rubriker används bara som tips om vad du kan behöva läsa vidare om.")
            refresh_watch_media = st.button("Kontrollera senaste media för bevakade case", key="watch_case_alert_refresh", use_container_width=False)
            if refresh_watch_media:
                watch_feed, watch_feed_errors = fetch_idea_flow_cached()
                st.session_state["idea_flow_feed"] = watch_feed
                st.session_state["idea_flow_errors"] = watch_feed_errors
            watch_media_feed = st.session_state.get("idea_flow_feed")
            watch_ideas = pd.DataFrame()
            if isinstance(watch_media_feed, pd.DataFrame) and not watch_media_feed.empty and not watch_df_global.empty:
                watch_mentions = map_mentions(watch_media_feed, watch_df_global)
                watch_ideas = build_verified_ideas(watch_mentions, watch_df_global) if not watch_mentions.empty else pd.DataFrame()
                if not watch_ideas.empty:
                    important = int((pd.to_numeric(watch_ideas.get("Case Impact Nivå", 0), errors="coerce").fillna(0) >= 2).sum())
                    st.caption(f"Mediabevakning matchade {len(watch_ideas)} bevakade aktier · {important} med potentiellt casepåverkande händelse. Händelsernas riktning verifieras inte från rubriken ensam.")
                else:
                    st.caption("Mediabevakningen är hämtad, men inga aktuella rubriker matchade dina bevakade aktier.")
            else:
                st.caption("Ingen mediabevakning är hämtad i den här sessionen ännu. Knappen ovan hämtar den när du vill göra en Case Alert-kontroll.")

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
                    journal = None
                    breaker = None
                    if not current_row.empty:
                        wr = current_row.iloc[0]
                        st.markdown(f"**Borsifys skäl just nu:** {wr.get('Varför','—')}")
                        cp = _num(wr.get("Pris"))
                        if np.isfinite(cp): st.caption(f"Aktuell hämtad kurs: {fmt_price_with_sek(wr)} · kursdag {wr.get('Prisdatum','—')}")
                    if not current_row.empty:
                        hist = get_score_history(sym, profile)
                        wr = current_row.iloc[0]
                        current_case = {
                            "score": _num(wr.get("Borsify Score")),
                            "valuation": _num(wr.get("Värdering")),
                            "quality": _num(wr.get("Kvalitet")),
                            "setup": _num(wr.get("Marknadsläge")),
                            "income": _num(wr.get("Utdelning")),
                            "risk": _num(wr.get("Risk")),
                            "coverage": _num(wr.get("Datatäckning")),
                        }
                        journal = assess_case_change(hist, current_case, meta.get("added_at"))
                        st.markdown("**Case Journal · vad har förändrats?**")
                        delta = journal.get("score_delta")
                        delta_text = f"{float(delta):+.1f} poäng sedan start" if np.isfinite(_num(delta)) else "historiken byggs upp"
                        st.write(f"**{journal.get('status', 'Historiken byggs upp')}** · {delta_text}")
                        days = journal.get("days_followed")
                        if days is not None:
                            st.caption(f"Följd i cirka {int(days)} dagar. Det här beskriver förändringar i Borsifys mätbild – inte ett automatiskt köp- eller säljbeslut.")
                        for change in journal.get("changes", []):
                            st.write(f"• {change}")
                        jt = journal_table(hist)
                        if len(jt) >= 2:
                            with st.expander("Visa sparad utveckling", expanded=False):
                                st.dataframe(jt, use_container_width=True, hide_index=True)
                        else:
                            st.caption("Efter fler dagliga analyser visas en tidslinje här så att du kan se om caset faktiskt utvecklas åt rätt håll.")
                    else:
                        st.caption("Case Journal börjar byggas när aktien har analyserats och sparats i bevakningen.")

                    st.markdown("**Vad skulle få dig att tänka om kring aktien?**")
                    st.caption("Sätt bara gränser som faktiskt skulle få dig att ompröva caset. 0 betyder att regeln är avstängd. Det här är en kontrollista, inte en automatisk säljorder.")
                    b1, b2 = st.columns(2)
                    breaker_min_score = b1.number_input("Minsta Borsify Score", 0.0, 100.0, float(_num(meta.get("breaker_min_score"))) if np.isfinite(_num(meta.get("breaker_min_score"))) else 0.0, 1.0, key=f"breaker_score_{sym}")
                    breaker_min_quality = b2.number_input("Minsta kvalitet", 0.0, 100.0, float(_num(meta.get("breaker_min_quality"))) if np.isfinite(_num(meta.get("breaker_min_quality"))) else 0.0, 1.0, key=f"breaker_quality_{sym}")
                    b3, b4 = st.columns(2)
                    breaker_min_risk = b3.number_input("Minsta riskpoäng", 0.0, 100.0, float(_num(meta.get("breaker_min_risk"))) if np.isfinite(_num(meta.get("breaker_min_risk"))) else 0.0, 1.0, key=f"breaker_risk_{sym}", help="I Borsify betyder högre riskpoäng bättre/tryggare riskbild.")
                    breaker_max_score_drop = b4.number_input("Max scorefall från start", 0.0, 100.0, float(_num(meta.get("breaker_max_score_drop"))) if np.isfinite(_num(meta.get("breaker_max_score_drop"))) else 0.0, 1.0, key=f"breaker_drop_{sym}")
                    if not current_row.empty:
                        breaker_rules = {"min_score": breaker_min_score, "min_quality": breaker_min_quality, "min_risk": breaker_min_risk, "max_score_drop": breaker_max_score_drop}
                        breaker = evaluate_case_breakers(current_case, hist, breaker_rules)
                        status = str(breaker.get("status", ""))
                        if breaker.get("tone") == "negative":
                            st.error(f"**{status}** · {breaker.get('explanation','')}")
                        elif breaker.get("tone") == "warning":
                            st.warning(f"**{status}** · {breaker.get('explanation','')}")
                        elif breaker.get("tone") == "positive":
                            st.success(f"**{status}** · {breaker.get('explanation','')}")
                        else:
                            st.info(f"**{status}** · {breaker.get('explanation','')}")
                        for item in breaker.get("triggered", []): st.write(f"🚨 {item}")
                        for item in breaker.get("near", []): st.write(f"⚠️ {item}")

                    if journal is not None and breaker is not None:
                        idea_row = None
                        if not watch_ideas.empty and "Ticker" in watch_ideas.columns:
                            idea_match = watch_ideas[watch_ideas["Ticker"].astype(str) == sym].head(1)
                            if not idea_match.empty:
                                idea_row = idea_match.iloc[0]
                        case_alert = evaluate_case_alert(journal, breaker, idea_row)
                        st.markdown("**Case Alert · behöver något prioriteras?**")
                        alert_text = f"**{case_alert.get('status','')}** · {case_alert.get('summary','')}"
                        if case_alert.get("tone") == "critical":
                            st.error(alert_text)
                        elif case_alert.get("tone") == "warning":
                            st.warning(alert_text)
                        elif case_alert.get("tone") == "positive":
                            st.success(alert_text)
                        else:
                            st.info(alert_text)
                        for reason in case_alert.get("reasons", []):
                            st.write(f"• {reason}")
                        if idea_row is not None:
                            event_name = str(idea_row.get("Huvudhändelse", "Övrigt / oklart"))
                            pulse_name = str(idea_row.get("Mediepuls", "Ingen tydlig ny puls"))
                            st.caption(f"Senaste externa kontext: {event_name} · {pulse_name}. Case Alert tolkar inte en vanlig rapport som positiv eller negativ utan verifierade fakta.")
                            headlines = idea_row.get("Rubriker") or []
                            if isinstance(headlines, list) and headlines:
                                latest_headline = headlines[0]
                                title = str(latest_headline.get("title", ""))
                                source = str(latest_headline.get("source", ""))
                                link = str(latest_headline.get("link", ""))
                                if title:
                                    st.write(f"Senaste rubrik: **{title}** · {source}")
                                if link:
                                    st.link_button("Öppna originalkällan", link)

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
                        update_watchlist_item(sym, note, target if target > 0 else None, score_threshold, score_move, daily_drop, breaker_min_score, breaker_min_quality, breaker_min_risk, breaker_max_score_drop)
                        st.success("Sparat")
                    if crem.button("Ta bort", key=f"remove_watch_{sym}", use_container_width=True):
                        toggle_watchlist(sym)
                        st.rerun()
            if st.button("Töm bevakningslistan"):
                clear_watchlist()
                st.rerun()
        st.caption("Inloggad användare: bevakning, scorehistorik, radarhistorik och signalhistorik lagras i Supabase. Gäst/lokalt läge: SQLite används på aktuell dator.")
    elif page == "Analysera":
        analyse_market, analyse_edge = st.tabs(["Marknad", "Historiska tester"])
        with analyse_market:
            st.subheader("Marknad · hela analysuniversumet")
            st.caption("Här finns rålistan för jämförelser och egen analys. Överblick och Dagens fynd är de rekommenderade startpunkterna.")
            st.dataframe(dataframe_for_display(scored), use_container_width=True, hide_index=True)
        with analyse_edge:
            default_edge_symbol = str(filtered.iloc[0]["Ticker"]) if not filtered.empty else "INVE-B.ST"
            render_edge_lab(default_edge_symbol, list(symbols), benchmark_symbol, benchmark_name)
    else:  # Metod
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

    st.caption("Konton/molnsynk: Supabase när konfigurerat. Datakälla: Yahoo Finance via yfinance. Sverige bred läses från universe.csv. Utländska marknader använder kuraterade startuniversum. Listorna är inte garanterat kompletta officiella indexlistor. Kontrollera alltid rapporter, nyheter, kassaflöde, skuldsättning och bolagsspecifika händelser före investeringsbeslut.")



if __name__ == "__main__":
    main()
