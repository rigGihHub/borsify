import ast
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from recommendation_ledger import build_recommendation_records, restore_frozen_scores, evaluate_record_from_history
from score_calibration import prepare_score_calibration_data, score_calibration_table
from score_inputs import _risk_score, _percentile_score
from position_entry_guidance import assess_position_entry
from inflection_engine import _yoy
from case_ai import build_case_ai_context
from outcome_currency import prices_in_sek
from fx import major_currency, major_amount_to_sek, quote_amount_to_sek


def app_functions(names, **env):
    source = ast.parse(Path('app.py').read_text())
    code = ast.Module(body=[n for n in source.body if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[])
    namespace = {'pd': pd, 'np': np, 'Any': Any, 'sqlite3': sqlite3, 'restore_frozen_scores': restore_frozen_scores, **env}
    exec(compile(code, 'app_contract', 'exec'), namespace)
    return namespace


def case(signal='BEVAKA'):
    return pd.DataFrame([{'Ticker': 'TEST.ST', 'Pris': 100, 'INVEST Score': 92,
                          'Case Gate': 'Toppcase', 'Borsify slutbetyg': 68,
                          'Borsify grundbetyg': 92, 'Signal': signal, 'Visad horisont': 'year'}])


def records(signal='BEVAKA'):
    return build_recommendation_records(case(signal), 'long', '4.40.0', 'Balanserad', 'Sverige', captured_at=pd.Timestamp('2025-01-02T12:00Z'))


def test_actual_sqlite_roundtrip_preserves_score_and_first_capture():
    source = ast.parse(Path('app.py').read_text())
    ddl = next(n.value for n in ast.walk(source) if isinstance(n, ast.Constant) and isinstance(n.value, str) and 'CREATE TABLE IF NOT EXISTS recommendation_ledger (' in n.value)
    conn = sqlite3.connect(':memory:'); conn.execute(ddl)
    ns = app_functions({'save_recommendation_records', 'get_recommendation_records'}, _supabase_client=lambda: None,
                       current_user_id=lambda: None, init_db=lambda: None, _db_connect=lambda: conn)
    original = records(); ns['save_recommendation_records'](original)
    changed = records('KÖP / ÄG'); changed[0]['entry_price'] = 999
    ns['save_recommendation_records'](changed)
    read = ns['get_recommendation_records']()
    assert read.iloc[0]['entry_price'] == 100
    assert read.iloc[0]['final_score'] == 68
    assert read.iloc[0]['raw_borsify_score'] == 92
    assert json.loads(read.iloc[0]['snapshot_json'])['Ledger Decision'] == 'NOT_RECOMMENDED'
    outcomes = pd.DataFrame([{'record_id': original[0]['record_id'], 'horizon': '1y', 'return_pct': .1}])
    assert len(prepare_score_calibration_data(read, outcomes, '1y', 'long')) == 1
    table = score_calibration_table(read, outcomes, '1y')
    assert {'Medianutfall', 'Positiva'}.issubset(table.columns)


def test_cloud_payload_matches_existing_schema_and_ignores_duplicate():
    calls = []
    class Client:
        def table(self, name):
            assert name == 'recommendation_ledger'; return self
        def upsert(self, payload, **kwargs):
            calls.append((payload, kwargs)); return self
        def execute(self):
            return None
    ns = app_functions({'save_recommendation_records'}, _supabase_client=lambda: Client(), current_user_id=lambda: 'user')
    ns['save_recommendation_records'](records())
    payload, options = calls[0]
    assert options['ignore_duplicates'] is True
    assert 'final_score' not in payload and 'raw_borsify_score' not in payload
    assert json.loads(payload['snapshot_json'])['Borsify slutbetyg'] == 68


def test_legacy_missing_score_is_never_reconstructed_from_raw_score():
    row = restore_frozen_scores(pd.DataFrame([{'snapshot_json': '{"Borsify Score": 99}'}]))
    assert pd.isna(row.iloc[0]['final_score'])


def test_unshown_finalist_is_not_claimed_as_a_buy():
    f = case().drop(columns=['Signal', 'Visad horisont'])
    snap = json.loads(build_recommendation_records(f, 'long', '4.40.0', 'Balanserad', 'Sverige')[0]['snapshot_json'])
    assert snap['Ledger Decision'] == 'ANALYSED_FINALIST'


def test_horizon_capture_ids_are_separate():
    a = records()[0]['record_id']
    f = case(); f['Visad horisont'] = 'lifetime'
    b = build_recommendation_records(f, 'long', '4.40.0', 'Balanserad', 'Sverige', captured_at=pd.Timestamp('2025-01-02T12:00Z'))[0]['record_id']
    assert a != b


def test_split_adjusted_series_does_not_use_old_raw_entry_denominator():
    record = records()[0]
    idx = pd.bdate_range('2025-01-02', periods=24)
    stock = pd.DataFrame({'Close': 50.0}, index=idx); stock.attrs['currency'] = 'SEK'
    bench = pd.DataFrame({'Close': 100.0}, index=idx); bench.attrs['currency'] = 'SEK'
    rows = evaluate_record_from_history(record, stock, as_of=idx[-1], benchmark_history=bench)
    one = next(r for r in rows if r['horizon'] == '1m')
    assert one['return_pct'] == 0 and one['excess_return_pct'] == 0
    assert one['evaluated_date'] == idx[22].date().isoformat()
    assert record['entry_price'] == 100


def test_incompatible_or_unknown_currency_never_claims_alpha():
    idx = pd.bdate_range('2025-01-02', periods=24)
    stock = pd.DataFrame({'Close': 50.0}, index=idx); stock.attrs['currency'] = 'SEK'
    bench = pd.DataFrame({'Close': 100.0}, index=idx); bench.attrs['currency'] = 'USD'
    rows = evaluate_record_from_history(records()[0], stock, as_of=idx[-1], benchmark_history=bench)
    assert all(r['excess_return_pct'] is None for r in rows)


def test_fx_matching_never_uses_future_rates():
    stock = pd.DataFrame({'Close': [10, 10]}, index=pd.to_datetime(['2025-01-02', '2025-01-03']))
    rates = pd.DataFrame({'Close': [11]}, index=pd.to_datetime(['2025-01-03']))
    result = prices_in_sek(stock, 'USD', rates)
    assert result.index.tolist() == [pd.Timestamp('2025-01-03')]
    assert result.iloc[0]['Close'] == 110


def test_missing_risk_and_percentile_data_is_not_positive_evidence():
    fields = ['Skuld/eget kapital','ROE','Vinstmarginal','52v från topp','Avstånd SMA200','3 mån']
    assert _risk_score(pd.DataFrame([{f: np.nan for f in fields}])).iloc[0] == 0
    assert _percentile_score(pd.Series([np.nan, 2., 3.])).iloc[0] == 0


@pytest.mark.parametrize('missing', ['Risk', 'Ingångsläge nivå', 'Bolagsbedömning nivå'])
def test_missing_position_inputs_stop_execution(missing):
    row = {'Risk': 75, 'Ingångsläge nivå': 'green', 'Bolagsbedömning nivå': 'green', 'Data Trust status': 'GOTT UNDERLAG', 'Analysis Confidence Score':80}
    row.pop(missing)
    assert assess_position_entry(row)['Första positionsstorlek %'] == 0


def test_missing_data_trust_caps_even_green_inputs():
    assert assess_position_entry({'Risk': 75, 'Ingångsläge nivå': 'green', 'Bolagsbedömning nivå': 'green'})['Första positionsstorlek %'] == 50


def test_negative_base_and_missing_quarter_are_not_positive_growth():
    assert pd.isna(_yoy(pd.Series([-200,-150,-120,-110,-100])))
    assert pd.isna(_yoy(pd.Series([2,2,2,2,1], index=pd.to_datetime(['2026-06-30','2026-03-31','2025-12-31','2025-09-30','2024-12-31']))))


def test_cross_currency_cap_uses_quote_currency_and_fcf_uses_same_units():
    ns = app_functions({'add_sek_conversions'}, major_currency=major_currency, major_amount_to_sek=major_amount_to_sek,
                       quote_amount_to_sek=quote_amount_to_sek, fetch_fx_rates_to_sek=lambda _: {'SEK':1, 'USD':10})
    frame = pd.DataFrame([{'Pris':100,'Valuta':'SEK','Finansiell valuta':'USD','Börsvärde lokal mdr':1,
                           '_Raw freeCashflow':10_000_000, '_Raw marketCap':1_000_000_000}])
    result, _, _ = ns['add_sek_conversions'](frame)
    assert result.iloc[0]['Börsvärde BSEK'] == 1
    assert result.iloc[0]['FCF-yield'] == .1


def test_ai_explains_the_visible_decision_and_correct_horizon():
    row = case().iloc[0].to_dict(); row['FCF-yield'] = .03; row['Investmentbolag rankningstak'] = 68
    context = build_case_ai_context(row, 'year')
    assert context['horizon'] == '3–12 månader'
    assert context['case_data']['Borsify slutbetyg'] == 68
    assert context['case_data']['Signal'] == 'BEVAKA'
    assert context['case_data']['Investmentbolag rankningstak'] == 68
    assert context['case_data']['FCF-yield'] == .03


def test_missing_mature_outcomes_are_visible_and_not_positive_evidence():
    from prospective_coverage import outcome_coverage
    audit = outcome_coverage(pd.DataFrame(records()), pd.DataFrame(), as_of='2026-06-01')
    assert audit['expected_due'] >= 5
    assert audit['missing'] == audit['expected_due']


def test_partial_benchmark_coverage_preserves_relative_measurement():
    from score_calibration import _outcome_basis
    assert _outcome_basis(pd.DataFrame({'excess_return_pct':[.1, np.nan]}))[0] == 'excess_return_pct'


def test_future_unfinished_horizons_do_not_starve_other_due_cases():
    from prospective_worker import evaluate_due_records
    r = records()[0]; r['user_id'] = 'user'
    idx=pd.bdate_range('2025-01-02',periods=50)
    history=pd.DataFrame({'Close':100.0},index=idx);history.attrs['currency']='SEK'
    calls=[]
    def fetch(symbol,date):
        calls.append(symbol);return history
    existing={(r['record_id'],'1w'),(r['record_id'],'1m')}
    result=evaluate_due_records([r],existing,fetch,lambda *_:('INDEX','Index',history),as_of='2025-02-20',limit=1)
    assert result==[] and calls==[]
    later=evaluate_due_records([r],set(),fetch,lambda *_:('INDEX','Index',history),as_of='2025-02-20',limit=1)
    assert {x['horizon'] for x in later}=={'1w','1m'}


def test_low_analysis_confidence_cannot_get_full_position_despite_green_axes():
    row={'Risk':75,'Ingångsläge nivå':'green','Bolagsbedömning nivå':'green','Data Trust status':'GOTT UNDERLAG','Analysis Confidence Score':40}
    result=assess_position_entry(row)
    assert result['Första positionsstorlek %']==50
    assert result['Positionsråd']=='🟡 Börja köpa försiktigt'


def test_price_only_index_cannot_manufacture_total_return_alpha():
    calls = []
    from types import SimpleNamespace
    ns = app_functions({'fetch_ledger_benchmark_history'},
                       st=SimpleNamespace(cache_data=lambda **kwargs: lambda function: function),
                       fetch_ledger_history=lambda symbol, date: calls.append(symbol) or pd.DataFrame({'Close': [100]}))
    assert ns['fetch_ledger_benchmark_history']('^OMXS30', '2025-01-02').empty
    assert calls == []
    assert not ns['fetch_ledger_benchmark_history']('VT', '2025-01-02').empty


def test_position_size_respects_displayed_wait_and_build_decisions():
    row = {'Bolagsbedömning nivå': 'green', 'Ingångsläge nivå': 'green', 'Risk': 75,
           'Data Trust status': 'GOTT UNDERLAG', 'Analysis Confidence Score': 80}
    assert assess_position_entry({**row, 'Signal': 'KÖP / ÄG'})['Första positionsstorlek %'] == 100
    assert assess_position_entry({**row, 'Signal': 'BYGG POSITION'})['Första positionsstorlek %'] == 50
    assert assess_position_entry({**row, 'Signal': 'BEVAKA'})['Första positionsstorlek %'] == 0
