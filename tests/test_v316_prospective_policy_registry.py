import json
import pandas as pd

from prospective_policy_registry import (
    STATUS_CANDIDATE,
    STATUS_REGISTERED,
    default_prospective_policies,
    definition_fingerprint,
    eligible_prospective_recommendations,
    prospective_policy_results,
    prospective_policy_governance,
    prospective_policy_summary,
    registry_table,
)


def _prospective_data():
    recs, outs = [], []
    base = pd.Timestamp('2026-09-07')
    # 40 independent post-registration cases. 20 satisfy the first policy requirement.
    for i in range(40):
        requirement = i < 20
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
        recs.append({
            'record_id': f'r{i}', 'symbol': f'S{i}',
            'captured_date': (base + pd.Timedelta(days=i*40)).date().isoformat(),
            'model_version': '3.16.0', 'horizon_type': 'short',
            'snapshot_json': json.dumps(snap), 'score': 70,
        })
        for horizon in ('1m', '3m'):
            outs.append({'record_id': f'r{i}', 'horizon': horizon, 'return_pct': 0.16 if requirement else -0.04})
    return pd.DataFrame(recs), pd.DataFrame(outs)


def test_registry_has_stable_ids_and_fingerprints():
    specs = default_prospective_policies()
    assert len(specs) == 3
    assert len({p.policy_id for p in specs}) == 3
    assert all(len(definition_fingerprint(p)) == 16 for p in specs)
    table = registry_table(specs)
    assert set(['Policy ID', 'Target', 'Extra krav', 'Definition']).issubset(table.columns)


def test_pre_registration_history_is_excluded():
    policy = default_prospective_policies()[0]
    recs = pd.DataFrame([
        {'captured_date': '2026-09-06', 'model_version': '3.15.0'},
        {'captured_date': '2026-09-07', 'model_version': '3.16.0'},
    ])
    eligible = eligible_prospective_recommendations(recs, policy)
    assert len(eligible) == 1
    assert eligible.iloc[0]['model_version'] == '3.16.0'


def test_prospective_policy_can_only_open_manual_review_after_multiple_horizons():
    recs, outs = _prospective_data()
    detail = prospective_policy_results(recs, outs, ['1m', '3m'])
    governance = prospective_policy_governance(detail)
    row = governance[governance['Policyhypotes'].str.startswith('Momentum i svag marknad')].iloc[0]
    assert row['Status'] == STATUS_CANDIDATE
    assert row['Stödjande horisonter'] == 2
    assert row['Största target-sample'] >= 32
    assert prospective_policy_summary(governance)['status'] == STATUS_CANDIDATE


def test_empty_history_remains_registered_not_backfilled():
    governance = prospective_policy_governance(pd.DataFrame())
    assert (governance['Status'] == STATUS_REGISTERED).all()


def test_v316_ui_version_and_no_auto_policy_activation():
    app = open('app.py', encoding='utf-8').read()
    assert 'APP_VERSION = "3.26.0"' in app
    assert 'Prospective Policy Registry' in app
    assert 'prospective_policy_results' in app
    assert 'Ingen policy aktiveras här' in app
