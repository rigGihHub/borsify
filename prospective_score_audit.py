"""Frozen, chronological cohorts; no fit on outcomes and no historical reconstruction."""
import json
import numpy as np
import pandas as pd
from independent_case_validation import independent_case_sample

LABELS = {'medium': 'Köp nu, sälj snart', 'year': 'Upp till ett år', 'lifetime': 'Mycket lång sikt'}


def prospective_score_audit(recommendations, outcomes, model_version, horizon, cost_bps=20, as_of=None):
    columns = ['Tidshorisont', 'Startkvartal', 'Jämförelseindex', 'Case', 'Netto mot index %', 'Höga betyg netto %', 'Övriga betyg netto %', 'Rangkorrelation', 'Status']
    if not np.isfinite(cost_bps) or not 0 <= cost_bps <= 1000:
        raise ValueError('Cost must be 0–1000 bps per side')
    required = {'record_id', 'model_version', 'snapshot_json', 'symbol', 'captured_date', 'final_score'}
    if recommendations.empty or outcomes.empty or not required.issubset(recommendations.columns):
        return pd.DataFrame(columns=columns)
    if not {'record_id', 'horizon', 'evaluated_date', 'return_pct', 'benchmark_return_pct', 'benchmark_symbol'}.issubset(outcomes.columns):
        return pd.DataFrame(columns=columns)
    rec = recommendations[recommendations.model_version.astype(str).eq(str(model_version))].copy()
    def snapshot(raw):
        try:
            value = json.loads(raw)
            return value if isinstance(value, dict) else {}
        except (TypeError, ValueError):
            return {}
    snap = rec.snapshot_json.map(snapshot)
    rec['visible_horizon'] = snap.map(lambda s: s.get('Visad horisont'))
    valid = snap.map(lambda s: s.get('PIT Outcome Basis') == 'next_session_close_total_return_v1' and s.get('PIT Complete') is True)
    rec = rec[valid & rec.visible_horizon.isin(LABELS)].copy()
    out = outcomes[outcomes.horizon.astype(str).eq(horizon)].copy()
    work = rec.merge(out.drop(columns=['symbol'], errors='ignore'), on='record_id', suffixes=('', '_out'))
    now = pd.to_datetime(as_of or pd.Timestamp.now(tz='UTC'), utc=True)
    work['_start'] = pd.to_datetime(work.captured_date, errors='coerce', utc=True)
    work['_end'] = pd.to_datetime(work.evaluated_date, errors='coerce', utc=True)
    for c in ['return_pct', 'benchmark_return_pct', 'final_score']:
        work[c] = pd.to_numeric(work[c], errors='coerce').replace([np.inf, -np.inf], np.nan)
    work = work.dropna(subset=['_start', '_end', 'return_pct', 'benchmark_return_pct', 'final_score'])
    work = work[(work._end > work._start) & (work._end <= now) & work.final_score.between(0, 100)
                & work.return_pct.ge(-1) & work.benchmark_return_pct.ge(-1)
                & work.benchmark_symbol.fillna('').astype(str).str.strip().ne('')]
    # Include buy and sell commission/spread/slippage as an explicit scenario.
    cost = cost_bps / 10000
    work['_net'] = (1 + work.return_pct) * (1 - cost) / (1 + cost) - 1 - work.benchmark_return_pct
    rows = []
    for (visible, benchmark), group in work.groupby(['visible_horizon', 'benchmark_symbol']):
        group = independent_case_sample(group, horizon)
        group['_quarter'] = group._start.dt.tz_localize(None).dt.to_period('Q').astype(str)
        for quarter, cohort in group.groupby('_quarter'):
            high = cohort[cohort.final_score.ge(70)]
            low = cohort[cohort.final_score.lt(70)]
            sufficient = len(cohort) >= 24 and len(high) >= 6 and len(low) >= 6
            corr = cohort.final_score.rank().corr(cohort._net.rank()) if len(cohort) >= 4 and cohort.final_score.nunique() > 1 and cohort._net.nunique() > 1 else np.nan
            rows.append({'Tidshorisont': LABELS[visible], 'Startkvartal': quarter, 'Jämförelseindex': benchmark,
                         'Case': len(cohort), 'Netto mot index %': 100 * cohort._net.mean(),
                         'Höga betyg netto %': 100 * high._net.mean(), 'Övriga betyg netto %': 100 * low._net.mean(),
                         'Rangkorrelation': corr,
                         'Status': 'Mätbart – inte bevisad överavkastning' if sufficient else 'För lite underlag'})
    return pd.DataFrame(rows, columns=columns)
