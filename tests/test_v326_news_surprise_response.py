import pandas as pd
from news_surprise_response import build_news_surprise_response, classify_news_surprise


def flat_hist():
    idx = pd.date_range('2026-08-01', periods=30, freq='B', tz='UTC')
    return pd.DataFrame({'Close':[100.0]*30}, index=idx)


def test_explicit_raise_guidance_is_stronger_than_generic_positive_news():
    a = {'title':'Company raises guidance after stronger than expected demand','direction':'positive','type':'Höjd prognos/guidance'}
    b = {'title':'Company wins contract','direction':'positive','type':'Order/kontrakt'}
    assert classify_news_surprise(a)[2] == 3
    assert classify_news_surprise(b)[2] == 2


def test_clear_positive_surprise_with_small_response_can_flag_underreaction():
    events={'news':[{'title':'Company raises guidance after stronger than expected demand','provider':'Reuters','published_at':'2026-08-28T08:00:00Z'}]}
    out=build_news_surprise_response(events, flat_hist(), pd.Timestamp('2026-08-29',tz='UTC'))
    assert out['News Surprise Underreaction'] is True
    assert out['News Surprise Strength'] == 3
    assert 'underreaktion' in out['News Surprise Status'].lower()


def test_negative_surprise_has_priority_over_positive_event():
    events={'news':[
        {'title':'Company wins contract worth 500 million','provider':'Reuters','published_at':'2026-08-28T08:00:00Z'},
        {'title':'Company cuts guidance after weaker than expected demand','provider':'Reuters','published_at':'2026-08-29T08:00:00Z'},
    ]}
    out=build_news_surprise_response(events, flat_hist(), pd.Timestamp('2026-08-30',tz='UTC'))
    assert out['News Surprise Primary Direction'] == 'negative'
    assert 'negativ' in out['News Surprise Primary Label'].lower()


def test_generic_earnings_headline_does_not_invent_consensus_surprise():
    events={'news':[{'title':'Company reports second quarter results','provider':'Reuters','published_at':'2026-08-28T08:00:00Z'}]}
    out=build_news_surprise_response(events, flat_hist(), pd.Timestamp('2026-08-29',tz='UTC'))
    assert out['News Surprise Strength'] == 0
    assert out['News Surprise Status'] == 'Ingen tydlig överraskning'


def test_relative_reference_requires_two_older_same_type_events():
    events={'news':[
        {'title':'Company raises guidance','provider':'Reuters','published_at':'2026-08-28T08:00:00Z'},
        {'title':'Company raised guidance','provider':'Reuters','published_at':'2026-08-10T08:00:00Z'},
    ]}
    out=build_news_surprise_response(events, flat_hist(), pd.Timestamp('2026-08-29',tz='UTC'))
    assert out['News Surprise Reference N'] == 0


def test_warning_denies_fake_consensus_and_causality():
    out=build_news_surprise_response({}, flat_hist(), pd.Timestamp('2026-08-29',tz='UTC'))
    warning=out['News Surprise Warning'].lower()
    assert 'inte verifierad konsensusavvikelse' in warning
    assert 'inte bevisad kausalitet' in warning
