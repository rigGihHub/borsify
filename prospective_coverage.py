"""Expose missing follow-up rather than silently treating available prices as the cohort."""
import json
import pandas as pd
from recommendation_ledger import horizons_for_record, target_date


def outcome_coverage(recommendations, outcomes, as_of=None):
    now = pd.Timestamp(as_of or pd.Timestamp.now(tz='UTC')).tz_localize(None).normalize()
    measured = set(zip(outcomes.get('record_id', pd.Series(dtype=str)), outcomes.get('horizon', pd.Series(dtype=str))))
    due = missing = unsupported = 0
    for _, row in recommendations.iterrows():
        try:
            snapshot = json.loads(row.get('snapshot_json') or '{}')
        except (TypeError, ValueError):
            snapshot = {}
        if snapshot.get('PIT Outcome Basis') != 'next_session_close_total_return_v1':
            unsupported += 1
            continue
        for horizon, days in horizons_for_record(row).items():
            if now >= target_date(row['captured_date'], days).normalize() + pd.Timedelta(days=4):
                due += 1
                missing += (row['record_id'], horizon) not in measured
    return {'expected_due': due, 'missing': int(missing), 'legacy_basis': unsupported}
