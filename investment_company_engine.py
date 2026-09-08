from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
import math

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Holding:
    ticker: str
    name: str
    weight: float


@dataclass(frozen=True)
class InvestmentCompanyProfile:
    key: str
    name: str
    symbols: tuple[str, ...]
    nav_per_share: float | None = None
    nav_date: str | None = None
    nav_source: str | None = None
    holdings_date: str | None = None
    holdings_source: str | None = None
    holdings: tuple[Holding, ...] = ()
    listed_portfolio_share: float = 1.0
    note: str = ""


# Conservative curated reference data. Values are explicitly dated and never treated
# as live. The app may compare them with current quotes, but freshness is surfaced.
# Industrivärden: NAV 31 Aug 2026; portfolio weights 30 Jun 2026 (official company site).
# Investor: adjusted NAV 30 Jun 2026. Only the listed sleeve is mapped; unlisted/EQT
# exposures mean a direct-basket comparison is intentionally incomplete.
PROFILES: tuple[InvestmentCompanyProfile, ...] = (
    InvestmentCompanyProfile(
        key="industrivarden",
        name="Industrivärden",
        symbols=("INDU-A.ST", "INDU-C.ST"),
        nav_per_share=532.0,
        nav_date="2026-08-31",
        nav_source="Industrivärden: substansvärde per aktie 31 augusti 2026",
        holdings_date="2026-06-30",
        holdings_source="Industrivärden: portfölj 30 juni 2026",
        holdings=(
            Holding("VOLV-B.ST", "Volvo", 0.29),
            Holding("SAND.ST", "Sandvik", 0.33),
            Holding("SHB-A.ST", "Handelsbanken", 0.15),
            Holding("ESSITY-B.ST", "Essity", 0.10),
            Holding("SCA-B.ST", "SCA", 0.04),
            Holding("SKA-B.ST", "Skanska", 0.04),
            Holding("ERIC-B.ST", "Ericsson", 0.04),
            Holding("ALLEI.ST", "Alleima", 0.02),
        ),
        listed_portfolio_share=1.0,
    ),
    InvestmentCompanyProfile(
        key="investor",
        name="Investor",
        symbols=("INVE-A.ST", "INVE-B.ST"),
        # 1,215bn adjusted NAV / 3,068,700,120 shares (30 Jun 2026) ≈ 395.93 SEK/share.
        nav_per_share=395.93,
        nav_date="2026-06-30",
        nav_source="Investor: justerat substansvärde och antal aktier 30 juni 2026",
        holdings_date="2026-06-30",
        holdings_source="Investor: noterade innehav 30 juni 2026",
        holdings=(
            Holding("ABB.ST", "ABB", 0.23),
            Holding("AZN.ST", "AstraZeneca", 0.08),
            Holding("ATCO-A.ST", "Atlas Copco", 0.13),
            Holding("EPI-A.ST", "Epiroc", 0.04),
            Holding("ERIC-B.ST", "Ericsson", 0.03),
            Holding("NDAQ", "Nasdaq", 0.04),
            Holding("SAAB-B.ST", "Saab", 0.07),
            Holding("SEB-A.ST", "SEB", 0.07),
            Holding("SOBI.ST", "Sobi", 0.05),
            Holding("WRT1V.HE", "Wärtsilä", 0.03),
        ),
        listed_portfolio_share=0.76,
        note="Investor har även Patricia Industries och EQT-investeringar; direktkorgen täcker därför inte hela substansvärdet.",
    ),
)

# Broader identification list. These are recognized as investment/holding companies,
# but Borsify deliberately avoids inventing NAV/portfolio data where no curated source
# exists in this release.
KNOWN_SYMBOLS = {
    "LATO-B.ST": "Latour",
    "LUND-B.ST": "Lundbergföretagen",
    "BURE.ST": "Bure Equity",
    "CREAD-A.ST": "Creades",
    "SVOL-B.ST": "Svolder",
    "KINV-B.ST": "Kinnevik",
    "TRACT-B.ST": "Traction",
    "VNV.ST": "VNV Global",
    "VEFAB.ST": "VEF",
    "FLAT-B.ST": "Flat Capital",
}


def _num(value: Any) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else np.nan
    except Exception:
        return np.nan


def _profile_for_symbol(symbol: str) -> InvestmentCompanyProfile | None:
    symbol = str(symbol or "").upper().strip()
    for profile in PROFILES:
        if symbol in profile.symbols:
            return profile
    return None


def identify_investment_company(symbol: str, name: str = "", industry: str = "") -> tuple[bool, str, InvestmentCompanyProfile | None]:
    symbol = str(symbol or "").upper().strip()
    profile = _profile_for_symbol(symbol)
    if profile:
        return True, profile.name, profile
    if symbol in KNOWN_SYMBOLS:
        return True, KNOWN_SYMBOLS[symbol], None

    text = f"{name} {industry}".lower()
    hints = ("investmentbolag", "investment company", "holding company")
    if any(h in text for h in hints):
        return True, str(name or symbol), None
    return False, "", None


def _age_days(as_of: str | None, today: date | None = None) -> int | None:
    if not as_of:
        return None
    try:
        return ((today or date.today()) - date.fromisoformat(as_of)).days
    except Exception:
        return None


def _freshness_label(age_days: int | None) -> str:
    if age_days is None:
        return "okänd ålder"
    if age_days <= 45:
        return "färsk"
    if age_days <= 100:
        return "något gammal"
    return "gammal"


def _price_sek(row: pd.Series) -> float:
    price_sek = _num(row.get("Pris SEK"))
    if np.isfinite(price_sek) and price_sek > 0:
        return price_sek
    currency = str(row.get("Valuta") or "").upper().strip()
    price = _num(row.get("Pris"))
    if currency == "SEK" and np.isfinite(price) and price > 0:
        return price
    return np.nan


def _holding_lookup(df: pd.DataFrame) -> dict[str, pd.Series]:
    if df is None or df.empty or "Ticker" not in df.columns:
        return {}
    return {str(row.get("Ticker") or "").upper(): row for _, row in df.iterrows()}


def _underlying_summary(profile: InvestmentCompanyProfile, lookup: dict[str, pd.Series]) -> tuple[float, float, list[str]]:
    weighted = 0.0
    covered = 0.0
    strongest: list[tuple[float, str]] = []
    for holding in profile.holdings:
        row = lookup.get(holding.ticker.upper())
        if row is None:
            continue
        score = _num(row.get("Borsify Score"))
        if not np.isfinite(score):
            continue
        weighted += holding.weight * score
        covered += holding.weight
        strongest.append((score, holding.name))
    score = weighted / covered if covered > 0 else np.nan
    strongest.sort(reverse=True)
    return score, covered, [name for _, name in strongest[:3]]


def evaluate_investment_company(row: pd.Series, universe: pd.DataFrame | None = None, today: date | None = None) -> dict[str, Any]:
    symbol = str(row.get("Ticker") or "").upper().strip()
    is_ic, display_name, profile = identify_investment_company(
        symbol, str(row.get("Namn") or ""), str(row.get("Industri") or row.get("Sektor") or "")
    )
    if not is_ic:
        return {
            "Investmentbolag": False,
            "Investmentbolag namn": "",
            "Investmentbolag status": "",
            "Investmentbolag enkel förklaring": "",
            "Investmentbolag direktval": "",
            "Investmentbolag substansrabatt": np.nan,
            "Investmentbolag substansdatum": "",
            "Investmentbolag innehavstäckning": np.nan,
            "Investmentbolag innehavsbetyg": np.nan,
            "Investmentbolag rankningstak": 100.0,
            "Investmentbolag datakvalitet": "ej relevant",
        }

    if profile is None:
        return {
            "Investmentbolag": True,
            "Investmentbolag namn": display_name,
            "Investmentbolag status": "Behöver substanskontroll",
            "Investmentbolag enkel förklaring": "Det här är ett investmentbolag. Borsify saknar ännu tillräckligt färsk substans- och innehavsdata för att behandla det som ett vanligt bolag.",
            "Investmentbolag direktval": "Otillräcklig data",
            "Investmentbolag substansrabatt": np.nan,
            "Investmentbolag substansdatum": "",
            "Investmentbolag innehavstäckning": np.nan,
            "Investmentbolag innehavsbetyg": np.nan,
            "Investmentbolag rankningstak": 70.0,
            "Investmentbolag datakvalitet": "begränsad",
        }

    price = _price_sek(row)
    nav = _num(profile.nav_per_share)
    discount = 1.0 - price / nav if np.isfinite(price) and price > 0 and np.isfinite(nav) and nav > 0 else np.nan
    nav_age = _age_days(profile.nav_date, today)
    nav_freshness = _freshness_label(nav_age)

    lookup = _holding_lookup(universe if universe is not None else pd.DataFrame())
    underlying_score, coverage, strongest = _underlying_summary(profile, lookup)
    effective_coverage = min(coverage, profile.listed_portfolio_share)
    listed_complete = profile.listed_portfolio_share >= 0.95

    rank_cap = 100.0
    data_quality = "god"
    if nav_age is None or nav_age > 100:
        data_quality = "begränsad"
        rank_cap = min(rank_cap, 70.0)
    elif nav_age > 45:
        data_quality = "medel"
        rank_cap = min(rank_cap, 74.0)
    if effective_coverage < 0.50:
        data_quality = "begränsad" if data_quality != "begränsad" else data_quality
        rank_cap = min(rank_cap, 72.0)
    if not listed_complete:
        # Never claim that buying the listed holdings replicates Investor as a whole.
        rank_cap = min(rank_cap, 76.0)

    if np.isfinite(discount):
        discount_text = f"{abs(discount):.0%} {'rabatt' if discount >= 0 else 'premie'} mot daterat substansvärde"
    else:
        discount_text = "substansrabatten kan inte räknas"

    strongest_text = ", ".join(strongest) if strongest else "för få innehav i dagens scan"
    if not listed_complete:
        direct_choice = "Ingen rättvis direktjämförelse"
        status = "Delvis look-through"
        explanation = (
            f"{profile.name} har både noterade och onoterade delar. {discount_text}. "
            f"Borsify kan läsa delar av de noterade innehaven ({effective_coverage:.0%} täckning), men ett direktköp av dem ersätter inte hela investmentbolaget."
        )
    elif np.isfinite(discount) and nav_age is not None and nav_age <= 45 and effective_coverage >= 0.60:
        if discount >= 0.07 and np.isfinite(underlying_score) and underlying_score >= 65:
            direct_choice = "Investmentbolaget ser bättre ut"
            status = "Attraktiv paket-rabatt"
            explanation = (
                f"Aktien handlas cirka {discount:.0%} under daterat substansvärde och de analyserade innehaven är sammantaget starka. "
                "Du får alltså en korg av bolag till rabatt, enligt den data Borsify har just nu."
            )
        elif discount <= -0.03:
            direct_choice = "Innehaven direkt kan vara bättre"
            status = "Premie mot substans"
            explanation = (
                f"Aktien handlas cirka {abs(discount):.0%} över daterat substansvärde. "
                "Då finns ingen tydlig prisfördel i att köpa paketet; jämför de största innehaven direkt."
            )
            rank_cap = min(rank_cap, 68.0)
        else:
            direct_choice = "Ingen tydlig vinnare"
            status = "Ingen tydlig paket-rabatt"
            explanation = (
                f"{discount_text.capitalize()}. Borsify ser därför ingen självklar prisfördel mellan investmentbolaget och innehaven direkt."
            )
            rank_cap = min(rank_cap, 74.0)
    else:
        direct_choice = "Otillräcklig data"
        status = "Behöver färskare jämförelse"
        explanation = (
            f"{discount_text.capitalize()}, men underlaget är {nav_freshness} eller innehavstäckningen är för låg. "
            "Borsify låter därför inte ett vanligt aktiescore ensamt göra detta till ett toppcase."
        )

    return {
        "Investmentbolag": True,
        "Investmentbolag namn": profile.name,
        "Investmentbolag status": status,
        "Investmentbolag enkel förklaring": explanation,
        "Investmentbolag direktval": direct_choice,
        "Investmentbolag substansrabatt": discount,
        "Investmentbolag substansdatum": profile.nav_date or "",
        "Investmentbolag innehavstäckning": effective_coverage,
        "Investmentbolag innehavsbetyg": underlying_score,
        "Investmentbolag rankningstak": rank_cap,
        "Investmentbolag datakvalitet": data_quality,
        "Investmentbolag starkaste innehav": strongest_text,
        "Investmentbolag källnot": "; ".join(x for x in [profile.nav_source, profile.holdings_source, profile.note] if x),
    }


def add_investment_company_context(df: pd.DataFrame, today: date | None = None) -> pd.DataFrame:
    """Attach look-through context without creating another score.

    The current scored universe is used only to summarize mapped underlying holdings.
    Missing values remain missing. The function may cap *daily relevance* later, but it
    does not mutate Borsify Score itself.
    """
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    contexts = [evaluate_investment_company(row, out, today=today) for _, row in out.iterrows()]
    ctx = pd.DataFrame(contexts, index=out.index)
    for col in ctx.columns:
        out[col] = ctx[col]
    return out
