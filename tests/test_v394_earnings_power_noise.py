from earnings_power_noise import assess_earnings_power_noise

def test_explicit_temporary_noise_can_be_strong_candidate():
    r=assess_earnings_power_noise({
        'Kvalitet':80,'Risk':70,'INVEST Score':75,
        'Vinst YoY senaste kvartal':-.18,'Marginal YoY förändring':-.02,
        'Omsättning YoY senaste kvartal':.08,'Omsättning acceleration':.02,'FCF YoY senaste kvartal':.20,
        'Report Delta positiva':4,'Report Delta negativa':1,'EPS-estimat förändring':.01,
        'Report Delta guidance':'temporary restructuring charge; outlook maintained',
    },'long')
    assert r['Earnings power noise nivå'] == 3
    assert r['Earnings power temporary verified'] is True

def test_no_temporary_claim_without_explicit_evidence():
    r=assess_earnings_power_noise({
        'Kvalitet':80,'Risk':70,'INVEST Score':75,
        'Vinst YoY senaste kvartal':-.18,'Omsättning YoY senaste kvartal':.08,
        'FCF YoY senaste kvartal':.20,'Report Delta positiva':4,'Report Delta negativa':1,
    },'long')
    assert r['Earnings power noise nivå'] >= 1
    assert r['Earnings power temporary verified'] is False
    assert 'inte explicit bevis' in r['Earnings power förklaring']

def test_broad_deterioration_blocks_noise_interpretation():
    r=assess_earnings_power_noise({
        'Vinst YoY senaste kvartal':-.30,'Omsättning YoY senaste kvartal':-.10,'FCF YoY senaste kvartal':-.30,
        'Report Delta positiva':0,'Report Delta negativa':4,'EPS-estimat förändring':-.08,
        'Report Delta guidance':'cuts guidance after profit warning',
    },'long')
    assert r['Earnings power noise nivå'] == -1

def test_signal_is_long_horizon_only():
    r=assess_earnings_power_noise({'Vinst YoY senaste kvartal':-.2,'Omsättning YoY senaste kvartal':.1,'FCF YoY senaste kvartal':.2,'Kvalitet':80},'medium')
    assert r['Earnings power noise nivå'] == 0

def test_release_wiring():
    app=open('app.py',encoding='utf-8').read(); rank=open('horizon_rankings.py',encoding='utf-8').read(); ledger=open('recommendation_ledger.py',encoding='utf-8').read()
    assert 'APP_VERSION = "4.39.1"' in app
    assert 'add_earnings_power_noise(ranked, horizon)' in app
    assert "add_earnings_power_noise(out,horizon)" in rank.replace(" ", "")
    assert '"Deal Conviction Score"' in rank
    assert '"Earnings power temporary verified"' in ledger
