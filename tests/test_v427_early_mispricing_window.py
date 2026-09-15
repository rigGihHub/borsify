from early_mispricing_window import assess_early_mispricing_window

def test_market_wrong_with_kpi_revisions_and_muted_price_is_early():
    r=assess_early_mispricing_window({"Value Trap verdict":"MARKET_WRONG","KPI Inflection nivå":2,"Revision breadth nivå":2,"1 mån":.04,"3 mån":.10,"Relativ marknad 3 mån":.03,"Relativ sektor 3 mån":.02,"Ingångsläge nivå":"green","Analysis Confidence Score":75})
    assert r["Early Mispricing nivå"]==3

def test_big_rerating_blocks_early_label():
    r=assess_early_mispricing_window({"Value Trap verdict":"MARKET_WRONG","KPI Inflection nivå":2,"Revision breadth nivå":2,"1 mån":.30,"3 mån":.55,"Relativ marknad 3 mån":.30,"Ingångsläge nivå":"green","Analysis Confidence Score":80})
    assert r["Early Mispricing status"]=="RERATING_ADVANCED"

def test_value_trap_cannot_be_early_mispricing():
    r=assess_early_mispricing_window({"Value Trap verdict":"VALUE_TRAP","KPI Inflection nivå":3,"Revision breadth nivå":3,"1 mån":0,"3 mån":0,"Ingångsläge nivå":"green"})
    assert r["Early Mispricing nivå"]==0

def test_positive_estimates_can_supply_independent_improvement():
    r=assess_early_mispricing_window({"Value Trap verdict":"POSSIBLY_MISPRICED","EPS-estimat förändring":.05,"EPS-revisionsbalans":.5,"Estimat tillförlitlighetsvikt":.8,"1 mån":.02,"3 mån":.08,"Relativ marknad 3 mån":.02,"Relativ sektor 3 mån":.01,"Ingångsläge nivå":"green","Analysis Confidence Score":70})
    assert r["Early Mispricing nivå"]>=2

def test_low_confidence_downgrades_positive_early_case():
    r=assess_early_mispricing_window({"Value Trap verdict":"MARKET_WRONG","KPI Inflection nivå":2,"Revision breadth nivå":2,"1 mån":.02,"3 mån":.08,"Relativ marknad 3 mån":.01,"Relativ sektor 3 mån":.01,"Ingångsläge nivå":"green","Analysis Confidence Score":35})
    assert r["Early Mispricing nivå"]==1

def test_app_and_ledger_expose_frozen_signal():
    app=open('app.py',encoding='utf-8').read(); led=open('recommendation_ledger.py',encoding='utf-8').read()
    assert 'APP_VERSION = "4.39.0"' in app
    assert 'add_early_mispricing_window(ranked)' in app
    assert '"Tidig felprissättning"' in app
    assert '"Early Mispricing status"' in led
