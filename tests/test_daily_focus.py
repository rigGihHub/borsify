from datetime import datetime

from daily_focus import build_daily_focus, focus_context


def test_focus_prefers_important_watch_change_over_plain_candidate():
    out = build_daily_focus(
        candidates=[{'Ticker':'AAA','Namn':'A','Prioritet':'Medel','Dagens relevans':65,'Borsify Score':72}],
        watch_changes=[{'ticker':'BBB','name':'B','tone':'negative','status':'Caset har försvagats','score_delta':-12,'summary':'Scoren har fallit.'}],
        signals=[],
        now=datetime(2026, 9, 1, 12, 0),
    )
    assert out[0]['ticker'] == 'BBB'


def test_focus_deduplicates_same_ticker():
    out = build_daily_focus(
        candidates=[{'Ticker':'AAA','Prioritet':'Hög','Dagens relevans':90,'Borsify Score':80}],
        watch_changes=[],
        signals=[{'symbol':'AAA','kind':'Ny i topp 10','text':'Ny signal','priority':3}],
        now=datetime(2026, 9, 1, 12, 0),
    )
    assert len(out) == 1
    assert out[0]['ticker'] == 'AAA'


def test_focus_limit_is_respected():
    candidates = [{'Ticker':t,'Prioritet':'Hög','Dagens relevans':80,'Borsify Score':75} for t in ['A','B','C','D']]
    out = build_daily_focus(candidates=candidates, watch_changes=[], signals=[], limit=3, now=datetime(2026, 9, 1, 12, 0))
    assert len(out) == 3


def test_focus_context_before_open():
    ctx = focus_context(datetime(2026, 9, 1, 6, 53))
    assert ctx['phase'] == 'preopen'
    assert ctx['title'] == 'Inför börsöppning'


def test_focus_context_during_day_and_after_close():
    assert focus_context(datetime(2026, 9, 1, 10, 15))['phase'] == 'session'
    assert focus_context(datetime(2026, 9, 1, 18, 15))['phase'] == 'afterclose'


def test_focus_context_weekend():
    assert focus_context(datetime(2026, 9, 5, 10, 0))['phase'] == 'weekend'


def test_recent_signal_gets_freshness_label_and_bonus():
    now = datetime(2026, 9, 1, 12, 0)
    out = build_daily_focus(
        signals=[
            {'symbol':'NEW','kind':'Ny i topp 10','text':'Ny signal','priority':2,'created_at':'2026-09-01T10:00:00'},
            {'symbol':'OLD','kind':'Ny i topp 10','text':'Äldre signal','priority':2,'created_at':'2026-08-28T10:00:00'},
        ],
        now=now,
    )
    assert out[0]['ticker'] == 'NEW'
    assert out[0]['freshness'] == 'Nytt i dag'


def test_time_context_never_changes_core_score_fields():
    candidate = {'Ticker':'AAA','Prioritet':'Hög','Dagens relevans':90,'Borsify Score':80}
    before = dict(candidate)
    build_daily_focus(candidates=[candidate], now=datetime(2026, 9, 1, 6, 0))
    assert candidate == before
