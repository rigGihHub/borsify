from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from scan_snapshot_cache import clear_scan_snapshots, get_scan_snapshot, put_scan_snapshot, symbol_set_key


ROOT = Path(__file__).resolve().parents[1]


def _frame():
    history = pd.DataFrame(
        {"Close": [100.0, 101.0], "Volume": [1000, 1200]},
        index=pd.to_datetime(["2026-09-11", "2026-09-12"]),
    )
    return pd.DataFrame([{"Ticker": "AAA.ST", "Pris": 101.0, "_history": history}])


def test_snapshot_roundtrip_preserves_history(tmp_path):
    db = tmp_path / "borsify.db"
    assert put_scan_snapshot(db, ["AAA.ST"], _frame())["saved"] is True
    restored, meta = get_scan_snapshot(db, ["AAA.ST"])
    assert meta["hit"] is True
    assert restored.iloc[0]["Ticker"] == "AAA.ST"
    assert isinstance(restored.iloc[0]["_history"], pd.DataFrame)
    assert restored.iloc[0]["_history"]["Close"].tolist() == [100, 101]


def test_symbol_key_is_order_independent_but_exact():
    assert symbol_set_key(["BBB", "AAA"]) == symbol_set_key(["aaa", "bbb", "AAA"])
    assert symbol_set_key(["AAA"]) != symbol_set_key(["AAA", "BBB"])


def test_stale_snapshot_is_not_used(tmp_path):
    db = tmp_path / "borsify.db"
    saved = put_scan_snapshot(db, ["AAA.ST"], _frame())
    future = datetime.fromisoformat(saved["captured_at"]) + timedelta(minutes=121)
    restored, meta = get_scan_snapshot(db, ["AAA.ST"], now=future)
    assert restored.empty
    assert meta["reason"] == "stale"


def test_manual_clear_removes_snapshot(tmp_path):
    db = tmp_path / "borsify.db"
    put_scan_snapshot(db, ["AAA.ST"], _frame())
    assert clear_scan_snapshots(db) == 1
    assert get_scan_snapshot(db, ["AAA.ST"])[0].empty


def test_app_wires_fast_resume_without_prefiltering():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.38.2"' in app
    assert "get_scan_snapshot(DB_PATH, scan_symbols, max_age_minutes=120)" in app
    assert "put_scan_snapshot(DB_PATH, scan_symbols, raw_df)" in app
    assert "clear_scan_snapshots(DB_PATH)" in app
    assert "Bolagsdata {completed}/{denominator}" in app
    assert "head(80)" not in app[app.index("raw_df, scan_snapshot"):app.index("if raw_df.empty", app.index("raw_df, scan_snapshot"))]
