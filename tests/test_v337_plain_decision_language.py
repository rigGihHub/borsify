from pathlib import Path

from decision_language import simplify_decision_text

APP = Path("app.py").read_text(encoding="utf-8")


def test_v337_version_and_presentation_layer_is_wired_in():
    assert 'APP_VERSION = "3.81.0"' in APP
    assert 'from decision_language import simplify_decision_text' in APP
    assert 'return simplify_decision_text(value)' in APP


def test_decision_language_translates_common_jargon_without_touching_numbers():
    text = simplify_decision_text(
        "Positiv inflektion; stark relativ styrka; estimatrevideringar förbättras; RSI 44."
    )
    low = text.lower()
    assert "inflektion" not in low
    assert "relativ styrka" not in low
    assert "estimatrevidering" not in low
    assert "rsi" not in low
    assert "utvecklingen har börjat förbättras" in low
    assert "marknaden" in low
    assert "vinstprognoser" in low
    assert "44" in text


def test_decision_language_is_compact_and_deterministic():
    raw = (
        "Fundamental katalysator med momentum och setup. "
        "Detta är en mycket lång intern förklaring som upprepas för att kontrollera att novice-vyn inte blir en vägg av text. " * 4
    )
    a = simplify_decision_text(raw, max_chars=180)
    b = simplify_decision_text(raw, max_chars=180)
    assert a == b
    assert len(a) <= 181
    assert "fundamental" not in a.lower()
    assert "katalysator" not in a.lower()
    assert "momentum" not in a.lower()
    assert "setup" not in a.lower()
