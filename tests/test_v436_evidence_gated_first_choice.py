from pathlib import Path

import pandas as pd

from first_choice_gate import add_first_choice_gate, first_choice_blockers


ROOT = Path(__file__).resolve().parents[1]


def test_clean_case_can_be_first_choice():
    row = {
        "Value Trap verdict": "MARKET_WRONG",
        "Ingångsläge nivå": "green",
        "Bolagsbedömning nivå": "green",
        "Analysis Confidence nivå": 3,
    }
    assert first_choice_blockers(row) == []


def test_each_hard_risk_blocks_strong_first_choice():
    frame = pd.DataFrame([
        {"Ticker": "TRAP", "Value Trap verdict": "VALUE_TRAP", "Analysis Confidence nivå": 3},
        {"Ticker": "CHASE", "Ingångsläge nivå": "red", "Analysis Confidence nivå": 3},
        {"Ticker": "WEAK", "Bolagsbedömning nivå": "red", "Analysis Confidence nivå": 3},
        {"Ticker": "DATA", "Analysis Confidence nivå": 1},
    ])
    gated = add_first_choice_gate(frame)
    assert not gated["Förstaval godkänd"].any()
    assert gated["Förstaval blockerare"].str.len().gt(0).all()


def test_missing_confidence_is_not_misrepresented_as_low():
    # Missing evidence is handled by Analysis Confidence itself; the gate must not
    # silently invent a red level when the upstream field is absent.
    assert "lågt analysförtroende" not in first_choice_blockers({})


def test_app_uses_diverse_finalists_and_full_evidence_before_first_choice():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.36.0"' in app
    assert "build_discovery_pool(df, max_candidates=min(12, len(df)))" in app
    assert "finalists = add_full_deal_evidence(finalists, \"year\")" in app
    assert "finalists = add_first_choice_gate(finalists)" in app
    assert "EVIDENSGRANSKAT FÖRSTAVAL" in app
    assert "daily_shortlist, evidence_finalists = build_evidence_gated_shortlist" in app


def test_gate_does_not_change_borsify_score():
    frame = pd.DataFrame([{"Ticker": "A", "Borsify Score": 77.0, "Analysis Confidence nivå": 3}])
    gated = add_first_choice_gate(frame)
    assert gated.loc[0, "Borsify Score"] == 77.0
