from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import fundamental_acquisition as fa
from fundamental_cache import put_cached_fundamentals, get_cached_fundamentals
from scan_snapshot_cache import put_scan_snapshot, get_scan_snapshot, scan_reuse_seconds, snapshot_source_health
from source_health_dashboard import build_source_health_rows, summarize_source_health


def test_legacy_dividend_never_discards_other_facts(monkeypatch, tmp_path):
    db = tmp_path / 'cache.db'
    put_cached_fundamentals(db, 'AAA', {'P/E': 12, 'Direktavkastning': 1.86})
    monkeypatch.setattr(fa, '_yf', lambda: (_ for _ in ()).throw(AssertionError('no request needed')))
    data, health = fa.fetch_fundamentals('AAA', db, str)
    assert data['P/E'] == 12
    assert np.isnan(data['Direktavkastning'])
    assert health['cache'] == 'HIT'


def test_fallback_expires_and_failed_fetch_is_not_persisted(monkeypatch, tmp_path):
    db = tmp_path / 'cache.db'
    put_cached_fundamentals(db, 'AAA', {'P/E': 12}, now=datetime.now(timezone.utc)-timedelta(hours=73))
    class T:
        def get_info(self): return {}
        info = {}
    class YF:
        Ticker = staticmethod(lambda s: T())
    monkeypatch.setattr(fa, '_yf', lambda: YF)
    data, health = fa.fetch_fundamentals('AAA', db, str)
    assert health['status'] == 'ERROR'
    assert np.isnan(data['P/E'])
    assert get_cached_fundamentals(db, 'AAA') is None


def test_zero_coverage_retries_after_five_minutes_without_busy_loop(tmp_path):
    db = tmp_path / 'cache.db'
    frame = pd.DataFrame([{'Ticker': 'AAA', 'Pris': 100}])
    saved = put_scan_snapshot(db, ['AAA'], frame)
    observed = datetime.fromisoformat(saved['captured_at'])
    assert get_scan_snapshot(db, ['AAA'], now=observed+timedelta(minutes=4))[1]['hit']
    assert not get_scan_snapshot(db, ['AAA'], now=observed+timedelta(minutes=5))[1]['hit']
    assert scan_reuse_seconds(frame) == 300
    assert scan_reuse_seconds(frame.assign(**{'P/E': 12})) == 7200


def test_source_error_survives_snapshot_roundtrip(tmp_path):
    db = tmp_path / 'cache.db'
    frame = pd.DataFrame([{'Ticker': 'AAA', 'Fundamental source status': 'ERROR',
                           'Fundamental source errors': 'get_info:no_financial_data'}])
    put_scan_snapshot(db, ['AAA'], frame)
    restored, _ = get_scan_snapshot(db, ['AAA'])
    rows = build_source_health_rows({'bq_source_health_fundamentals': snapshot_source_health(restored)})
    assert summarize_source_health(rows)['error'] == 1
    assert 'no_financial_data' in rows.iloc[0]['errors']


def test_unknown_source_cannot_be_green():
    frame = pd.DataFrame([{'Ticker': 'AAA', 'P/E': 12}])
    rows = build_source_health_rows({'bq_source_health_fundamentals': snapshot_source_health(frame)})
    assert summarize_source_health(rows)['warning'] == 1


def test_workers_do_not_mutate_streamlit_session_and_errors_not_cached():
    source = Path('app.py').read_text()
    start = source.index('def fetch_fundamentals(')
    body = source[start:source.index('def fetch_bulk_price_history', start)]
    assert 'st.session_state' not in body
    assert '@st.cache_data' not in source[source.rfind('\n\n', 0, start):start]
    assert source.index('snapshot_source_health(raw_df)') < source.index('_source_rows = build_source_health_rows(st.session_state)', source.index('snapshot_source_health(raw_df)'))
