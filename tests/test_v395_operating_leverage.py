from operating_leverage_setup import assess_operating_leverage_setup


def test_strong_early_operating_leverage_candidate():
    r=assess_operating_leverage_setup({
        'Omsättning YoY senaste kvartal':.14,
        'Omsättning acceleration':.07,
        'Marginal YoY förändring':.005,
        'Marginal YoY föregående kvartal':-.01,
        'Vinst YoY senaste kvartal':.12,
        'FCF YoY senaste kvartal':.08,
        'Kvalitet':78,'Risk':68,'INVEST Score':74,
        'Värdering':65,'1 mån':.05,'3 mån':.10,'Avstånd SMA200':.08,
    }, 'long')
    assert r['Operating leverage nivå'] == 3
    assert r['Operating leverage cost base verified'] is False


def test_margin_deterioration_blocks_signal():
    r=assess_operating_leverage_setup({
        'Omsättning YoY senaste kvartal':.15,
        'Omsättning acceleration':.06,
        'Marginal YoY förändring':-.04,
        'Vinst YoY senaste kvartal':-.25,
        'Kvalitet':75,'Risk':65,
    }, 'long')
    assert r['Operating leverage nivå'] == -1


def test_short_horizon_does_not_use_signal():
    r=assess_operating_leverage_setup({
        'Omsättning YoY senaste kvartal':.15,'Omsättning acceleration':.06,
        'Marginal YoY förändring':.01,'Vinst YoY senaste kvartal':.10,
        'Kvalitet':80,'Risk':70
    }, 'medium')
    assert r['Operating leverage nivå'] == 0


def test_app_and_ranking_wired():
    app=open('app.py',encoding='utf-8').read()
    rank=open('horizon_rankings.py',encoding='utf-8').read()
    ledger=open('recommendation_ledger.py',encoding='utf-8').read()
    assert 'APP_VERSION = "4.34.0"' in app
    assert 'Operating leverage' in app
    assert 'add_operating_leverage_setup(ranked, horizon)' in app
    assert "add_operating_leverage_setup(out, horizon)" in rank
    assert '"Deal Conviction Score"' in rank
    assert '"Operating leverage cost base verified"' in ledger
