import json
import pandas as pd

from interaction_diagnostics import (
    prepare_interaction_sample,
    interaction_archetype_table,
    interaction_archetype_summary,
)


def _data():
    recs = []
    outs = []
    base = pd.Timestamp('2023-01-01')
    # 36 independent observations: enough both-leg and exactly-one controls.
    for i in range(36):
        both = i < 10
        one_a = 10 <= i < 20
        one_b = 20 <= i < 30
        snap = {
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
        ret = 0.16 if both else ((0.03 if i % 2 == 0 else -0.02) if (one_a or one_b) else 0.01)
        outs.append({'record_id': f'r{i}', 'horizon': '1m', 'return_pct': ret})
    return pd.DataFrame(recs), pd.DataFrame(outs)


def test_interaction_detects_momentum_plus_relative_strength():
    recs, outs = _data()
    table = interaction_archetype_table(recs, outs, '1m', 'short')
    row = table[table['Arketyp'].eq('Längre momentum + relativ styrka')].iloc[0]
    assert row['Status'] == 'Stark möjlig interaction'
    assert row['Båda signaler'] == 10
    assert row['En signal'] == 20


def test_interaction_uses_independent_point_in_time_sample():
    recs, outs = _data()
    sample = prepare_interaction_sample(recs, outs, '1m', 'short')
    assert len(sample) == 36
    summary = interaction_archetype_summary(interaction_archetype_table(recs, outs, '1m', 'short'), len(sample))
    assert summary['status'] == 'Interactions hittade'


def test_interaction_requires_enough_history():
    recs, outs = _data()
    recs = recs.iloc[:12]
    outs = outs.iloc[:12]
    table = interaction_archetype_table(recs, outs, '1m', 'short')
    assert table.empty
    summary = interaction_archetype_summary(table, 12)
    assert summary['status'] == 'Vänta'


def test_v313_ui_version_and_governance_present():
    app = open('app.py', encoding='utf-8').read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert 'Case Archetypes · fungerar vissa signaler bättre tillsammans?' in app
    assert 'interaction_archetype_table' in app
    assert 'ändrar aldrig vikter eller regler automatiskt' in app
