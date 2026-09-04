from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_268_or_newer():
    assert 'APP_VERSION = "2.67.0"' not in APP

def test_country_filter_is_first_class_and_uses_flags():
    assert 'selected_countries = st.multiselect(' in APP
    assert '"Land",' in APP
    assert 'format_func=lambda c: f"{_country_flag(c)} {c}"' in APP

def test_price_filter_is_in_sek():
    assert '"Pris från (SEK)"' in APP
    assert '"Pris till (SEK)"' in APP
    assert "Utländska aktiekurser räknas om till SEK." in APP

def test_country_filter_reduces_symbols_before_scan():
    scan=APP.index('with st.spinner(f"Borsify analyserar {len(scan_symbols)} aktier…")')
    country_filter=APP.index('if _market_label_for_ticker(sym) in set(selected_countries)')
    assert country_filter < scan

def test_old_cache_caption_is_fixed():
    assert "fundamenta 6 h" not in APP
    assert "bolagsdata upp till 24 h" in APP
