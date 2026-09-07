import json
import pandas as pd

from regime_archetype_diagnostics import (
    regime_archetype_table,
    regime_archetype_consistency,
    regime_archetype_summary,
)


def _data():
    recs, outs = [], []
    base = pd.Timestamp('2021-01-01')
    # Two market regimes, 18 observations each. In STRONG the archetype helps;
    # in WEAK it hurts, creating a deliberately regime-dependent result.
    for rix, regime in enumerate(['STARK MARKNAD', 'SVAG MARKNAD']):
        for j in range(18):
            i = rix * 18 + j
            both = j < 6
            one_a = 6 <= j < 12
            one_b = 12 <= j < 18
            snap = {
                'Marknadsläge': regime,
                'Short 12–1 Momentum': 72 if (both or one_a) else 40,
                '12–1 momentum score': 72 if (both or one_a) else 40,
                'Short Relative Strength': 68 if (both or one_b) else 45,
                'Short Trend': 62,
                'Short Momentum': 60,
                'Short Catalyst': 45,
                'Short Revisions': 45,
                'Post-report stöd': False,
                'Post-report varning': False,
                'Idiosynkratisk volatilitet status': 'INGEN TYDLIG EXTRA RISK',
            }
            recs.append({
                'record_id': f'r{i}', 'symbol': f'S{i}',
                'captured_date': (base + pd.Timedelta(days=i*40)).date().isoformat(),
                'horizon_type': 'short', 'snapshot_json': json.dumps(snap), 'score': 70,
            })
            if regime == 'STARK MARKNAD':
                ret = 0.18 if both else (0.02 if j % 2 == 0 else -0.01)
            else:
                ret = -0.12 if both else 0.03
            outs.append({'record_id': f'r{i}', 'horizon': '1m', 'return_pct': ret})
    return pd.DataFrame(recs), pd.DataFrame(outs)


def test_regime_archetype_detects_opposite_behavior_between_regimes():
    recs, outs = _data()
    detail = regime_archetype_table(recs, outs, '1m', 'short')
    rows = detail[detail['Arketyp'].eq('Längre momentum + relativ styrka')]
    assert set(rows['Marknadsläge']) == {'STARK MARKNAD', 'SVAG MARKNAD'}
    assert 'Stark möjlig interaction' in set(rows['Status'])
    assert 'Motsäger hypotesen' in set(rows['Status'])


def test_regime_archetype_consistency_marks_regime_dependency():
    recs, outs = _data()
    detail = regime_archetype_table(recs, outs, '1m', 'short')
    summary_table = regime_archetype_consistency(detail)
    row = summary_table[summary_table['Arketyp'].eq('Längre momentum + relativ styrka')].iloc[0]
    assert row['Bedömning'] == 'Regimberoende'
    head = regime_archetype_summary(detail, summary_table)
    assert head['status'] == 'Regimskillnader hittade'


def test_regime_archetype_requires_frozen_market_regime():
    recs, outs = _data()
    recs['snapshot_json'] = recs['snapshot_json'].map(lambda x: json.dumps({k:v for k,v in json.loads(x).items() if k != 'Marknadsläge'}))
    detail = regime_archetype_table(recs, outs, '1m', 'short')
    assert detail.empty
    assert regime_archetype_summary(detail, pd.DataFrame())['status'] == 'Vänta'


def test_v314_ui_version_and_governance_present():
    app = open('app.py', encoding='utf-8').read()
    assert 'APP_VERSION = "3.26.0"' in app
    assert 'Regime-aware Archetypes · fungerar samma kombination i olika börsklimat?' in app
    assert 'regime_archetype_table' in app
    assert 'inga regler ändras automatiskt' in app
