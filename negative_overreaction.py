from __future__ import annotations

import math
from typing import Any
import numpy as np
import pandas as pd

from decision_axes import assess_company_quality


def _num(v: Any) -> float:
    try:
        x=float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _yes(v: Any) -> bool:
    if isinstance(v,bool):
        return v
    return str(v or '').strip().lower() in {'1','true','ja','yes'}


def _text(v: Any) -> str:
    return str(v or '').strip().casefold()


def assess_negative_overreaction(row: pd.Series | dict[str,Any]) -> dict[str,Any]:
    """Find quality-on-sale cases without rewarding falling knives.

    A price drop is only interesting when independent fundamental/expectation evidence
    does *not* validate the drop. This layer is categorical and conservative; it is a
    ranking context/tie-break, never a standalone buy gate.
    """
    r=row
    company=assess_company_quality(r)
    company_level=str(company.get('Bolagsbedömning nivå','')).lower()
    quality=_num(r.get('Kvalitet')); risk=_num(r.get('Risk')); valuation=_num(r.get('Värdering'))
    daily=_num(r.get('Dagsförändring')); m1=_num(r.get('1 mån')); m3=_num(r.get('3 mån'))
    draw=_num(r.get('52v från topp'))
    reaction=_num(r.get('Report Delta kursreaktion'))
    report_pos=_num(r.get('Report Delta positiva')); report_neg=_num(r.get('Report Delta negativa'))
    report_status=_text(r.get('Report Delta status'))
    consensus_neg=_yes(r.get('Konsensusminne negativ'))
    consensus_pos=_yes(r.get('Konsensusminne positiv'))
    change_warning=_yes(r.get('Förändringsbekräftelse varning'))
    change_candidate=_yes(r.get('Förändringsbekräftelse kandidat'))
    negative_families=[x.strip() for x in str(r.get('Förändringsbekräftelse negativa familjer') or '').split(',') if x.strip()]
    positive_families=[x.strip() for x in str(r.get('Förändringsbekräftelse positiva familjer') or '').split(',') if x.strip()]
    upside=_num(r.get('Riktkurs potential'))

    shock=False; shock_parts=[]
    if np.isfinite(reaction) and reaction <= -.05:
        shock=True; shock_parts.append(f'rapportreaktion {reaction:.0%}')
    if np.isfinite(daily) and daily <= -.06:
        shock=True; shock_parts.append(f'dagsfall {daily:.0%}')
    if np.isfinite(m1) and m1 <= -.12:
        shock=True; shock_parts.append(f'1 månad {m1:.0%}')
    elif np.isfinite(m3) and m3 <= -.20:
        shock=True; shock_parts.append(f'3 månader {m3:.0%}')
    if np.isfinite(draw) and draw <= -.20:
        shock_parts.append(f'{draw:.0%} från 52-veckorstopp')

    fundamental_break = (
        company_level == 'red'
        or (np.isfinite(quality) and quality < 55)
        or (np.isfinite(risk) and risk < 45)
        or 'bred negativ rapportförändring' in report_status
        or (np.isfinite(report_neg) and report_neg >= 2 and (not np.isfinite(report_pos) or report_neg >= report_pos))
        or consensus_neg
        or change_warning
        or len(negative_families) >= 2
    )

    supports=[]; cautions=[]
    if company_level == 'green': supports.append('bolagskvaliteten är fortfarande stark')
    if np.isfinite(report_pos) and report_pos >= 3 and np.isfinite(report_neg) and report_neg <= 1:
        supports.append('rapportförändringen är fortfarande brett positiv')
    elif 'stark rapport men marknaden säger emot' in report_status:
        supports.append('rapporten var stark trots negativ kursreaktion')
    if consensus_pos and not consensus_neg: supports.append('analytikerkonsensus har inte vänt ned')
    if change_candidate and not negative_families: supports.append('flera oberoende förändringsfamiljer är fortsatt positiva')
    if np.isfinite(upside) and upside >= .15: supports.append('observerad riktkurspotential finns kvar efter fallet')
    if np.isfinite(valuation) and valuation >= 65: supports.append('värderingen har blivit attraktiv i Borsifys modell')

    if fundamental_break:
        cautions.append('fundamenta eller förväntningsbild bekräftar delar av kursfallet')
    if consensus_neg: cautions.append('konsensusminnet är negativt')
    if len(negative_families): cautions.append('negativa förändringsfamiljer finns')
    if np.isfinite(report_neg) and report_neg >= 2: cautions.append('rapporten innehåller flera negativa förändringar')

    if not shock:
        tier=0; label='— Ingen tydlig negativ överreaktion'
    elif fundamental_break:
        tier=-1; label='⚠️ Möjlig fallande kniv'
    else:
        intact=sum([
            company_level=='green',
            np.isfinite(report_pos) and report_pos>=3 and (not np.isfinite(report_neg) or report_neg<=1),
            consensus_pos and not consensus_neg,
            change_candidate and not negative_families,
            np.isfinite(upside) and upside>=.15,
            np.isfinite(valuation) and valuation>=65,
        ])
        if intact >= 4 and len(supports) >= 3:
            tier=3; label='💎 Negativ överreaktion · stark fyndkandidat'
        elif intact >= 2 and len(supports) >= 2:
            tier=2; label='🟢 Möjlig negativ överreaktion'
        else:
            tier=1; label='🟡 Kursfall utan tydligt fyndbevis'

    rank_value=float(max(tier,0)*100)
    rank_value += min(len(supports),5)*5
    if tier < 0: rank_value=-100.0

    why=', '.join(shock_parts[:3]) if shock_parts else 'ingen tydlig prisstöt'
    if supports: why += '. Talar för överreaktion: ' + '; '.join(supports[:3])
    if cautions: why += '. Varning: ' + '; '.join(cautions[:2])

    return {
        'Negativ överreaktion': label,
        'Negativ överreaktion nivå': tier,
        'Negativ överreaktion rangvärde': rank_value,
        'Negativ överreaktion prisstöt': '; '.join(shock_parts),
        'Negativ överreaktion stöd': '; '.join(supports[:5]),
        'Negativ överreaktion varningar': '; '.join(cautions[:4]),
        'Negativ överreaktion förklaring': why,
        'Fallande kniv varning': bool(shock and fundamental_break),
    }


def add_negative_overreaction(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    rows=[assess_negative_overreaction(r) for _,r in out.iterrows()]
    extra=pd.DataFrame(rows,index=out.index)
    overlap=[c for c in extra.columns if c in out.columns]
    if overlap: out=out.drop(columns=overlap)
    return out.join(extra)
