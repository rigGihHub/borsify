from __future__ import annotations

import math
from typing import Any
import numpy as np
import pandas as pd

from decision_axes import assess_company_quality
from entry_timing import assess_entry_timing


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _yes(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v or '').strip().lower() in {'1','true','ja','yes'}


def assess_good_deal(row: pd.Series | dict[str, Any], horizon: str) -> dict[str, Any]:
    """Judge whether a *good company* also looks like a good deal now.

    This is intentionally categorical. It rewards independent evidence that value is
    still left on the table, and penalises crowding/chasing. It is used as a ranking
    tie-break, never as a standalone buy gate or return forecast.
    """
    r = row
    company = assess_company_quality(r)
    entry = assess_entry_timing(r, horizon)

    valuation = _num(r.get('Värdering'))
    quality = _num(r.get('Kvalitet'))
    risk = _num(r.get('Risk'))
    upside = _num(r.get('Riktkurs potential'))
    change_n = _num(r.get('Förändringsbekräftelse positiva familjer antal'))
    expectation_gap = _yes(r.get('Expectation Gap kandidat'))
    expectation_gap_strong = _yes(r.get('Expectation Gap stark'))
    crowded = _yes(r.get('Crowded varning'))
    crowded_strong = _yes(r.get('Crowded stark varning'))
    entry_level = str(entry.get('Ingångsläge nivå', '')).lower()
    company_level = str(company.get('Bolagsbedömning nivå', '')).lower()

    supports: list[str] = []
    cautions: list[str] = []

    if expectation_gap:
        supports.append('förbättringen ser ut att ligga före förväntningarna')
    if expectation_gap_strong:
        supports.append('flera förändringssignaler bekräftar samma gap')
    if np.isfinite(upside) and upside >= .20:
        supports.append('minst cirka 20 % observerad riktkurspotential finns kvar')
    elif np.isfinite(upside) and upside >= .12:
        supports.append('tvåsiffrig observerad riktkurspotential finns kvar')
    if np.isfinite(valuation) and valuation >= 65:
        supports.append('värderingen är fortfarande attraktiv i Borsifys modell')
    if np.isfinite(change_n) and change_n >= 2:
        supports.append('minst två oberoende förändringsfamiljer förbättras')
    if np.isfinite(quality) and quality >= 70 and np.isfinite(risk) and risk >= 60:
        supports.append('bolagskvalitet och riskrobusthet är båda goda')

    if crowded_strong:
        cautions.append('förväntningsbilden är mycket trång')
    elif crowded:
        cautions.append('många verkar redan vara positiva')
    if entry_level == 'red':
        cautions.append('kursen är för utsträckt för att jaga')
    elif entry_level == 'orange':
        cautions.append('ingångsläget är ansträngt')
    if np.isfinite(upside) and upside <= .05:
        cautions.append('observerad riktkurspotential är liten')
    if np.isfinite(valuation) and valuation < 40:
        cautions.append('värderingen är ansträngd')
    if company_level == 'red':
        cautions.append('bolagskvaliteten är för svag')

    # Hard anti-false-positive rules first.
    if company_level == 'red' or entry_level == 'red' or crowded_strong:
        tier = 0
        label = '🔴 Ingen god affär nu'
    else:
        underappreciated = expectation_gap or (np.isfinite(upside) and upside >= .15) or (np.isfinite(valuation) and valuation >= 70)
        confirmed_change = (np.isfinite(change_n) and change_n >= 2) or expectation_gap
        good_company = company_level == 'green'
        clean_price = entry_level in {'green','yellow'}
        if good_company and clean_price and underappreciated and confirmed_change and not crowded and len(supports) >= 3:
            tier = 3
            label = '💎 Stark affärsasymmetri'
        elif good_company and entry_level != 'orange' and underappreciated and not crowded:
            tier = 2
            label = '🟢 God affär'
        elif company_level in {'green','yellow'} and not crowded_strong:
            tier = 1
            label = '🟡 Bra case – men inte tydligt fynd'
        else:
            tier = 0
            label = '🔴 Ingen god affär nu'

    # Numeric value is only an ordinal tie-break inside an already-approved universe.
    rank_value = float(tier * 100)
    rank_value += min(len(supports), 5) * 4
    rank_value -= min(len(cautions), 4) * 6

    why = '; '.join(supports[:3]) if supports else 'ingen tydlig kombination av värde, förändring och kvarvarande uppsida'
    if cautions:
        why += '. Motargument: ' + '; '.join(cautions[:2])

    return {
        'Affärsläge': label,
        'Affärsläge nivå': tier,
        'Affärsläge rangvärde': rank_value,
        'Affärsläge stöd': '; '.join(supports[:5]),
        'Affärsläge varningar': '; '.join(cautions[:4]),
        'Affärsläge förklaring': why,
    }


def add_good_deal(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    rows = [assess_good_deal(r, horizon) for _, r in out.iterrows()]
    extra = pd.DataFrame(rows, index=out.index)
    overlap = [c for c in extra.columns if c in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    return out.join(extra)
