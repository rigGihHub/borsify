from datetime import datetime

from since_last_visit import build_since_last_visit, visit_label


def test_first_visit_does_not_pretend_existing_items_are_new():
    out = build_since_last_visit(None, signals=[{'symbol':'AAA','created_at':'2026-09-01T06:00:00'}])
    assert out == []


def test_only_items_after_previous_visit_are_returned():
    out = build_since_last_visit(
        '2026-09-01T05:00:00',
        signals=[
            {'symbol':'OLD','kind':'Score lyfter','text':'gammal','priority':3,'created_at':'2026-09-01T04:59:00'},
            {'symbol':'NEW','kind':'Ny i topp 10','text':'ny','priority':2,'created_at':'2026-09-01T05:01:00'},
        ],
    )
    assert [x['ticker'] for x in out] == ['NEW']


def test_watch_change_can_be_new_since_last_visit():
    out = build_since_last_visit(
        '2026-08-31T20:00:00',
        watch_changes=[{'ticker':'BBB','tone':'negative','status':'Caset försvagas','summary':'Score ned.','changed_at':'2026-09-01'}],
    )
    assert out[0]['ticker'] == 'BBB'
    assert out[0]['kind'] == 'Bevakat case'


def test_same_ticker_is_deduplicated_to_strongest_reason():
    out = build_since_last_visit(
        '2026-08-31T20:00:00',
        signals=[{'symbol':'AAA','kind':'Ny signal','priority':1,'created_at':'2026-09-01T05:00:00'}],
        watch_changes=[{'ticker':'AAA','tone':'negative','status':'Caset försvagas','changed_at':'2026-09-01T00:00:00'}],
    )
    assert len(out) == 1
    assert out[0]['kind'] == 'Bevakat case'


def test_visit_label_is_plain_language():
    now = datetime(2026, 9, 1, 6, 55)
    assert visit_label(None, now) == 'Första besöket'
    assert 'cirka' in visit_label('2026-09-01T06:20:00', now)
    assert visit_label('2026-08-31T12:00:00', now) == 'Sedan i går'


def test_reviewed_change_is_hidden_but_later_event_same_ticker_can_show():
    first = build_since_last_visit(
        '2026-09-01T05:00:00',
        signals=[{'event_key':'e1','symbol':'AAA','kind':'Score lyfter','created_at':'2026-09-01T05:10:00'}],
    )
    assert len(first) == 1
    reviewed = {first[0]['key']}
    out = build_since_last_visit(
        '2026-09-01T05:00:00',
        signals=[
            {'event_key':'e1','symbol':'AAA','kind':'Score lyfter','created_at':'2026-09-01T05:10:00'},
            {'event_key':'e2','symbol':'AAA','kind':'Ny i topp 10','created_at':'2026-09-01T05:20:00'},
        ],
        reviewed_keys=reviewed,
    )
    assert len(out) == 1
    assert out[0]['headline'] == 'Ny i topp 10'


def test_signal_source_event_key_makes_review_key_stable():
    a = build_since_last_visit(
        '2026-09-01T05:00:00',
        signals=[{'event_key':'fixed-123','symbol':'AAA','kind':'Score lyfter','text':'A','created_at':'2026-09-01T05:10:00'}],
    )
    b = build_since_last_visit(
        '2026-09-01T05:00:00',
        signals=[{'event_key':'fixed-123','symbol':'AAA','kind':'Score lyfter','text':'ändrad visningstext','created_at':'2026-09-01T05:10:00'}],
    )
    assert a[0]['key'] == b[0]['key'] == 'source:fixed-123'


def test_each_item_exposes_a_context_target():
    sig = build_since_last_visit(
        '2026-09-01T05:00:00',
        signals=[{'symbol':'AAA','kind':'Score lyfter','created_at':'2026-09-01T05:10:00'}],
    )
    watch = build_since_last_visit(
        '2026-09-01T05:00:00',
        watch_changes=[{'ticker':'BBB','status':'Caset försvagas','changed_at':'2026-09-01T05:10:00'}],
    )
    assert sig[0]['target'] == 'signal'
    assert watch[0]['target'] == 'journal'
