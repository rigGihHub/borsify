import numpy as np
import pandas as pd
import pytest
import fundamental_acquisition as fa
from fundamental_cache import get_cached_fundamentals, put_cached_fundamentals
from scan_snapshot_cache import fundamental_coverage, put_scan_snapshot, get_scan_snapshot


@pytest.mark.parametrize('info', [{}, {'shortName': 'A', 'currentPrice': 10}, {'marketCap': float('nan')}])
def test_empty_financial_response_is_error_and_never_cached(monkeypatch, tmp_path, info):
    class T:
        def get_info(self): return info
    T.info = info
    class YF:
        Ticker = staticmethod(lambda s: T())
    monkeypatch.setattr(fa, '_yf', lambda: YF)
    db = tmp_path / 'x.db'
    payload, health = fa.fetch_fundamentals('AAA', db, lambda x: x)
    assert health['status'] == 'ERROR'
    assert payload['_Fundamental cache'] == 'fel'
    assert get_cached_fundamentals(db, 'AAA') is None


def test_bad_legacy_cache_is_refetched_and_zero_is_valid(monkeypatch, tmp_path):
    db = tmp_path / 'x.db'
    put_cached_fundamentals(db, 'AAA', {'Namn': 'AAA'})
    class T:
        def get_info(self): return {'profitMargins': 0, 'shortName': 'New'}
    class YF:
        Ticker = staticmethod(lambda s: T())
    monkeypatch.setattr(fa, '_yf', lambda: YF)
    payload, health = fa.fetch_fundamentals('AAA', db, lambda x: x)
    assert health['cache'] == 'MISS'
    assert payload['Vinstmarginal'] == 0
    assert payload['Namn'] == 'New'


def test_failed_forced_refresh_preserves_prior_payload_and_timestamp(monkeypatch, tmp_path):
    db = tmp_path / 'x.db'
    original = {'Namn': 'Old', 'P/E': 12, 'Fundamental hämtad': '2026-09-30T12:00:00'}
    put_cached_fundamentals(db, 'AAA', original)
    class T:
        def get_info(self): return {}
        info = {}
    class YF:
        Ticker = staticmethod(lambda s: T())
    monkeypatch.setattr(fa, '_yf', lambda: YF)
    payload, health = fa.fetch_fundamentals('AAA', db, lambda x: x, force_refresh=True)
    assert health['status'] == 'ERROR'
    assert payload['Namn'] == 'AAA'  # current failure, never merged with old facts
    assert get_cached_fundamentals(db, 'AAA') == original


def test_snapshot_regression_keeps_whole_previous_frame_and_time(tmp_path):
    db = tmp_path / 'x.db'
    good = pd.DataFrame([{'Ticker': 'AAA', 'Pris': 100, 'P/E': 12, 'ROE': .15}])
    first = put_scan_snapshot(db, ['AAA'], good)
    bad = pd.DataFrame([{'Ticker': 'AAA', 'Pris': 110, 'P/E': np.nan, 'ROE': np.nan}])
    assert put_scan_snapshot(db, ['AAA'], bad)['reason'] == 'reduced_data_coverage'
    restored, meta = get_scan_snapshot(db, ['AAA'])
    assert restored.iloc[0]['Pris'] == 100
    assert meta['captured_at'] == first['captured_at']
    better = good.assign(**{'Forward P/E': 10})
    assert put_scan_snapshot(db, ['AAA'], better)['saved']


def test_coverage_counts_finite_facts_not_price_or_name():
    frame = pd.DataFrame([{'Namn': 'AAA', 'Pris': 100}, {'P/E': np.inf}, {'ROE': 0}])
    assert fundamental_coverage(frame) == {'rows': 3, 'with_data': 1, 'complete': 0, 'facts': 1}


def test_partial_refresh_does_not_replace_richer_fundamental_cache(monkeypatch, tmp_path):
    db = tmp_path / 'x.db'
    original = {'Namn': 'Old', 'P/E': 12, 'ROE': .2}
    put_cached_fundamentals(db, 'AAA', original)
    class T:
        def get_info(self): return {'marketCap': 1000}
    class YF:
        Ticker = staticmethod(lambda s: T())
    monkeypatch.setattr(fa, '_yf', lambda: YF)
    payload, health = fa.fetch_fundamentals('AAA', db, lambda x: x, force_refresh=True)
    assert health['status'] == 'PARTIAL'
    assert np.isnan(payload['P/E'])
    assert get_cached_fundamentals(db, 'AAA') == original
