import pandas as pd
from case_journal import assess_case_change, journal_table


def _history():
    return pd.DataFrame([
        {"score": 60, "valuation": 55, "quality": 60, "setup": 50, "income": 50, "risk": 65, "coverage": 90, "captured_date": "2026-08-01"},
        {"score": 64, "valuation": 58, "quality": 66, "setup": 51, "income": 50, "risk": 67, "coverage": 92, "captured_date": "2026-08-10"},
    ])


def test_case_strengthening_is_explained():
    current = {"score": 68, "valuation": 64, "quality": 71, "setup": 53, "income": 51, "risk": 68, "coverage": 94}
    out = assess_case_change(_history(), current, "2026-08-01")
    assert out["status"] == "Borsifys mätbild har stärkts"
    assert out["score_delta"] == 8
    assert any("Kvalitet" in x for x in out["changes"])
    assert any("Värdering" in x for x in out["changes"])


def test_small_change_is_not_overstated():
    current = {"score": 62, "valuation": 57, "quality": 63, "setup": 51, "income": 50, "risk": 64, "coverage": 91}
    out = assess_case_change(_history(), current)
    assert out["status"] == "Borsifys mätbild är ungefär oförändrad"


def test_journal_table_uses_first_snapshot_as_baseline():
    table = journal_table(_history())
    assert table.iloc[0]["Förändring från start"] == 0
    assert table.iloc[1]["Förändring från start"] == 4
