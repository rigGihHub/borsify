import pandas as pd

from finalist_selection import select_deep_finalist_pool
from recommendation_ledger import snapshot_columns
from report_delta_engine import build_report_delta, select_report_delta_candidates


def _metrics(**overrides):
    base = {
        "Senaste EPS-överraskning": 0.08,
        "Omsättning YoY senaste kvartal": 0.12,
        "Omsättning acceleration": 0.05,
        "Marginal YoY förändring": 0.02,
        "FCF YoY senaste kvartal": 0.22,
        "Vinst YoY senaste kvartal": 0.18,
        "EPS-estimat förändring": 0.03,
        "EPS-revisionsbalans": 0.50,
        "Estimat tillförlitlighetsvikt": 0.75,
    }
    base.update(overrides)
    return base


def _post(reaction=0.01, days=8):
    return {
        "Post-report dagar sedan": days,
        "Post-report reaktion": reaction,
        "Post-report fortsatt rörelse": 0.02,
    }


def test_broad_positive_report_with_muted_reaction_becomes_candidate():
    result = build_report_delta(_metrics(), _post())
    assert result["Report Delta kandidat"] is True
    assert result["Report Delta underreaktion"] is True
    assert result["Report Delta positiva"] >= 4
    assert "liten kursreaktion" in result["Report Delta status"]


def test_missing_report_evidence_is_not_inferred_into_candidate():
    result = build_report_delta({}, _post())
    assert result["Report Delta kandidat"] is False
    assert result["Report Delta evidens"] == 0
    assert result["Report Delta status"] == "För lite rapportdelta-data"


def test_clear_negative_price_reaction_blocks_discovery_advantage():
    result = build_report_delta(_metrics(), _post(reaction=-0.07))
    assert result["Report Delta kandidat"] is False
    assert result["Report Delta underreaktion"] is False
    assert "marknaden säger emot" in result["Report Delta status"]


def test_only_explicit_guidance_language_counts_as_guidance_change():
    explicit = {"news": [{"title": "Bolaget höjer prognos efter stark rapport"}]}
    generic = {"news": [{"title": "VD är optimistisk efter kvartalet"}]}
    pos = build_report_delta(_metrics(), _post(), explicit)
    neutral = build_report_delta(_metrics(), _post(), generic)
    assert any("höjt guidningen" in x for x in pos["Report Delta styrkor"])
    assert neutral["Report Delta guidance"] == "Ingen explicit guidningsförändring verifierad"


def test_report_delta_gets_single_fresh_change_doorway_after_two_incumbents():
    rows = []
    for ticker, invest, report_candidate in [("AAA.ST", 90, False), ("BBB.ST", 88, False), ("CCC.ST", 50, True), ("DDD.ST", 70, False)]:
        rows.append({
            "Ticker": ticker, "INVEST Score": invest, "Datatäckning": 80,
            "Daytrade Score": 50, "Mellan Score": 50, "Lång Score": 50, "Livstid Score": 50,
            "Kvalitet": 50, "Värdering": 50, "REVERSAL Score": 50,
            "Report Delta kandidat": report_candidate, "Report Delta underreaktion": report_candidate,
            "Report Delta positiva": 5 if report_candidate else 0,
            "Report Delta negativa": 0, "Report Delta evidens": 6 if report_candidate else 0,
        })
    result = select_deep_finalist_pool(pd.DataFrame(rows), pool_size=3)
    assert result["Ticker"].tolist() == ["AAA.ST", "BBB.ST", "CCC.ST"]
    assert result.iloc[2]["Djupurval Nyckel"] == "report_delta"


def test_report_delta_fields_are_frozen_in_point_in_time_ledger_schema():
    cols = snapshot_columns("long")
    assert "Report Delta status" in cols
    assert "Report Delta kandidat" in cols
    assert "Report Delta kursreaktion" in cols


def test_v355_is_wired_into_app():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.73.0"' in app
    assert "build_report_delta" in app
    assert "Vad förändrades i senaste rapporten?" in app
