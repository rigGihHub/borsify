from analysis_confidence import assess_analysis_confidence

def test_high_confidence_requires_good_data_not_high_stock_score():
    r=assess_analysis_confidence({
        "Datatäckning":.95,
        "Fundamental source status":"OK",
        "Deep source status":"OK",
        "KPI strukturerad täckning":3,
        "Deep Confidence":90,
        "Deal Conviction oberoende familjer":4,
        "Data Failure penalty":0,
    })
    assert r["Analysis Confidence Score"]>=80
    assert "Mycket högt" in r["Analysis Confidence"]

def test_open_circuit_blocks_high_confidence():
    r=assess_analysis_confidence({
        "Datatäckning":.95,
        "Fundamental source status":"OK",
        "Deep source status":"OK",
        "Fundamental circuit open":True,
        "KPI strukturerad täckning":3,
        "Deep Confidence":90,
        "Deal Conviction oberoende familjer":4,
    })
    assert "öppen circuit breaker" in r["Analysis Confidence blockerare"]
    assert r["Analysis Confidence nivå"]<4

def test_missing_sector_kpis_reduce_confidence():
    base={
        "Datatäckning":.9,"Fundamental source status":"OK","Deep source status":"OK",
        "Deep Confidence":80,"Deal Conviction oberoende familjer":3,
    }
    a=assess_analysis_confidence({**base,"KPI strukturerad täckning":3})
    b=assess_analysis_confidence({**base,"KPI strukturerad täckning":0,"Business KPI gaps":"NRR/churn; ARR"})
    assert a["Analysis Confidence Score"]>b["Analysis Confidence Score"]

def test_analysis_confidence_is_not_in_deal_conviction():
    deal=open("deal_conviction.py",encoding="utf-8").read()
    assert "Analysis Confidence" not in deal

def test_app_exposes_confidence_and_version():
    app=open("app.py",encoding="utf-8").read()
    ledger=open("recommendation_ledger.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.2"' in app
    assert "assess_analysis_confidence" in app
    assert '"Analysis Confidence Score"' in ledger
