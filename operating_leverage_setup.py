from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


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


def assess_operating_leverage_setup(row: pd.Series | dict[str, Any], horizon: str) -> dict[str, Any]:
    """Detect revenue acceleration before full margin/earnings follow-through.

    The signal does not infer a stable cost base when direct cost history is unavailable.
    It only identifies a setup where revenue accelerates, margins are not deteriorating,
    and earnings/FCF have not already fully caught up. This is a long-horizon ranking
    context layer after buy gates, not a standalone buy signal or earnings forecast.
    """
    r = row
    rev_yoy = _num(r.get('Omsättning YoY senaste kvartal'))
    rev_acc = _num(r.get('Omsättning acceleration'))
    margin_yoy = _num(r.get('Marginal YoY förändring'))
    margin_prev = _num(r.get('Marginal YoY föregående kvartal'))
    earnings_yoy = _num(r.get('Vinst YoY senaste kvartal'))
    earnings_prev = _num(r.get('Vinst YoY föregående kvartal'))
    fcf_yoy = _num(r.get('FCF YoY senaste kvartal'))
    fcf_prev = _num(r.get('FCF YoY föregående kvartal'))
    quality = _num(r.get('Kvalitet'))
    risk = _num(r.get('Risk'))
    invest = _num(r.get('INVEST Score'))
    valuation = _num(r.get('Värdering'))
    m1 = _num(r.get('1 mån'))
    m3 = _num(r.get('3 mån'))
    dist = _num(r.get('Avstånd SMA200'))
    crowded = _yes(r.get('Crowded varning')) or _yes(r.get('Crowded stark varning'))

    supports: list[str] = []
    warnings: list[str] = []

    revenue_accelerating = np.isfinite(rev_acc) and rev_acc >= .03 and np.isfinite(rev_yoy) and rev_yoy >= .03
    if revenue_accelerating:
        supports.append(f'omsättningstillväxten accelererar ({rev_acc:+.1%})')

    margin_not_worsening = False
    if np.isfinite(margin_yoy):
        if margin_yoy >= -.005:
            margin_not_worsening = True
            supports.append('marginalen försämras inte trots högre tillväxt')
        if np.isfinite(margin_prev) and margin_yoy - margin_prev >= .0075:
            supports.append('marginalutvecklingen förbättras sekventiellt')
    elif np.isfinite(margin_prev) and margin_prev >= 0:
        margin_not_worsening = True

    # We want earnings power that has room to catch up. If earnings already vastly
    # outpace revenue, this is not an "before earnings" setup anymore.
    earnings_lag = False
    if np.isfinite(earnings_yoy) and np.isfinite(rev_yoy):
        earnings_lag = earnings_yoy <= rev_yoy + .05
        if earnings_lag:
            supports.append('vinsttillväxten har ännu inte sprungit långt före omsättningen')
    elif not np.isfinite(earnings_yoy):
        warnings.append('vinsttillväxt saknas – hävstången är mindre verifierad')

    fcf_lag = False
    if np.isfinite(fcf_yoy) and np.isfinite(rev_yoy):
        fcf_lag = fcf_yoy <= rev_yoy + .10
        if fcf_lag:
            supports.append('kassaflödet har ännu inte fullt hunnit ikapp omsättningstillväxten')

    if np.isfinite(quality) and quality >= 70:
        supports.append('bolagskvaliteten är hög')
    if np.isfinite(risk) and risk >= 60:
        supports.append('riskprofilen är robust')
    if np.isfinite(invest) and invest >= 65:
        supports.append('INVEST-bedömningen är stark')

    # Explicit warnings / anti-false-positive gates.
    if np.isfinite(margin_yoy) and margin_yoy <= -.02:
        warnings.append('marginalen försämras tydligt')
    if np.isfinite(earnings_yoy) and earnings_yoy <= -.20:
        warnings.append('vinsten försämras kraftigt')
    if np.isfinite(fcf_yoy) and fcf_yoy <= -.25:
        warnings.append('kassaflödet försämras kraftigt')
    if np.isfinite(rev_acc) and rev_acc <= -.03:
        warnings.append('omsättningstillväxten bromsar')
    if crowded:
        warnings.append('förväntningsbilden är redan trång')
    if np.isfinite(m1) and m1 >= .22:
        warnings.append('kursen har redan sprungit senaste månaden')
    if np.isfinite(m3) and m3 >= .40:
        warnings.append('kursen har redan sprungit på tre månader')
    if np.isfinite(dist) and dist >= .20:
        warnings.append('kursen ligger långt över lång trend')
    if np.isfinite(valuation) and valuation < 40:
        warnings.append('värderingen är ansträngd')

    long_horizon = horizon in {'year','long','lifetime'}
    severe_break = any(x in warnings for x in [
        'marginalen försämras tydligt','vinsten försämras kraftigt',
        'kassaflödet försämras kraftigt','omsättningstillväxten bromsar'
    ])
    quality_ok = (not np.isfinite(quality) or quality >= 60) and (not np.isfinite(risk) or risk >= 50)
    price_not_chasing = not any('kursen har redan sprungit' in x or 'långt över lång trend' in x for x in warnings)

    core = revenue_accelerating and margin_not_worsening and quality_ok
    lag_support = earnings_lag or fcf_lag

    if not long_horizon:
        tier = 0; label = '— Operating-leverage-signalen används bara långsiktigt'
    elif severe_break:
        tier = -1; label = '⚠️ Ingen operating leverage – försämring dominerar'
    elif not core:
        tier = 0; label = '— För lite stöd för operating-leverage-setup'
    elif lag_support and price_not_chasing and not crowded and len(supports) >= 5:
        tier = 3; label = '💎 Operating leverage before earnings · stark tidig kandidat'
    elif lag_support and price_not_chasing and not crowded:
        tier = 2; label = '🟢 Omsättningen accelererar före full vinsthävstång'
    else:
        tier = 1; label = '🟡 Operating-leverage-setup finns – men affären är inte tydligt tidig'

    rank = float(max(tier, 0) * 100 + min(len(supports), 7) * 6 - min(len(warnings), 5) * 8)
    if tier < 0:
        rank = -100.0

    why = '; '.join(supports[:5]) if supports else 'ingen verifierad operating-leverage-setup'
    why += '. Borsify verifierar inte en stabil kostnadsbas utan direkt kostnadshistorik; signalen bygger på omsättningsacceleration och observerad marginalrespons.'
    if warnings:
        why += ' Motargument: ' + '; '.join(warnings[:3])

    return {
        'Operating leverage': label,
        'Operating leverage nivå': tier,
        'Operating leverage rangvärde': rank,
        'Operating leverage stöd': '; '.join(supports[:7]),
        'Operating leverage varningar': '; '.join(warnings[:6]),
        'Operating leverage förklaring': why,
        'Operating leverage cost base verified': False,
    }


def add_operating_leverage_setup(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    extra = pd.DataFrame([assess_operating_leverage_setup(r, horizon) for _, r in out.iterrows()], index=out.index)
    overlap = [c for c in extra.columns if c in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    return out.join(extra)
