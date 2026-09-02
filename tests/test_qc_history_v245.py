from datetime import datetime, timezone, timedelta
import pandas as pd

from qc_history import (
    evolve_qc_state, is_quarantined, scan_health, quarantine_summary,
    should_record_qc_outcome,
)

T0=datetime(2026,9,1,12,0,tzinfo=timezone.utc)

def test_three_separate_hard_failures_trigger_quarantine():
    s=None
    for day in range(3):
        now=T0+timedelta(days=day)
        assert should_record_qc_outcome(s,"hard_failure",now)
        s=evolve_qc_state(s,symbol="BAD",outcome="hard_failure",reason="no price",now=now)
    assert s["failure_streak"]==3
    assert s["status"]=="KARANTÄN"
    assert is_quarantined(s,T0+timedelta(days=2,hours=1))

def test_same_day_rerun_does_not_count_as_new_observation():
    s=evolve_qc_state(None,symbol="BAD",outcome="hard_failure",now=T0)
    assert not should_record_qc_outcome(s,"hard_failure",T0+timedelta(hours=2))

def test_success_immediately_clears_failure_streak_and_quarantine():
    s=None
    for day in range(3):
        s=evolve_qc_state(s,symbol="X",outcome="hard_failure",now=T0+timedelta(days=day))
    assert is_quarantined(s,T0+timedelta(days=2,hours=1))
    recovered=evolve_qc_state(s,symbol="X",outcome="verified",now=T0+timedelta(days=3))
    assert recovered["failure_streak"]==0
    assert recovered["quarantine_until"] is None
    assert recovered["status"]=="VERIFIERAD"

def test_provider_outage_guard_does_not_count_failure():
    health=scan_health(1,100)
    assert health["provider_healthy_enough"] is False
    s=evolve_qc_state(None,symbol="X",outcome="transient_failure",now=T0,count_failure=False)
    assert s["failure_streak"]==0
    assert s["failure_count"]==0

def test_reasonable_batch_allows_individual_strikes():
    health=scan_health(20,100)
    assert health["provider_healthy_enough"] is True

def test_quarantine_expires_after_seven_days():
    s=None
    for day in range(3):
        s=evolve_qc_state(s,symbol="X",outcome="hard_failure",now=T0+timedelta(days=day))
    assert not is_quarantined(s,T0+timedelta(days=9,hours=1))

def test_summary_counts_active_quarantine():
    s1=None
    for day in range(3):
        s1=evolve_qc_state(s1,symbol="A",outcome="hard_failure",now=T0+timedelta(days=day))
    s2=evolve_qc_state(None,symbol="B",outcome="verified",now=T0)
    frame=pd.DataFrame([s1,s2])
    summary=quarantine_summary(frame,T0+timedelta(days=2,hours=1))
    assert summary["quarantined"]==1
    assert summary["verified"]==1
