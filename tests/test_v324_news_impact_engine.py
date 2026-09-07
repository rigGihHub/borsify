import pandas as pd
from news_impact_engine import build_news_impact_assessment


def hist():
    idx = pd.date_range('2026-08-25', periods=12, freq='B', tz='UTC')
    return pd.DataFrame({'Close':[100,100,100,101,101,101,102,102,102,102,102,102]}, index=idx)


def test_positive_strong_source_with_small_reaction_can_flag_underreaction():
    events={'news':[{'title':'Company raises guidance for full year','provider':'Reuters','published_at':'2026-08-28T08:00:00Z'}]}
    out=build_news_impact_assessment(events,hist(),pd.Timestamp('2026-08-29',tz='UTC'))
    assert out['News Impact Status']=='Möjlig underreaktion'
    assert out['News Impact Underreaction Count']==1


def test_negative_fresh_news_has_priority():
    events={'news':[{'title':'Company cuts guidance after weak demand','provider':'Reuters','published_at':'2026-08-28T08:00:00Z'}]}
    out=build_news_impact_assessment(events,hist(),pd.Timestamp('2026-08-29',tz='UTC'))
    assert out['News Impact Status']=='Färsk negativ nyhet'
    assert out['News Impact Negative Count']==1


def test_old_news_does_not_become_fresh_support():
    events={'news':[{'title':'Company wins contract','provider':'Reuters','published_at':'2026-07-01T08:00:00Z'}]}
    out=build_news_impact_assessment(events,hist(),pd.Timestamp('2026-08-29',tz='UTC'))
    assert out['News Impact Fresh Count']==0


def test_unknown_source_never_counts_as_underreaction_proof():
    events={'news':[{'title':'Company raises guidance','provider':'Random Blog','published_at':'2026-08-28T08:00:00Z'}]}
    out=build_news_impact_assessment(events,hist(),pd.Timestamp('2026-08-29',tz='UTC'))
    assert out['News Impact Underreaction Count']==0


def test_warning_denies_causality_claim():
    out=build_news_impact_assessment({},hist(),pd.Timestamp('2026-08-29',tz='UTC'))
    assert 'inte bevisad kausalitet' in out['News Impact Warning']
