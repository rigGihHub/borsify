import json
import pandas as pd

from recommendation_ledger import build_recommendation_records, point_in_time_snapshot_summary


def test_long_ledger_v2_freezes_provenance_and_decision_inputs():
    frame = pd.DataFrame([{
        "Ticker": "AAA.ST", "Namn": "AAA", "Pris": 100.0, "Prisdatum": "2026-09-04",
        "Case Gate": "Toppcase", "INVEST Score": 78, "Case Confidence": 72,
        "Case Evidence Count": 4, "Fundamental Data status": "STARKT UNDERLAG",
        "Fundamental Data senaste rapportperiod": "2026-06-30",
        "EPS-estimat förändring": 0.08, "Analytiker antal": 7,
        "Analytikertäckning": "Användbar analytikertäckning",
        "Primary Catalyst": "Nästa rapport", "Catalyst Source": "Reuters",
        "Catalyst Source Quality": "Starkare källa", "Case Vetoes": "inga hårda motbevis i gate-modellen",
    }])
    rows = build_recommendation_records(
        frame, "long", "2.90.0", "Balanserad", "Sverige",
        captured_at=pd.Timestamp("2026-09-04T10:00:00Z"),
    )
    snap = json.loads(rows[0]["snapshot_json"])
    assert snap["PIT Schema Version"] == 3
    assert snap["PIT Model Version"] == "2.90.0"
    assert snap["PIT Captured At"] == "2026-09-04T10:00:00+00:00"
    assert snap["PIT Profile"] == "Balanserad"
    assert snap["PIT Market"] == "Sverige"
    assert snap["EPS-estimat förändring"] == 0.08
    assert snap["Analytiker antal"] == 7
    assert snap["Catalyst Source"] == "Reuters"
    assert snap["PIT Complete"] is True


def test_missing_point_in_time_fields_stay_missing_and_are_declared():
    frame = pd.DataFrame([{
        "Ticker": "AAA.ST", "Namn": "AAA", "Pris": 100.0,
        "Case Gate": "Bevaka", "INVEST Score": 62, "Case Confidence": 50,
    }])
    rows = build_recommendation_records(
        frame, "long", "2.90.0", "Balanserad", "Sverige",
        captured_at=pd.Timestamp("2026-09-04T10:00:00Z"),
    )
    snap = json.loads(rows[0]["snapshot_json"])
    assert snap["PIT Complete"] is False
    assert "Prisdatum" in snap["PIT Critical Missing"]
    assert "Fundamental Data status" in snap["PIT Critical Missing"]
    assert "Fundamental Data senaste rapportperiod" in snap["PIT Critical Missing"]
    assert "EPS-estimat förändring" not in snap  # never backfilled


def test_short_pit_summary_requires_decision_and_price_date():
    summary = point_in_time_snapshot_summary({
        "Ticker": "A", "Pris": 10, "Short Alpha Gate": "Kortsiktigt toppcase",
        "Short Alpha Score": 75, "Short Alpha Confidence": 80,
    }, "short")
    assert summary["complete"] is False
    assert summary["critical_missing"] == ["Prisdatum"]


def test_v290_ui_exposes_frozen_decision_audit():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "4.40.0"' in app
    assert "Vad visste Borsify när beslutet togs?" in app
    assert "Borsify fyller inte i saknade gamla uppgifter i efterhand" in app


def test_short_deep_stage_keeps_full_provenance_for_ledger():
    app = open("app.py", encoding="utf-8").read()
    assert "result.update(inflection)" in app
    assert "result.update(catalyst)" in app
    assert '"Catalyst Source"' in open("recommendation_ledger.py", encoding="utf-8").read()


def test_ledger_freezes_final_and_raw_borsify_scores_separately():
    frame = pd.DataFrame([{
        "Ticker": "INDU-C.ST", "Namn": "Industrivärden C", "Pris": 100.0,
        "Borsify Score": 68.0, "Borsify grundbetyg": 92.0,
        "Borsify slutbetyg": 68.0,
        "Case Gate": "Toppcase", "Case Confidence": 80,
        "Case Evidence Count": 4,
    }])
    rows = build_recommendation_records(
        frame, "long", "4.40.0", "Balanserad", "Sverige",
        captured_at=pd.Timestamp("2026-09-02T08:00:00Z"),
    )
    assert rows[0]["final_score"] == 68.0
    assert rows[0]["raw_borsify_score"] == 92.0
