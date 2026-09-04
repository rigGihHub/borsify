from pathlib import Path

APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_266_or_newer():
    assert 'APP_VERSION = "2.65.0"' not in APP

def test_benchmark_variables_are_defined_before_market_note():
    note=APP.index('market_note = f" · {benchmark_name}')
    assert APP.index('benchmark_symbol = market_config.get("benchmark")') < note
    assert APP.index('benchmark_name = market_config.get("benchmark_name"') < note
    assert APP.index('idx = fetch_index_snapshot(benchmark_symbol)') < note

def test_analysis_page_also_has_benchmark_variables_in_scope():
    assert 'render_edge_lab(default_edge_symbol, list(symbols), benchmark_symbol, benchmark_name)' in APP

def test_plain_language_removes_hurdle_jargon_from_deep_card():
    assert "årlig avkastningshurdle" not in APP
    assert "vilken framtida vinsttillväxt dagens aktiepris verkar kräva" in APP
