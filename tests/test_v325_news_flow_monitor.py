import pandas as pd
from news_flow_monitor import build_news_flow_monitor


def flat_hist():
    idx = pd.date_range('2026-08-01', periods=30, freq='B', tz='UTC')
    return pd.DataFrame({'Close':[100.0]*30}, index=idx)


def rising_late_hist():
    idx = pd.date_range('2026-08-01', periods=30, freq='B', tz='UTC')
    vals = [100.0]*22 + [100.5, 101.0, 102.0, 103.0, 103.0, 103.0, 103.0, 103.0]
    return pd.DataFrame({'Close':vals}, index=idx)


def test_two_independent_positive_days_can_create_improving_underreaction_flow():
    events={'news':[
        {'title':'Company raises guidance for full year','provider':'Reuters','published_at':'2026-08-26T08:00:00Z'},
        {'title':'Company wins contract worth 500 million','provider':'Business Wire','published_at':'2026-08-29T08:00:00Z'},
    ]}
    out=build_news_flow_monitor(events,flat_hist(),pd.Timestamp('2026-08-30',tz='UTC'))
    assert out['News Flow Status']=='Förbättrande flöde · möjlig underreaktion'
    assert out['News Flow Independent Positive 14d']==2
    assert out['News Flow Distinct Positive Days']==2


def test_syndicated_duplicate_does_not_count_as_two_events():
    events={'news':[
        {'title':'Company raises guidance for full year','provider':'Reuters','published_at':'2026-08-29T08:00:00Z'},
        {'title':'Company raises guidance for full year','provider':'Business Wire','published_at':'2026-08-29T12:00:00Z'},
    ]}
    out=build_news_flow_monitor(events,flat_hist(),pd.Timestamp('2026-08-30',tz='UTC'))
    assert out['News Flow Independent Positive 14d']==1
    assert out['News Flow Unique Items 30d']==1
    assert not out['News Flow Status'].startswith('Förbättrande flöde')


def test_fresh_negative_strong_source_breaks_positive_sequence():
    events={'news':[
        {'title':'Company raises guidance for full year','provider':'Reuters','published_at':'2026-08-24T08:00:00Z'},
        {'title':'Company wins contract worth 500 million','provider':'Business Wire','published_at':'2026-08-26T08:00:00Z'},
        {'title':'Company cuts guidance after weak demand','provider':'Reuters','published_at':'2026-08-29T08:00:00Z'},
    ]}
    out=build_news_flow_monitor(events,flat_hist(),pd.Timestamp('2026-08-30',tz='UTC'))
    assert out['News Flow Independent Negative 14d']==1
    assert out['News Flow Status'] in {'Negativ nyhet bryter flödet','Försämrande nyhetsflöde'}


def test_direction_shift_compares_recent_with_prior_window_without_synthetic_score():
    events={'news':[
        {'title':'Company cuts guidance','provider':'Yahoo Finance','published_at':'2026-08-05T08:00:00Z'},
        {'title':'Company raises guidance','provider':'Yahoo Finance','published_at':'2026-08-22T08:00:00Z'},
        {'title':'Company wins contract','provider':'Yahoo Finance','published_at':'2026-08-28T08:00:00Z'},
    ]}
    out=build_news_flow_monitor(events,flat_hist(),pd.Timestamp('2026-08-30',tz='UTC'))
    assert out['News Flow Direction Shift'] >= 2
    assert out['News Flow Status']=='Nyhetsriktningen förbättras'


def test_warning_explicitly_denies_causality():
    out=build_news_flow_monitor({},flat_hist(),pd.Timestamp('2026-08-30',tz='UTC'))
    assert 'inte bevisad kausalitet' in out['News Flow Warning']
    assert out['News Flow Status']=='För lite nyhetsflöde'
