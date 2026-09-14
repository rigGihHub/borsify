from kpi_inflection import assess_kpi_inflection

def test_generic_improvement_is_not_called_leading_sector_inflection():
    r=assess_kpi_inflection({"Business profile":"Industri","KPI Omsättning QoQ":.12,"KPI FCF QoQ":.25,
                              "KPI-specifika saknas":"orderingång/orderbok; pris/mix"})
    assert r["KPI Inflection nivå"]==2
    assert r["KPI Inflection ledande KPI observerad"] is False

def test_observed_leading_kpi_can_create_strong_inflection():
    r=assess_kpi_inflection({"Business profile":"Industri","KPI Omsättning QoQ":.10,
                              "KPI-specifika observerade":"orderingång/orderbok"})
    assert r["KPI Inflection nivå"]==3

def test_retail_inventory_running_ahead_of_sales_is_warning():
    r=assess_kpi_inflection({"Business profile":"Retail/konsument","KPI Omsättning QoQ":.02,"KPI Lager QoQ":.20})
    assert "lagret växer" in r["KPI Inflection varningar"]

def test_missing_leading_kpis_are_explicit_in_explanation():
    r=assess_kpi_inflection({"Business profile":"Mjukvara/tech","KPI Omsättning QoQ":.10,
                              "KPI-specifika saknas":"ARR/återkommande intäkter; NRR/churn"})
    assert "NRR/churn" in r["KPI Inflection förklaring"]

def test_app_wires_kpi_inflection_but_deal_conviction_does_not_weight_it_yet():
    app=open("app.py",encoding="utf-8").read(); deal=open("deal_conviction.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.35.0"' in app
    assert "assess_kpi_inflection" in app
    assert "KPI Inflection nivå" not in deal
