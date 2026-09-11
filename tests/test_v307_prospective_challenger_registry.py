import pandas as pd

from prospective_challenger_registry import (
    STATUS_CANDIDATE,
    STATUS_REGISTERED,
    default_prospective_challengers,
    definition_fingerprint,
    eligible_prospective_recommendations,
    prospective_governance,
    registry_table,
)


def test_registry_is_predeclared_and_fingerprinted():
    specs = default_prospective_challengers()
    assert len(specs) == 6
    assert len({x.challenger_id for x in specs}) == 6
    table = registry_table(specs)
    assert set(table["Förregistrerad version"]) == {"3.07.0"}
    assert set(table["Förregistrerad datum"]) == {"2026-09-06"}
    assert table["Definition"].str.len().eq(16).all()


def test_fingerprint_changes_when_definition_changes():
    spec = default_prospective_challengers()[0]
    from dataclasses import replace
    changed = replace(spec, hypothesis=spec.hypothesis + " ändrad")
    assert definition_fingerprint(spec) != definition_fingerprint(changed)


def test_only_post_registration_version_and_date_are_eligible():
    spec = default_prospective_challengers()[0]
    recs = pd.DataFrame([
        {"record_id": "old-version", "model_version": "3.06.0", "captured_date": "2026-09-10"},
        {"record_id": "old-date", "model_version": "3.07.0", "captured_date": "2026-09-05"},
        {"record_id": "eligible", "model_version": "3.07.0", "captured_date": "2026-09-06"},
        {"record_id": "later", "model_version": "3.08.0", "captured_date": "2026-09-20"},
    ])
    out = eligible_prospective_recommendations(recs, spec)
    assert set(out["record_id"]) == {"eligible", "later"}


def test_governance_waits_without_new_outcomes():
    gov = prospective_governance(pd.DataFrame())
    assert not gov.empty
    assert set(gov["Status"]) == {STATUS_REGISTERED}


def test_candidate_requires_two_prospective_wins_and_large_sample():
    spec = default_prospective_challengers()[0]
    detail = pd.DataFrame([
        {"Challenger ID": spec.challenger_id, "Status": "Challenger bättre", "Oberoende case": 52},
        {"Challenger ID": spec.challenger_id, "Status": "Challenger bättre", "Oberoende case": 48},
    ])
    gov = prospective_governance(detail, [spec])
    assert gov.iloc[0]["Status"] == STATUS_CANDIDATE


def test_v307_ui_and_version_are_wired():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "Prospektivt Challenger-register" in app
    assert "Case från före registreringen får aldrig räknas" in app
    assert "Ingen automatisk promotion" in app
