from business_management_intelligence import assess_business_management_intelligence

def test_software_profile_surfaces_missing_sector_kpis_instead_of_inventing():
    r=assess_business_management_intelligence({"Sektor":"Technology","Bransch":"Software","ROE":.20,"Vinstmarginal":.15})
    assert r["Business profile"]=="Mjukvara/tech"
    assert "NRR/churn" in r["Business key KPIs"]
    assert "NRR/churn" in r["Business KPI gaps"]
    assert "saknas" in r["Business KPI coverage"]

def test_industrial_profile_calls_out_order_book():
    r=assess_business_management_intelligence({"Sektor":"Industrials","Bransch":"Machinery"})
    assert r["Business profile"]=="Industri"
    assert "orderingång/orderbok" in r["Business key KPIs"]

def test_management_execution_uses_observed_evidence_only():
    r=assess_business_management_intelligence({
        "Report Delta guidance":"Bolaget har höjt guidningen",
        "Report Delta positiva":4,"Report Delta negativa":0,
        "Kapitalallokering återköpsyield":.02,
        "Kapitalallokering skuldtrend":-.15,
    })
    assert r["Management execution nivå"]==2
    assert "VD-kvalitet" in r["Management execution förklaring"]

def test_negative_execution_is_not_explained_away():
    r=assess_business_management_intelligence({
        "Report Delta guidance":"cuts guidance after profit warning",
        "Report Delta positiva":0,"Report Delta negativa":3,
        "Kapitalallokering emissionsyield":.05,
        "Kapitalallokering skuldtrend":.30,
    })
    assert r["Management execution nivå"]==-1

def test_app_wires_engine_but_does_not_add_it_to_deal_conviction():
    app=open("app.py",encoding="utf-8").read()
    deal=open("deal_conviction.py",encoding="utf-8").read()
    ledger=open("recommendation_ledger.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.38.2"' in app
    assert "add_business_management_intelligence(ranked)" in app
    assert "Verksamhet & ledning" in app
    assert "Management execution nivå" not in deal
    assert '"Management execution förklaring"' in ledger
