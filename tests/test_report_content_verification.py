import hashlib
import json

import pandas as pd
import pytest

from recommendation_ledger import build_recommendation_records
from report_fetcher import verify_primary_report_from_events
from report_sources import candidate_report, report_freshness, source_priority
from report_verification import (
    can_support_fresh_recommendation,
    report_data_provenance,
    verify_report_text,
)


URL = "https://www.nasdaq.com/european-market-activity/news/company-news/example-q3"
BODY = (
    "Example AB Q3 2026 interim report. Revenue SEK 100 million. "
    "Operating profit SEK 12 million. Cash flow SEK 20 million. "
    + "The company describes its operations and financial outlook. " * 40
)


def candidate():
    return candidate_report("Example AB Q3 2026 report", "2026-09-01T08:00:00+02:00", URL, source="Nasdaq")


@pytest.mark.parametrize("url", [
    "https://nasdaq.com.example.org/report",
    "https://example.org/nasdaq.com/report",
    "https://example.org/report?source=news.eu.nasdaq.com",
    "https://nasdaq.com@example.org/report",
    "https://example.org/investor-relations/report",
    "https://example.org/ir/report",
    "https://www.nasdaq.com/articles/secondary-report-summary",
    "file://nasdaq.com/report",
    "https://[broken/report",
])
def test_url_strings_do_not_establish_primary_source(url):
    assert source_priority(url, "Sverige") == 9
    cand = candidate()
    cand["url"] = url
    assert verify_report_text(cand, "Sverige", BODY)["Rapport läst"] is False


@pytest.mark.parametrize("url,country", [
    (URL, "Sverige"),
    ("https://news.eu.nasdaq.com/report", "Danmark"),
    ("https://live.euronext.com/en/report", "Norge"),
])
def test_recognised_exchange_hosts(url, country):
    assert source_priority(url, country) == 1


@pytest.mark.parametrize("body", [
    "Cookie settings. Privacy policy. Contact us. " * 80,
    "Quarterly report guidance margin cash flow risk. " * 80,
    "Q3 2026 report. Contact us for information. " * 80,
    "Revenue SEK 100 million. Profit SEK 12 million. " * 80,
])
def test_long_navigation_or_keyword_text_is_not_a_read_report(body):
    result = verify_report_text(candidate(), "Sverige", body)
    assert result["Rapport läst"] is False
    assert "Rapport text SHA256" not in result


def test_report_period_must_match_discovered_title():
    result = verify_report_text(candidate(), "Sverige", BODY.replace("Q3 2026", "Q2 2025"))
    assert result["Rapport läst"] is False
    assert "stämmer inte" in result["Rapport kontroll"]


def test_financial_body_has_content_fingerprint_and_no_delta_text_claim():
    report = verify_report_text(candidate(), "Sverige", BODY)
    assert report["Rapport läst"] is True
    assert report["Rapport periodtext"] == "Q3 2026"
    assert report["Rapport finansiella ämnen"] == ["omsättning", "resultat", "kassaflöde"]
    assert report["Rapport text SHA256"] == hashlib.sha256(BODY.strip().encode()).hexdigest()
    assert report["Rapport textutdrag"][0] == {"ämne": "omsättning", "textutdrag": "Revenue SEK 100 million"}
    assert pd.Timestamp(report["Rapport kontrollerad"]).tzinfo is not None
    provenance = report_data_provenance({}, report)
    assert provenance["Rapport text verifierad"] is True
    assert "används inte i Report Delta" in provenance["Report Delta datagrund"]


def test_redirect_to_secondary_source_cannot_verify_primary_text(monkeypatch):
    monkeypatch.setattr("report_fetcher.fetch_report_text", lambda *_a, **_kw: {
        "ok": True, "text": BODY, "resolved_url": "https://example.org/news/report",
    })
    result = verify_primary_report_from_events({"news": [{
        "title": "Example AB Q3 2026 report", "link": URL,
        "published_at": "2026-09-01T08:00:00+02:00",
    }]}, "Sverige")
    assert result["Rapport läst"] is False
    assert result["Rapport URL"] == "https://example.org/news/report"
    assert result["Rapport begärd URL"] == URL


def test_failed_check_remains_visible_in_provenance():
    report = verify_report_text(candidate(), "Sverige", "Cookie policy. " * 200)
    provenance = report_data_provenance({}, report)
    assert provenance["Rapport läst"] is False
    assert provenance["Rapport kontroll"] == report["Rapport kontroll"]
    assert provenance["Rapport titel"] == report["Rapport titel"]
    assert provenance["Rapport URL"] == URL


def test_legacy_truthy_flag_is_not_text_verification():
    assert report_data_provenance({}, {"Rapport läst": "False"})["Rapport text verifierad"] is False
    assert report_data_provenance({}, {"Rapport läst": True})["Rapport text verifierad"] is False


@pytest.mark.parametrize("published", ["", "NaT", "invalid", "2026-10-01T08:00:00+02:00"])
def test_unknown_or_future_date_cannot_support_fresh_recommendation(published):
    freshness = report_freshness(published, now="2026-09-30T08:00:00+02:00")
    assert freshness["known"] is False
    assert can_support_fresh_recommendation({
        "Rapport läst": True, "Rapport datum verifierat": freshness["known"],
        "Rapport färskhet": freshness["label"],
    }) is False


@pytest.mark.parametrize("horizon", ["short", "long"])
def test_ledger_freezes_report_check_evidence(horizon):
    report = verify_report_text(candidate(), "Sverige", BODY)
    frame = pd.DataFrame([{"Ticker": "EXAMPLE.ST", "Pris": 100, **report}])
    row = build_recommendation_records(frame, horizon, "4.39.2", "Balanserad", "Sverige")[0]
    snap = json.loads(row["snapshot_json"])
    for field in ["Rapport text SHA256", "Rapport kontrollerad", "Rapport verifieringsversion",
                  "Rapport periodtext", "Rapport finansiella ämnen", "Rapport textutdrag", "Rapport datum verifierat"]:
        assert snap[field] == report[field]
    report["Rapport text SHA256"] = "changed later"
    assert json.loads(row["snapshot_json"])["Rapport text SHA256"] != report["Rapport text SHA256"]
