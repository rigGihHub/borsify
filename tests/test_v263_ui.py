from pathlib import Path
APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_263_or_newer():
    assert 'APP_VERSION = "2.62.0"' not in APP

def test_scan_performance_diagnostics_are_visible():
    assert "Bolagsdata denna körning:" in APP
    assert "24-timmarscache" in APP
    assert "kursdel" in APP
    assert "nya Yahoo-anrop" in APP

def test_scan_is_price_first():
    scan=APP[APP.index("def scan_universe"):APP.index("@st.cache_data(ttl=43200",APP.index("def scan_universe"))]
    assert scan.index("fetch_bulk_price_history") < scan.index("fetch_fundamentals")
    assert "prisdata stoppad före bolagsdata" in scan
