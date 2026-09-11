import json
import pandas as pd

from failure_cohort_diagnostics import prepare_failure_cohort_sample, failure_cohort_table, failure_cohort_summary


def _data():
    recs=[]; outs=[]; base=pd.Timestamp('2024-01-01')
    for i in range(30):
        bad = i >= 18 and i % 2 == 0
        snap={
            'Short Alpha Score': 78 if bad else 68,
            'Short Trend': 35 if bad else 65,
            'Short Relative Strength': 40 if bad else 65,
            'Short Momentum': 70,
            'Short Participation': 65,
            'Short Revisions': 55,
            'Short Catalyst': 55,
            'Post-report stöd': False,
            'Idiosynkratisk volatilitet status': 'Normal',
        }
        recs.append({'record_id':f'r{i}','symbol':f'S{i}','captured_date':(base+pd.Timedelta(days=i*40)).date().isoformat(),'horizon_type':'short','snapshot_json':json.dumps(snap),'score':snap['Short Alpha Score']})
        ret = -0.12 if bad else 0.06
        outs.append({'record_id':f'r{i}','horizon':'1m','return_pct':ret})
    return pd.DataFrame(recs), pd.DataFrame(outs)


def test_failure_cohort_detects_high_score_weak_confirmation():
    recs, outs = _data()
    table = failure_cohort_table(recs, outs, '1m', 'short')
    assert 'Högt score + svag kursbekräftelse' in set(table['Cohort'])
    row=table[table['Cohort'].eq('Högt score + svag kursbekräftelse')].iloc[0]
    assert row['Status'] == 'Stark failure cohort'


def test_failure_cohort_uses_independent_sample_and_summary():
    recs, outs = _data()
    sample=prepare_failure_cohort_sample(recs, outs, '1m', 'short')
    assert len(sample) >= 24
    summary=failure_cohort_summary(failure_cohort_table(recs, outs, '1m', 'short'), len(sample))
    assert summary['status'] == 'Failure cohorts hittade'


def test_v312_ui_and_version_present():
    app=open('app.py', encoding='utf-8').read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert 'Drift Attribution · vilka typer av case står för tappet?' in app
    assert 'failure_cohort_table' in app
