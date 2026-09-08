import json
import pandas as pd

from regime_selection_policy import regime_selection_policy_table, regime_selection_policy_summary


def _data():
    recs, outs = [], []
    base = pd.Timestamp('2021-01-01')
    for i in range(24):
        requirement = i < 12
        snap = {
            'Marknadsläge': 'SVAG',
            'Short Momentum': 72,
            'Short Catalyst': 70 if requirement else 40,
            'Short Revisions': 45,
            'Short Trend': 65,
            'Short Relative Strength': 62,
            'Idiosynkratisk volatilitet status': 'INGEN TYDLIG EXTRA RISK',
            'Evidence Family Support Count': 3,
        }
        recs.append({'record_id': f'r{i}', 'symbol': f'S{i}', 'captured_date': (base + pd.Timedelta(days=i*40)).date().isoformat(), 'horizon_type': 'short', 'snapshot_json': json.dumps(snap), 'score': 70})
        outs.append({'record_id': f'r{i}', 'horizon': '1m', 'return_pct': 0.15 if requirement else -0.03})
    return pd.DataFrame(recs), pd.DataFrame(outs)


def test_policy_detects_better_target_cases_with_extra_requirement():
    recs, outs = _data()
    table = regime_selection_policy_table(recs, outs)
    row = table[table['Policyhypotes'].str.startswith('Momentum i svag marknad')].iloc[0]
    assert row['Status'] == 'Starkt stöd för högre krav'
    assert row['Krav uppfyllt'] == 12
    assert row['Krav ej uppfyllt'] == 12
    assert regime_selection_policy_summary(table)['status'] == 'Kravhypoteser får stöd'


def test_policy_requires_weak_market_point_in_time_data():
    recs, outs = _data()
    recs['snapshot_json'] = recs['snapshot_json'].map(lambda x: json.dumps({**json.loads(x), 'Marknadsläge': 'STARK'}))
    table = regime_selection_policy_table(recs, outs)
    assert table.empty
    assert regime_selection_policy_summary(table)['status'] == 'Vänta'


def test_v315_ui_version_and_no_automatic_rule_change():
    app = open('app.py', encoding='utf-8').read()
    assert 'APP_VERSION = "3.38.0"' in app
    assert 'Regime-aware Selection Policy' in app
    assert 'regime_selection_policy_table' in app
    assert 'ändrar aldrig köpgränser eller regler automatiskt' in app
