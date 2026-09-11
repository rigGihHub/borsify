import pandas as pd

from relationship_data_builder import (
    build_relationship_registry,
    relationship_registry_health,
    validate_relationship_record,
)
from verified_relationship_engine import load_verified_relationships


def _row(**updates):
    row = {
        "source_ticker": "INVE-B.ST",
        "target_ticker": "ATCO-A.ST",
        "relationship_type": "ownership",
        "direction": "two_sided",
        "evidence_label": "Investor AB lists Atlas Copco as a listed holding",
        "source_url": "https://www.investorab.com/",
        "source_date": "2026-09-09",
        "verified_at": "2026-09-09",
        "active": "true",
        "source_kind": "company_portfolio_page",
        "source_title": "Investor AB portfolio",
        "relationship_note": "",
    }
    row.update(updates)
    return row


def test_builder_requires_primary_source_and_https():
    ok, errors, _ = validate_relationship_record(
        _row(source_kind="media", source_url="http://example.com"), as_of="2026-09-09"
    )
    assert not ok
    assert "non_primary_or_missing_source_kind" in errors
    assert "source_must_be_https" in errors


def test_builder_rejects_future_or_inverted_dates():
    ok, errors, _ = validate_relationship_record(
        _row(source_date="2026-09-10", verified_at="2026-09-11"), as_of="2026-09-09"
    )
    assert not ok
    assert "verification_in_future" in errors

    ok2, errors2, _ = validate_relationship_record(
        _row(source_date="2026-09-10", verified_at="2026-09-09"), as_of="2026-09-09"
    )
    assert not ok2
    assert "source_after_verification" in errors2


def test_builder_deduplicates_same_directed_relationship_by_latest_verification():
    older = _row(source_date="2026-09-08", verified_at="2026-09-08", evidence_label="Older primary-source verification")
    newer = _row(verified_at="2026-09-09", evidence_label="Newer primary-source verification")
    reg, rejected = build_relationship_registry([older, newer], as_of="2026-09-09")
    assert rejected.empty
    assert len(reg) == 1
    assert reg.iloc[0]["evidence_label"] == "Newer primary-source verification"


def test_registry_health_is_transparent_and_score_free():
    reg, _ = build_relationship_registry([_row()], as_of="2026-09-09")
    h = relationship_registry_health(reg, as_of="2026-09-09")
    assert h["relations"] == 1
    assert h["source_companies"] == 1
    assert h["target_companies"] == 1
    assert h["primary_source_share"] == 1.0
    assert not any("score" in k.casefold() for k in h)


def test_seed_registry_has_real_primary_source_coverage_and_valid_tickers():
    reg = load_verified_relationships()
    assert len(reg) >= 20
    assert {"INVE-B.ST", "INDU-C.ST"}.issubset(set(reg["source_ticker"]))
    assert reg["source_url"].str.startswith("https://").all()
    universe = set(pd.read_csv("avanza_universe.csv")["Ticker"].astype(str))
    assert set(reg["source_ticker"]).issubset(universe)
    assert set(reg["target_ticker"]).issubset(universe)


def test_v361_version_and_advanced_coverage_ui_are_wired():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "relationship_registry_health" in app
    assert "Relationsdatabas – täckning och källkvalitet" in app
    assert "Relationship Score" not in open("relationship_data_builder.py", encoding="utf-8").read()
