from pathlib import Path
import json
import pandas as pd

from policy_health_monitor import policy_health_summary, policy_health_table, policy_effect_health, opportunity_cost_health
from production_policy_registry import bootstrap_policy_registry


def test_baseline_policy_health_is_explicit_not_fake_effect(tmp_path):
    db = tmp_path / "db.sqlite"
    bootstrap_policy_registry(db, "3.19.0")
    table = policy_health_table(pd.DataFrame(), pd.DataFrame(), str(db), "3.19.0")
    head = policy_health_summary(table)
    assert head["status"] == "Baseline"
    assert head["automatic_rollback"] is False
    assert "Baseline" in " ".join(table["Detalj"].astype(str))


def test_policy_effect_warns_when_requirement_group_does_worse():
    rows = []
    for i in range(8):
        rows.append({"_target": True, "_requirement": True, "return_pct": -0.05 - i * 0.001})
    for i in range(8):
        rows.append({"_target": True, "_requirement": False, "return_pct": 0.05 + i * 0.001})
    result = policy_effect_health(pd.DataFrame(rows), "1m")
    assert result["Status"] == "Varning"
    assert result["gap"] <= -0.04


def test_opportunity_cost_flags_filtered_winners():
    rows = [{"_target": True, "_requirement": False, "return_pct": x} for x in [0.12, 0.11, 0.10, 0.09, 0.02, -0.01]]
    result = opportunity_cost_health(pd.DataFrame(rows), "1m")
    assert result["Status"] == "Varning"
    assert result["winner_rate"] >= 0.40


def test_policy_health_summary_requires_manual_rollback_review():
    table = pd.DataFrame([
        {"Kontroll": "Runtime-integritet", "Status": "OK", "N": 1, "Detalj": "ok"},
        {"Kontroll": "Policyutfall 1m", "Status": "Varning", "N": 20, "Detalj": "bad"},
        {"Kontroll": "Missade vinnare 1m", "Status": "Varning", "N": 10, "Detalj": "bad"},
    ])
    head = policy_health_summary(table)
    assert head["status"] == "Granska rollback"
    assert head["automatic_rollback"] is False


def test_v319_ui_and_version_contract():
    root = Path(__file__).resolve().parents[1]
    app = (root / "app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "3.81.0"' in app
    assert "Policy Health Monitor · hjälper den aktiva policyn fortfarande?" in app
    assert "policy_health_table" in app
    assert "aldrig själv ändra urvalsregler eller genomföra rollback" in app
