from pathlib import Path

APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_267_or_newer():
    assert 'APP_VERSION = "2.66.0"' not in APP

def test_country_flag_helper_exists():
    assert 'def _country_flag(country: str) -> str:' in APP
    assert '"Sverige": "🇸🇪"' in APP
    assert '"USA": "🇺🇸"' in APP
    assert '"Storbritannien": "🇬🇧"' in APP

def test_stock_identity_always_includes_ticker_country_and_flag():
    assert 'def _stock_identity(' in APP
    assert 'return f"{flag} {name} · {ticker} · {country}"' in APP

def test_main_recommendation_views_use_stock_identity():
    assert 'st.markdown(f"### {rank}. {_stock_identity(row)}")' in APP
    assert 'st.markdown(f"### {_stock_identity(case)}")' in APP
    assert 's1.markdown(f"### {rank}. {_stock_identity(case)}")' in APP
    assert 'a.markdown(f"### {rank}. {_stock_identity(case)}")' in APP

def test_why_now_shows_source_type_when_available():
    assert 'st.caption(f"Underlag: {catalyst_type} · källa: {catalyst_source}")' in APP
