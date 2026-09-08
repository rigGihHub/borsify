from pathlib import Path
import pandas as pd
from market_universe import audit_catalog, load_avanza_universe, breadth_summary

ROOT = Path(__file__).resolve().parents[1]


def test_expanded_catalog_is_materially_larger_but_still_clean():
    audit = audit_catalog(ROOT / "avanza_universe.csv")
    assert len(audit) >= 750
    assert audit["Katalog QC"].eq("GODKÄND").all()
    assert audit["Ticker"].is_unique


def test_expansion_preserves_core_and_adds_broad_candidates():
    df = load_avanza_universe(ROOT / "avanza_universe.csv")
    s = breadth_summary(df)
    assert s["countries"] == 15
    assert s["total"] >= 750
    assert s["core"] >= 300
    assert s["extended"] >= 350


def test_us_expansion_contains_additional_large_and_mid_cap_candidates():
    df = pd.read_csv(ROOT / "avanza_universe.csv")
    us = df[df["Land"].eq("USA")]
    assert len(us) >= 300
    for ticker in ["TSLA", "MRK", "LIN", "WFC", "PLD", "SHW", "ANET", "VRTX"]:
        row = us[us["Ticker"].eq(ticker)]
        assert len(row) == 1
        assert row.iloc[0]["Nivå"] == "Bred"


def test_release_version_is_289():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "3.38.0"' in app
