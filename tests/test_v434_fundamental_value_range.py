from pathlib import Path

from fundamental_value_range import build_fundamental_value_range


ROOT = Path(__file__).resolve().parents[1]


def _scenario(confidence=72):
    return {
        "status": "OK",
        "confidence": confidence,
        "current_price": 100.0,
        "horizon_years": 5,
        "bear": {"future_price": 80.0},
        "base": {"future_price": 140.0},
        "bull": {"future_price": 220.0},
    }


def test_supported_case_returns_coarse_ranges_without_ranking_effect():
    result = build_fundamental_value_range(
        {"Sektor": "Industrials", "FCF-yield": 0.05, "Valuta": "SEK"}, _scenario()
    )
    assert result["Fundamental Value Range status"] == "SUPPORTED"
    assert result["Fundamental Value Range base low"] < result["Fundamental Value Range base high"]
    assert result["Fundamental Value Range ranking effect"] == "NONE"
    assert "utspädning" in result["Fundamental Value Range warnings"].lower()


def test_sector_specific_models_are_not_faked():
    for sector in ("Financial Services", "Real Estate"):
        result = build_fundamental_value_range({"Sektor": sector, "FCF-yield": 0.05}, _scenario())
        assert result["Fundamental Value Range status"] == "UNSUPPORTED_MODEL"
        assert result["Fundamental Value Range ranking effect"] == "NONE"


def test_missing_or_negative_fcf_never_counts_as_confirmation():
    missing = build_fundamental_value_range({"Sektor": "Industrials"}, _scenario())
    negative = build_fundamental_value_range({"Sektor": "Industrials", "FCF-yield": -0.01}, _scenario())
    assert missing["Fundamental Value Range status"] == "FCF_NOT_CONFIRMED"
    assert negative["Fundamental Value Range status"] == "FCF_NOT_CONFIRMED"


def test_low_scenario_confidence_blocks_the_range():
    result = build_fundamental_value_range(
        {"Sektor": "Technology", "FCF-yield": 0.04}, _scenario(confidence=42)
    )
    assert result["Fundamental Value Range status"] == "LOW_CONFIDENCE"


def test_high_debt_reduces_confidence_but_does_not_double_count_debt_in_value():
    normal = build_fundamental_value_range(
        {"Sektor": "Industrials", "FCF-yield": 0.05, "Skuld/eget kapital": 80}, _scenario()
    )
    indebted = build_fundamental_value_range(
        {"Sektor": "Industrials", "FCF-yield": 0.05, "Skuld/eget kapital": 250}, _scenario()
    )
    assert indebted["Fundamental Value Range confidence"] == normal["Fundamental Value Range confidence"] - 10
    assert indebted["Fundamental Value Range base low"] == normal["Fundamental Value Range base low"]
    assert "skuld" in indebted["Fundamental Value Range warnings"].lower()


def test_version_and_integration_are_explicit():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    ledger = (ROOT / "recommendation_ledger.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.35.0"' in app
    assert "build_fundamental_value_range" in app
    assert "Fundamental Value Range ranking effect" in ledger
    assert "Påverkar inte Borsify Score eller huvudrankingen" in app
