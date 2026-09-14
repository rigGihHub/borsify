import pandas as pd
from negative_overreaction import assess_negative_overreaction, add_negative_overreaction


def test_strong_quality_positive_report_and_selloff_is_candidate():
    r=assess_negative_overreaction({
        "Kvalitet":82,"Risk":72,"Värdering":74,
        "Dagsförändring":-.07,"1 mån":-.15,"52v från topp":-.28,
        "Report Delta status":"Stark rapport men marknaden säger emot",
        "Report Delta positiva":4,"Report Delta negativa":0,"Report Delta kursreaktion":-.08,
        "Konsensusminne positiv":True,"Konsensusminne negativ":False,
        "Förändringsbekräftelse kandidat":True,"Förändringsbekräftelse negativa familjer":"",
        "Riktkurs potential":.22,
    })
    assert r["Negativ överreaktion nivå"] >= 2
    assert r["Fallande kniv varning"] is False


def test_negative_fundamentals_turn_selloff_into_falling_knife():
    r=assess_negative_overreaction({
        "Kvalitet":78,"Risk":66,"Dagsförändring":-.09,"1 mån":-.18,
        "Report Delta status":"Bred negativ rapportförändring",
        "Report Delta positiva":1,"Report Delta negativa":3,
        "Konsensusminne negativ":True,
    })
    assert r["Negativ överreaktion nivå"] == -1
    assert r["Fallande kniv varning"] is True
    assert "fallande kniv" in r["Negativ överreaktion"].lower()


def test_no_selloff_means_no_overreaction_even_for_great_company():
    r=assess_negative_overreaction({
        "Kvalitet":90,"Risk":80,"Värdering":80,"1 mån":.04,"Dagsförändring":.01,
        "Report Delta positiva":4,"Report Delta negativa":0,
    })
    assert r["Negativ överreaktion nivå"] == 0


def test_dataframe_layer_preserves_rows_and_adds_fields():
    df=pd.DataFrame([{"Ticker":"A","Kvalitet":80,"Risk":70,"1 mån":-.15}])
    out=add_negative_overreaction(df)
    assert list(out["Ticker"]) == ["A"]
    assert "Negativ överreaktion" in out.columns


def test_release_ui_and_ranking_wiring():
    app=open("app.py",encoding="utf-8").read()
    rankings=open("horizon_rankings.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.34.1"' in app
    assert "Quality on sale – negativ överreaktion" in app
    assert '"Negativ överreaktion"' in app
    assert "add_negative_overreaction(out)" in rankings
    assert '"Deal Conviction Score"' in rankings
