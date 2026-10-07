import pandas as pd
import pytest
from scenario_engine import build_scenarios
from portfolio_advisor import assess_holding
from investment_controls import portfolio_exposure, holding_review


def test_low_pe_cannot_create_base_upside_without_growth():
    r = build_scenarios({'Pris':100,'EPS':20,'P/E':5}, {'Omsättning CAGR':0,'Vinst CAGR':0})
    assert r['base']['future_price'] == pytest.approx(100)
    assert r['base']['earnings_contribution'] + r['base']['multiple_contribution'] == pytest.approx(r['base']['upside'])


def test_cyclical_and_financial_models_fail_closed():
    r = {'Pris':100,'EPS':20,'Bransch':'Marine Shipping','Valuta':'SEK','Finansiell valuta':'SEK'}
    assert build_scenarios(r, {'Vinst CAGR':0})['status'] != 'OK'
    result = build_scenarios(r, {'Vinst CAGR':0,'Normaliserad EPS':10})
    assert result['base']['future_price'] == 50
    assert build_scenarios({**r,'Bransch':'Banks'}, {'Vinst CAGR':0})['status'] != 'OK'


def test_declining_earnings_preserve_scenario_order():
    r = build_scenarios({'Pris':100,'EPS':10}, {'Vinst CAGR':-.3})
    assert r['bear']['future_price'] < r['base']['future_price'] < r['bull']['future_price']


def test_missing_data_never_means_hold():
    assert assess_holding(100, {})['Status'] == 'KAN INTE BEDÖMAS'
    assert assess_holding(100, {'Pris':105,'Borsify Score':80})['Status'] == 'KAN INTE BEDÖMAS'


def test_exposure_uses_sek_and_aggregates_duplicate_holdings():
    h = pd.DataFrame([{'symbol':'A','quantity':10},{'symbol':'A','quantity':10},{'symbol':'B','quantity':10},{'symbol':'C','quantity':5}])
    q = pd.DataFrame([{'Ticker':'A','Pris SEK':100,'Pris':10,'Sektor':'Tech','Valuta':'USD'}, {'Ticker':'B','Pris SEK':200,'Pris':200,'Sektor':'Energy','Valuta':'SEK'}])
    before, missing = portfolio_exposure(h,q)
    assert missing == 1
    assert before['Bolag'].iloc[0,1] == 50
    after, _ = portfolio_exposure(h,q,q.iloc[0],4000)
    assert after['Bolag'].iloc[0,1] == 75


def test_review_is_frozen_and_requires_newer_data(tmp_path):
    db = tmp_path / 'review.db'
    first = {'Omsättningstillväxt':.1,'Vinstmarginal':.2,'Fundamental hämtad':'2026-10-01'}
    a, note = holding_review(1,first,db)
    assert 'köpdatum' in note
    b, _ = holding_review(1,{**first,'Vinstmarginal':.1},db)
    assert not any(p['Status']=='OMPRÖVA' for p in b)
    c, _ = holding_review(1,{**first,'Vinstmarginal':.1,'Fundamental hämtad':'2026-10-07'},db)
    assert any(p['Status']=='OMPRÖVA' for p in c)
    assert c[1]['Utgångsvärde'] == .2


def test_annual_eps_in_other_currency_is_not_used_as_quote_currency():
    result = build_scenarios({'Pris':100,'EPS':20,'Bransch':'Marine Shipping','Valuta':'SEK','Finansiell valuta':'USD'}, {'Vinst CAGR':0,'Normaliserad EPS':10})
    assert result['status'] != 'OK'
