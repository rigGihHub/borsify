from catalyst_to_recognition import assess_catalyst_to_recognition

def base():
    return {
        "Market Blind Spot status":"CREDIBLE_BLIND_SPOT",
        "Market Blind Spot Score":82,
        "Early Mispricing status":"EARLY_MISPRICING",
        "Analysis Confidence Score":75,
        "1 mån":.05,"Relativ marknad 3 mån":.04,"Relativ sektor 3 mån":.03,
    }

def test_strong_path_requires_real_mechanisms():
    r=assess_catalyst_to_recognition({**base(),
        "Catalyst Independent Support":True,"Catalyst Strength":3,"Catalyst Confidence":85,
        "Primary Catalyst":"Rapport/resultat","Catalyst Timing":"inom en månad",
        "KPI Inflection nivå":2,"Revision breadth nivå":2})
    assert r["Catalyst-to-Recognition nivå"]==3

def test_blind_spot_without_mechanism_stays_weak():
    r=assess_catalyst_to_recognition(base())
    assert r["Catalyst-to-Recognition status"]=="NO_RECOGNITION_PATH"

def test_price_already_running_downgrades_path():
    r=assess_catalyst_to_recognition({**base(),
        "Catalyst Independent Support":True,"Catalyst Strength":3,
        "Primary Catalyst":"Rapport/resultat","Catalyst Timing":"inom en månad",
        "KPI Inflection nivå":2,"1 mån":.28})
    assert r["Catalyst-to-Recognition status"]=="RECOGNITION_IN_PROGRESS"

def test_low_confidence_blocks_strong_label():
    r=assess_catalyst_to_recognition({**base(),
        "Analysis Confidence Score":35,
        "Catalyst Independent Support":True,"Catalyst Strength":3,
        "Catalyst Confidence":90,"Primary Catalyst":"Rapport/resultat",
        "Catalyst Timing":"inom en månad","KPI Inflection nivå":2,"Revision breadth nivå":2})
    assert r["Catalyst-to-Recognition nivå"]==1

def test_no_mispricing_base_means_no_path():
    r=assess_catalyst_to_recognition({"Market Blind Spot status":"NO_MISPRICING_BASE"})
    assert r["Catalyst-to-Recognition nivå"]==0

def test_app_wires_signal_but_not_into_deal_conviction():
    app=open("app.py",encoding="utf-8").read()
    deal=open("deal_conviction.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.34.0"' in app
    assert "add_catalyst_to_recognition(ranked)" in app
    assert "Catalyst-to-Recognition" not in deal
