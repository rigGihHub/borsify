from pathlib import Path
import pandas as pd
from management_signal_layer import build_management_signal, select_management_signal_candidates

ROOT = Path(__file__).resolve().parents[1]

def _events(*titles):
    return {"news": [{"title": t, "provider": "Example"} for t in titles]}

def test_requires_explicit_management_attribution_and_concrete_topics():
    out = build_management_signal(_events(
        "Company sees improving demand and stronger margins",
        "CEO says demand is improving as margins expand",
    ))
    assert out["Ledningssignal positiva"] == 1  # first unattributed title ignored; one headline counts one topic
    assert out["Ledningssignal kandidat"] is False

def test_two_independent_positive_topics_can_open_candidate_door():
    out = build_management_signal(_events(
        "CEO says demand is improving",
        "CFO says margins expand as costs normalize",
    ))
    assert out["Ledningssignal positiva"] == 2
    assert out["Ledningssignal kandidat"] is True
    assert out["Ledningssignal varning"] is False
    assert "score" not in " ".join(out.keys()).lower()

def test_negative_management_language_blocks_positive_candidate():
    out = build_management_signal(_events(
        "CEO says demand is improving",
        "CFO says margin pressure remains",
        "CEO says order book grows",
    ))
    assert out["Ledningssignal positiva"] >= 2
    assert out["Ledningssignal negativa"] >= 1
    assert out["Ledningssignal kandidat"] is False
    assert out["Ledningssignal varning"] is True

def test_generic_optimism_is_ignored():
    out = build_management_signal(_events("CEO says we are very optimistic about the future"))
    assert out["Ledningssignal jämförbara"] == 0
    assert out["Ledningssignal kandidat"] is False

def test_selector_is_deterministic():
    df = pd.DataFrame({
        "Ticker": ["BBB.ST", "AAA.ST", "CCC.ST"],
        "Ledningssignal kandidat": [True, True, True],
        "Ledningssignal stark": [False, True, True],
        "Ledningssignal positiva": [2, 3, 3],
        "Ledningssignal negativa": [0, 0, 0],
    }, index=[1,2,3])
    assert select_management_signal_candidates(df, quota=1) == [(2, "Ledningssignal")]

def test_version_ui_selection_and_pit_wiring():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    finalist=(ROOT/'finalist_selection.py').read_text(encoding='utf-8')
    ledger=(ROOT/'recommendation_ledger.py').read_text(encoding='utf-8')
    assert 'APP_VERSION = "3.73.0"' in app
    assert 'build_management_signal' in app
    assert 'bq_management_signal_radar' in app
    assert 'select_management_signal_candidates' in finalist
    assert 'reason_keys[idx] = "management_signal"' in finalist
    assert '"Ledningssignal status"' in ledger
