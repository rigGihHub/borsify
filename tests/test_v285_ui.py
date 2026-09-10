from pathlib import Path

APP = Path("app.py").read_text(encoding="utf-8")


def test_v285_ui_exposes_false_negative_learning_without_auto_retuning():
    assert 'APP_VERSION = "3.73.0"' in APP
    assert 'Vad missade Borsify?' in APP
    assert 'false_negative_analysis(recs, outs, chosen_h)' in APP
    assert 'ändrar inte köpmodellen' in APP
