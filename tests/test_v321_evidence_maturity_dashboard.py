import pandas as pd
import evidence_maturity_dashboard as em


def test_summary_empty_waits():
    out = em.build_evidence_maturity_dashboard(pd.DataFrame(), pd.DataFrame())
    summary = em.evidence_maturity_summary(out)
    assert summary["status"] == "Vänta"
    assert summary["review_ready"] == 0


def test_summary_distinguishes_prospective_from_review():
    table = pd.DataFrame([
        {"Evidensnivå": em.LEVEL_PROSPECTIVE},
        {"Evidensnivå": em.LEVEL_HISTORICAL},
    ])
    summary = em.evidence_maturity_summary(table)
    assert summary["status"] == "Prospektiv"
    assert summary["prospective"] == 1


def test_dashboard_language_never_auto_promotes():
    src = open("evidence_maturity_dashboard.py", encoding="utf-8").read().lower()
    assert "never changes scores" in src
    assert "manuell" in src
    assert "automatisk" in src


def test_v321_ui_and_version():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.73.0"' in app
    assert "Evidence Maturity" in app
    assert "vad vet vi faktiskt" in app
