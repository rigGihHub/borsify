import pandas as pd
from catalyst_engine import build_catalyst_assessment

NOW=pd.Timestamp("2026-09-03T10:00:00Z")

def test_fresh_external_headline_exposes_source_type():
    r=build_catalyst_assessment(
        {},
        {"news":[{
            "title":"Company wins new contract",
            "published_at":"2026-09-02T09:00:00Z",
            "provider":"Example News",
        }]},
        NOW,
    )
    assert r["Catalyst Evidence Type"]=="Daterad extern rubrik"
    assert r["Catalyst Source"]=="Example News"

def test_fundamental_inflection_exposes_internal_data_source():
    r=build_catalyst_assessment(
        {
            "Inflection Signal":"Positiv inflektion",
            "Inflection Confidence":80,
            "EPS-estimat förändring":.08,
        },
        {},
        NOW,
    )
    assert r["Catalyst Evidence Type"]=="Rapporterade siffror och estimat"
    assert r["Catalyst Source"]=="Bolagsdata/analytikerdata"

def test_missing_catalyst_source_stays_explicitly_missing():
    r=build_catalyst_assessment({}, {}, NOW)
    assert r["Catalyst Evidence Type"]=="För lite underlag"
    assert r["Catalyst Source"]=="—"
