from pathlib import Path
import pandas as pd

from horizon_change_reasons import snapshot_details, explain_change, add_change_reasons

APP = Path("app.py").read_text(encoding="utf-8")
SCHEMA = Path("supabase_schema.sql").read_text(encoding="utf-8")


def test_snapshot_freezes_only_point_in_time_explanation_inputs():
    row = pd.Series({
        "Värdering": 71, "Kvalitet": 82, "Marknadsläge": 68, "Risk": 76,
        "Datatäckning": .88, "Relativ styrka": 63, "Case Readiness": 79,
        "För långt gången": False, "Signal": "KÖP NU", "framtid": 999,
    })
    snap = snapshot_details(row)
    assert snap["valuation"] == 71
    assert snap["signal"] == "KÖP NU"
    assert "framtid" not in snap


def test_strengthened_case_explains_actual_positive_component_changes():
    current = pd.Series({"Värdering": 72, "Kvalitet": 78, "Marknadsläge": 70, "Risk": 74,
                         "Datatäckning": .90, "Relativ styrka": 66, "Case Readiness": 80,
                         "För långt gången": False})
    previous = {"valuation": 64, "quality": 77, "setup": 63, "risk": 73,
                "coverage": .89, "relative_strength": 65, "case_readiness": 79, "overextended": False}
    text = explain_change(current, previous, "STÄRKT")
    assert "värderingen har blivit mer attraktiv" in text
    assert "marknadsläget och timingen har förbättrats" in text


def test_weakened_case_explains_actual_negative_component_changes():
    current = pd.Series({"Värdering": 64, "Kvalitet": 72, "Marknadsläge": 60, "Risk": 63,
                         "Datatäckning": .82, "Relativ styrka": 44, "Case Readiness": 68,
                         "För långt gången": False})
    previous = {"valuation": 70, "quality": 78, "setup": 69, "risk": 72,
                "coverage": .90, "relative_strength": 57, "case_readiness": 76, "overextended": False}
    text = explain_change(current, previous, "FÖRSVAGAD")
    assert any(x in text for x in ["riskprofilen har försämrats", "aktien går svagare jämfört med marknaden", "marknadsläget och timingen har försämrats"])


def test_missing_old_details_are_not_backfilled_from_today():
    current = pd.Series({"Ticker": "AAA", "Värdering": 90, "Förändring": "STÄRKT"})
    previous = pd.DataFrame([{"Ticker": "AAA", "Rank": 2, "Score": 70}])
    out = add_change_reasons(pd.DataFrame([current]), previous)
    assert "äldre analys saknar frysta delkomponenter" in out.iloc[0]["Vad har förändrats"]


def test_v344_wiring_is_explanatory_not_a_new_score():
    assert 'APP_VERSION = "3.73.0"' in APP
    assert 'from horizon_change_reasons import add_change_reasons, snapshot_details' in APP
    assert 'ranked = add_change_reasons(ranked, previous_horizon, horizon)' in APP
    assert '"Varför ändrad?"' in APP
    assert 'add column if not exists details jsonb' in SCHEMA
