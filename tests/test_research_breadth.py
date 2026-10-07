import json
from datetime import datetime, timezone, timedelta
import pandas as pd
from business_report_evidence import extract_business_evidence, usable_business_evidence
from research_rotation import rotation_candidates, save_research_batch, cached_research
from prospective_score_audit import prospective_score_audit


def test_primary_excerpts_keep_negative_and_source():
    fields = extract_business_evidence('Our investments in new products increased by 20%. Customer retention declined from 95% to 80% due to competition.', 'https://issuer.example/report', '2026-09-01', 'Q2 2026')
    row = {**fields, 'Rapport text verifierad': True, 'Rapport URL': 'https://issuer.example/report'}
    evidence = usable_business_evidence(row, '2026-10-07')
    assert any('declined' in x['text'] for x in evidence)
    assert 'Konkurrensfördel verifierad' not in fields
    assert not usable_business_evidence({**row, 'Rapport text verifierad': False}, '2026-10-07')
    assert not usable_business_evidence(row, '2028-10-07')
    assert not usable_business_evidence({**row, 'Rapport URL': 'https://other.example'}, '2026-10-07')


def test_rotation_survives_restart_and_failed_fetch(tmp_path):
    db = tmp_path / 'research.db'
    frame = pd.DataFrame({'Ticker': ['C', 'B', 'A', 'D'], 'Historik år': [4]*4, 'Rapport verksamhetsunderlag': [[{'text': 'example'}]]*4})
    first = rotation_candidates(frame, db, 2)
    assert first.Ticker.tolist() == ['A', 'B']
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    save_research_batch(first, db, now)
    assert rotation_candidates(frame, db, 2).Ticker.tolist() == ['C', 'D']
    save_research_batch(pd.DataFrame([{'Ticker': 'A', 'Deep Confidence': 0}]), db, now + timedelta(days=1))
    cached = cached_research(db, now + timedelta(days=2))
    assert set(cached.Ticker) == {'A', 'B'}
    assert cached.iloc[0]['Rapport verksamhetsunderlag'][0]['text'] == 'example'
    assert cached_research(db, now + timedelta(days=9)).empty


def audit_data():
    recs, outs = [], []
    for i in range(30):
        recs.append({'record_id': str(i), 'symbol': f'A{i}', 'captured_date': '2026-01-01', 'model_version': 'new', 'final_score': 80 if i < 15 else 60,
                     'snapshot_json': json.dumps({'Visad horisont': 'year', 'PIT Complete': True, 'PIT Outcome Basis': 'next_session_close_total_return_v1'})})
        outs.append({'record_id': str(i), 'horizon': '1m', 'evaluated_date': '2026-02-15', 'return_pct': .12 if i < 15 else .08, 'benchmark_return_pct': .10, 'benchmark_symbol': '^TEST'})
    return pd.DataFrame(recs), pd.DataFrame(outs)


def test_prospective_audit_cost_and_no_future_or_legacy():
    recs, outs = audit_data()
    free = prospective_score_audit(recs, outs, 'new', '1m', cost_bps=0, as_of='2026-10-07')
    costly = prospective_score_audit(recs, outs, 'new', '1m', cost_bps=20, as_of='2026-10-07')
    assert free.iloc[0]['Case'] == 30
    assert costly.iloc[0]['Netto mot index %'] < free.iloc[0]['Netto mot index %']
    assert prospective_score_audit(recs, outs, 'new', '1m', as_of='2026-01-02').empty
    assert prospective_score_audit(recs, outs, 'other', '1m').empty
    recs['snapshot_json'] = '{}'
    assert prospective_score_audit(recs, outs, 'new', '1m').empty


def test_visible_horizons_and_benchmarks_are_separate():
    recs, outs = audit_data()
    recs.loc[0, 'snapshot_json'] = recs.loc[0, 'snapshot_json'].replace('year', 'lifetime')
    outs.loc[1, 'benchmark_symbol'] = '^OTHER'
    result = prospective_score_audit(recs, outs, 'new', '1m', as_of='2026-10-07')
    assert len(result) == 3
    assert set(result['Tidshorisont']) == {'Mycket lång sikt', 'Upp till ett år'}


def test_missing_index_is_not_zero_return():
    recs, outs = audit_data()
    outs['benchmark_return_pct'] = None
    assert prospective_score_audit(recs, outs, 'new', '1m').empty
