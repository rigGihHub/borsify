from pathlib import Path

APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_world_market_explanation_is_plain_language():
    assert "fonden VT, som äger aktier från många olika länder" in APP
    assert "praktisk proxy för en bred världsmarknad" not in APP

def test_toplist_does_not_explain_momentum_with_momentum():
    assert "Mycket kort horisont. Momentum" not in APP
    assert "hur kursen gått de senaste 1–3 månaderna" in APP

def test_visible_data_stamp_uses_bolagsdata():
    assert "bolagsdata hämtad" in APP
