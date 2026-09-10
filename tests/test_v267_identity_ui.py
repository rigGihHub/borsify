from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_main_recommendation_views_use_stock_identity():
    assert '_stock_identity(first)' in APP
    assert 'table["Aktie"] = table.apply(_stock_identity, axis=1)' in APP

def test_why_now_is_present_on_primary_cards():
    assert 'st.markdown("**Varför nu?**")' in APP
