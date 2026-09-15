from cash_conversion_inflection import assess_cash_conversion_inflection
def test_strong_cash_conversion_inflection():
    r=assess_cash_conversion_inflection({"FCF YoY senaste kvartal":.45,"FCF YoY föregående kvartal":.05,"Vinst YoY senaste kvartal":.15,"Vinst YoY föregående kvartal":.12,"FCF yield":.06,"Kvalitet":75,"Datatäckning":.8,"Ingångsläge nivå":"green"})
    assert r["Cash conversion inflection nivå"] == 3
def test_no_signal_when_fcf_does_not_accelerate():
    r=assess_cash_conversion_inflection({"FCF YoY senaste kvartal":.10,"FCF YoY föregående kvartal":.08,"Vinst YoY senaste kvartal":.10,"Vinst YoY föregående kvartal":.08})
    assert r["Cash conversion inflection nivå"] == 0
def test_deteriorating_fcf_blocks():
    r=assess_cash_conversion_inflection({"FCF YoY senaste kvartal":-.25,"FCF YoY föregående kvartal":.05,"Kvalitet":70})
    assert r["Cash conversion inflection nivå"] == -1
def test_app_and_ranking_wired():
    app=open("app.py",encoding="utf-8").read()
    rank=open("horizon_rankings.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.38.2"' in app
    assert "add_cash_conversion_inflection(ranked)" in app
    assert "add_cash_conversion_inflection(out)" in rank
    assert '"Deal Conviction Score"' in rank
