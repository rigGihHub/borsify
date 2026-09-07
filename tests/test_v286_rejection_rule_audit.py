import json
import pandas as pd

from false_negative_analysis import rejection_rule_audit, rejection_rule_audit_summary


def _rec(i, evidence, decision="NOT_RECOMMENDED"):
    return {
        "record_id": f"r{i}", "symbol": f"S{i}", "name": f"S{i}", "captured_date": "2026-01-01",
        "horizon_type": "long", "rank": i + 1, "gate": "Bevaka", "model_version": "2.86.0",
        "snapshot_json": json.dumps({"Ledger Decision": decision, "Case Evidence Count": evidence}),
    }


def test_rejection_rule_audit_flags_reason_only_with_comparison_support():
    recs = pd.DataFrame([_rec(i, 2 if i < 5 else 5) for i in range(10)])
    outs = pd.DataFrame([
        {"record_id": f"r{i}", "horizon": "1y", "return_pct": (0.25 if i < 4 else 0.02)}
        for i in range(10)
    ])
    audit = rejection_rule_audit(recs, outs, "1y")
    row = audit[audit["Stopporsak"].eq("För få oberoende stöd")].iloc[0]
    assert row["Med orsaken"] == 5
    assert row["Utan orsaken"] == 5
    assert row["Missar med orsaken"] == 4
    assert row["Status"] == "Granska om regeln är för hård"
    assert rejection_rule_audit_summary(audit)["status"] == "Regel värd att granska"


def test_rejection_rule_audit_excludes_missing_old_fields_instead_of_calling_them_clean():
    rows = [_rec(i, 2 if i < 5 else 5) for i in range(10)]
    rows.append({
        "record_id": "old", "symbol": "OLD", "name": "OLD", "captured_date": "2025-01-01",
        "horizon_type": "long", "rank": 11, "gate": "Bevaka", "model_version": "2.70.0",
        "snapshot_json": json.dumps({"Ledger Decision": "NOT_RECOMMENDED"}),
    })
    recs = pd.DataFrame(rows)
    outs = pd.DataFrame([{"record_id": f"r{i}", "horizon": "1y", "return_pct": 0.01} for i in range(10)] +
                        [{"record_id": "old", "horizon": "1y", "return_pct": 0.50}])
    audit = rejection_rule_audit(recs, outs, "1y")
    row = audit[audit["Stopporsak"].eq("För få oberoende stöd")].iloc[0]
    assert row["Med orsaken"] == 5
    assert row["Utan orsaken"] == 5


def test_rejection_rule_audit_uses_one_metric_basis_for_whole_cohort():
    recs = pd.DataFrame([_rec(i, 2 if i < 5 else 5) for i in range(10)])
    outs = pd.DataFrame([
        {"record_id": f"r{i}", "horizon": "1y", "return_pct": 0.20 if i < 3 else 0.01,
         "excess_return_pct": None if i == 0 else 0.30}
        for i in range(10)
    ])
    audit = rejection_rule_audit(recs, outs, "1y")
    row = audit[audit["Stopporsak"].eq("För få oberoende stöd")].iloc[0]
    assert row["Mätning"] == "Rå kursutveckling"


def test_v286_ui_exposes_rule_audit_without_auto_relaxing_model():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.26.0"' in app
    assert "Stoppar någon regel för många framtida vinnare?" in app
    assert "rejection_rule_audit(recs, outs, chosen_h)" in app
    assert "Ingen modellvikt eller köpgräns ändras automatiskt" in app
