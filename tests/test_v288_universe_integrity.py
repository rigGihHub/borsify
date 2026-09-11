from pathlib import Path
import pandas as pd
from market_universe import audit_catalog, catalog_integrity_summary, load_avanza_universe, universe_symbols

ROOT = Path(__file__).resolve().parents[1]


def test_current_catalog_passes_local_integrity_gate():
    audit = audit_catalog(ROOT / "avanza_universe.csv")
    summary = catalog_integrity_summary(audit)
    assert summary["total"] >= 500
    assert summary["approved"] == summary["total"]
    assert summary["excluded"] == 0
    assert summary["countries"] == 15


def test_duplicate_ticker_is_rejected_before_provider_call():
    df = pd.DataFrame([
        {"Ticker": "VOLV-B.ST", "Land": "Sverige", "Nivå": "Kärna"},
        {"Ticker": "VOLV-B.ST", "Land": "Sverige", "Nivå": "Bred"},
    ])
    audit = audit_catalog(df)
    assert set(audit["Katalog QC"]) == {"EXKLUDERA"}
    assert audit["Katalogproblem"].str.contains("duplicerad ticker").all()


def test_country_suffix_conflict_is_rejected():
    df = pd.DataFrame([{"Ticker": "NOVO-B.ST", "Land": "Danmark", "Nivå": "Kärna"}])
    audit = audit_catalog(df)
    assert audit.iloc[0]["Katalog QC"] == "EXKLUDERA"
    assert "suffix" in audit.iloc[0]["Katalogproblem"]


def test_unknown_tier_is_rejected():
    df = pd.DataFrame([{"Ticker": "AAPL", "Land": "USA", "Nivå": "Mega"}])
    audit = audit_catalog(df)
    assert audit.iloc[0]["Katalog QC"] == "EXKLUDERA"
    assert "universumnivå" in audit.iloc[0]["Katalogproblem"]


def test_loader_exposes_only_approved_catalog_rows(tmp_path):
    p = tmp_path / "catalog.csv"
    pd.DataFrame([
        {"Ticker": "AAPL", "Land": "USA", "Nivå": "Kärna"},
        {"Ticker": "BAD.ST", "Land": "Danmark", "Nivå": "Bred"},
    ]).to_csv(p, index=False)
    loaded = load_avanza_universe(p)
    assert loaded["Ticker"].tolist() == ["AAPL"]
    assert universe_symbols(loaded, ["USA"], broad=True) == ["AAPL"]


def test_app_surfaces_catalog_integrity_without_claiming_provider_verification():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "3.81.0"' in app
    assert "Katalogkontrollen bevisar inte att aktien handlas" in app
    assert "stoppades före datahämtning" in app
