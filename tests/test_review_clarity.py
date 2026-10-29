from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest
from review_clarity import earnings_hurdle, observation_status
from future_discovery import assess_future_candidate, select_future_companies
from data_trust import assess_data_trust
from purchase_consistency import purchase_blockers


def test_hurdle_reconstructs_target_price_after_five_years():
    growth = earnings_hurdle(100, 25, 5, .1)
    assert (1 + growth)**5 * 25 == pytest.approx(100 * 1.1**5)
    assert earnings_hurdle(25) == pytest.approx(.1)
    assert earnings_hurdle(50, 40) < earnings_hurdle(50, 20)


@pytest.mark.parametrize('value', [None, float('nan'), float('inf'), 0, -20, 'bad'])
def test_no_earnings_scenario_for_invalid_pe(value):
    assert earnings_hurdle(value) is None


def test_observation_status_counts_old_missing_and_future_without_scan_timestamp():
    frame = pd.DataFrame({'Prisdatum': ['2026-10-01', None, '2027-01-01'],
                          'Fundamental hämtad': ['2026-10-28T12:00:00Z', 'bad', '2026-10-01']})
    status = observation_status(frame, '2026-10-29T12:00:00Z')
    assert status['prices']['old'] == 1
    assert status['prices']['missing'] == 1
    assert status['prices']['future'] == 1
    assert status['fundamentals']['old'] == 1
    assert status['fundamentals']['oldest'].startswith('2026-10-01')
    assert observation_status(pd.DataFrame())['rows'] == 0


def test_theme_cannot_promote_declining_company_above_growing_business():
    now = datetime.now(timezone.utc)
    def case(ticker, growth, industry):
        return assess_future_candidate({'Ticker': ticker, 'Omsättningstillväxt': growth,
             'Bransch': industry, 'Fundamental hämtad': now.isoformat()}, now)
    ranked = select_future_companies(pd.DataFrame([case('DECLINE', -.2, 'Software'), case('GROW', .2, 'Other')]))
    assert ranked.iloc[0].Ticker == 'GROW'


def test_old_metrics_are_not_displayed_and_empty_payload_is_not_current_evidence():
    now = datetime.now(timezone.utc)
    row = assess_future_candidate({'Ticker': 'UNKNOWN', 'P/E': 90,
          'Fundamental hämtad': (now-timedelta(days=4)).isoformat()}, now)
    assert row['P/E'] is None
    assert row['Framtid underlag'] == 'Otillräckligt aktuellt underlag'
    empty = assess_future_candidate({'Ticker': 'UNKNOWN', 'Fundamental hämtad': now.isoformat()}, now)
    assert empty['Framtid underlag'] == 'Otillräckligt aktuellt underlag'


def test_future_and_stale_observations_stop_data_trust_and_purchase():
    now = datetime.now(timezone.utc)
    for changes in [{'Prisdatum': (now+timedelta(days=2)).isoformat()},
                    {'Fundamental hämtad': (now-timedelta(hours=73)).isoformat()},
                    {'Fundamental hämtad': 'bad'}]:
        row = {'Prisdatum': now.isoformat(), 'Fundamental hämtad': now.isoformat(), **changes}
        row.update(assess_data_trust(row))
        assert row['Data Trust status'] == 'STOPP'
        assert any('datakontrollen' in reason for reason in purchase_blockers(row))


def test_unchanged_observations_keep_cache_inputs_stable_across_reruns(monkeypatch):
    import data_trust
    class Clock:
        current = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
        @classmethod
        def now(cls, tz):
            return cls.current
    monkeypatch.setattr(data_trust, 'datetime', Clock)
    row = {'Prisdatum': '2026-10-28', 'Fundamental hämtad': '2026-10-29T10:00:00Z'}
    first = assess_data_trust(row)
    Clock.current += timedelta(seconds=10)
    assert assess_data_trust(row) == first
