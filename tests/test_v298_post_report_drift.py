import numpy as np
import pandas as pd

from post_report_drift import build_post_report_drift
from recommendation_ledger import snapshot_columns

NOW = pd.Timestamp("2026-09-05", tz="UTC")


def _earnings(date="2026-08-20", surprise=.08):
    return pd.DataFrame({"surprisePercent": [surprise]}, index=pd.to_datetime([date], utc=True))


def _prices(values):
    idx = pd.to_datetime(["2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24", "2026-09-04"], utc=True)
    return pd.DataFrame({"Close": values}, index=idx)


def _metrics(eps=.04, balance=.5, weight=.75):
    return {
        "EPS-estimat förändring": eps,
        "EPS-revisionsbalans": balance,
        "Estimat tillförlitlighetsvikt": weight,
    }


def test_positive_report_drift_requires_surprise_reaction_and_follow_through():
    result = build_post_report_drift(_earnings(), _prices([100, 102, 104, 106, 109]), _metrics(), NOW)
    assert result["Post-report status"] == "Positiv rapportdrift"
    assert result["Post-report stöd"] is True
    assert result["Post-report varning"] is False
    assert result["Post-report reaktion"] > .03
    assert result["Post-report fortsatt rörelse"] > .04


def test_good_report_that_reverses_is_warning_not_support():
    result = build_post_report_drift(_earnings(), _prices([100, 104, 105, 101, 98]), _metrics(), NOW)
    assert result["Post-report status"] == "Bra rapport men styrkan har vänt"
    assert result["Post-report stöd"] is False
    assert result["Post-report varning"] is True


def test_negative_report_drift_is_warning():
    result = build_post_report_drift(_earnings(surprise=-.10), _prices([100, 98, 95, 94, 91]), _metrics(eps=-.05, balance=-.5), NOW)
    assert result["Post-report status"] == "Negativ rapportdrift"
    assert result["Post-report varning"] is True


def test_old_report_is_not_why_now_support():
    result = build_post_report_drift(_earnings(date="2026-05-01"), _prices([100, 102, 104, 106, 109]), _metrics(), NOW)
    assert "för gammal" in result["Post-report status"]
    assert result["Post-report stöd"] is False


def test_missing_data_is_not_inferred():
    result = build_post_report_drift(pd.DataFrame(), pd.DataFrame(), {}, NOW)
    assert result["Post-report status"] == "För lite data"
    assert np.isnan(result["Post-report reaktion"])


def test_point_in_time_ledger_freezes_post_report_fields():
    cols = snapshot_columns("long")
    assert "Post-report reaktion" in cols
    assert "Post-report fortsatt rörelse" in cols
    assert "Post-report analytikerrespons" in cols


def test_app_wires_engine_into_deep_and_short_paths():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert 'from post_report_drift import build_post_report_drift' in app
    assert app.count('build_post_report_drift(') >= 2
    assert 'build_post_report_drift(' in app
