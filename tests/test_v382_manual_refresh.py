import sqlite3
from pathlib import Path

from fundamental_cache import put_cached_fundamentals, get_cached_fundamentals, clear_fundamentals_cache


def test_clear_fundamentals_cache_forces_persistent_refresh(tmp_path):
    db = tmp_path / "borsify.db"
    put_cached_fundamentals(db, "VOLV-B.ST", {"Namn": "Volvo"})
    assert get_cached_fundamentals(db, "VOLV-B.ST") is not None
    assert clear_fundamentals_cache(db) == 1
    assert get_cached_fundamentals(db, "VOLV-B.ST") is None


def test_manual_refresh_is_primary_and_clears_both_caches():
    app = Path("app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.37.0"' in app
    assert 'st.button("↻ Uppdatera data", type="primary"' in app
    assert "st.cache_data.clear()" in app
    assert "clear_fundamentals_cache(DB_PATH)" in app
    assert 'bq_last_manual_refresh_completed' in app
    assert 'Färsk data' in app and 'Delvis färsk' in app and 'Gammal data' in app


def test_refresh_does_not_delete_research_or_pit_history():
    app = Path("app.py").read_text(encoding="utf-8")
    refresh_block = app[app.index('if refresh:', app.index('key="manual_refresh_top"')):app.index('with st.sidebar:', app.index('key="manual_refresh_top"'))]
    forbidden = ["DELETE FROM recommendation", "DELETE FROM consensus", "DELETE FROM report", "unlink", "rmtree"]
    assert not any(x in refresh_block for x in forbidden)
