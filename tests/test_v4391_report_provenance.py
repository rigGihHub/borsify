from pathlib import Path

from report_delta_engine import build_report_delta
from report_verification import report_data_provenance
from recommendation_ledger import snapshot_columns


ROOT = Path(__file__).resolve().parents[1]


def test_report_delta_provenance_marks_unverified_original_report_text():
    raw = {"source_health": {"source": "Yahoo Finance via yfinance"}}
    provenance = report_data_provenance(raw)
    assert provenance["Rapport läst"] is False
    assert provenance["Rapport text verifierad"] is False
    assert provenance["Rapport primärkälla verifierad"] is False
    assert "ingen verifierad primär rapporttext" in provenance["Report Delta datagrund"].lower()


def test_report_delta_calculation_remains_separate_from_report_provenance():
    delta = build_report_delta(
        {
            "Senaste EPS-överraskning": 0.08,
            "Omsättning acceleration": 0.06,
            "Marginal YoY förändring": 0.03,
            "FCF YoY senaste kvartal": 0.20,
        },
        {"Post-report dagar sedan": 8, "Post-report reaktion": 0.01},
    )
    assert delta["Report Delta kandidat"] is True
    assert "Rapport läst" not in delta


def test_app_wires_report_provenance_into_all_report_delta_paths():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.39.1"' in app
    assert "from report_verification import report_data_provenance" in app
    assert app.count("build_report_delta_with_provenance(") == 4
    assert "Originalrapporten markeras bara som verifierad" in app


def test_point_in_time_ledger_freezes_report_provenance():
    cols = snapshot_columns("long")
    assert "Report Delta datagrund" in cols
    assert "Rapport text verifierad" in cols
    assert "Rapport kontroll" in cols
