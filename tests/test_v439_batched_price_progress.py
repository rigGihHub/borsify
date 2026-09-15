from pathlib import Path

from price_batching import partial_fallback_symbols, symbol_batches


ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")


def test_symbol_batches_are_stable_bounded_and_deduplicated():
    symbols = [f"S{i}" for i in range(83)] + ["S1"]
    batches = symbol_batches(symbols, batch_size=40)
    assert [len(batch) for batch in batches] == [40, 40, 3]
    assert [symbol for batch in batches for symbol in batch] == symbols[:-1]


def test_empty_multi_symbol_batch_does_not_fan_out_to_single_requests():
    assert partial_fallback_symbols(("A", "B", "C"), {}, max_fallbacks=8) == []
    assert partial_fallback_symbols(("A",), {}, max_fallbacks=8) == ["A"]


def test_partial_batch_fallback_is_bounded_and_only_targets_missing_symbols():
    batch = tuple(f"S{i}" for i in range(20))
    selected = partial_fallback_symbols(batch, {"S0": object(), "S2": object()}, max_fallbacks=4)
    assert selected == ["S1", "S3", "S4", "S5"]


def test_scan_updates_price_progress_per_completed_batch():
    scan = APP[APP.index("def scan_universe"):APP.index("@st.cache_data(ttl=43200", APP.index("def scan_universe"))]
    assert "for batch in symbol_batches(symbols, batch_size=40)" in scan
    assert 'progress_callback("prices", completed_prices, len(symbols))' in scan
    assert "fetch_bulk_price_history(tuple(symbols))" not in scan


def test_release_version_is_4390():
    assert 'APP_VERSION = "4.39.0"' in APP
