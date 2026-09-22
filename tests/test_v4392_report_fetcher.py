from report_fetcher import fetch_report_text, verify_primary_report_from_events


class _Response:
    headers = {"content-type": "text/html; charset=utf-8"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        body = "<html><body>" + ("Quarterly report guidance margin cash flow risk. " * 80) + "</body></html>"
        return body.encode("utf-8")


def test_fetch_report_text_extracts_html(monkeypatch):
    monkeypatch.setattr("report_fetcher.urlopen", lambda *_args, **_kwargs: _Response())
    result = fetch_report_text("https://www.nasdaq.com/european-market-activity/news/company-news/test")
    assert result["ok"] is True
    assert "Quarterly report guidance" in result["text"]
    assert "<html>" not in result["text"]


def test_primary_report_event_can_be_verified(monkeypatch):
    monkeypatch.setattr("report_fetcher.urlopen", lambda *_args, **_kwargs: _Response())
    report = verify_primary_report_from_events(
        {
            "news": [{
                "title": "Example AB Q3 quarterly report",
                "link": "https://www.nasdaq.com/european-market-activity/news/company-news/example-q3",
                "published_at": "2026-09-01T08:00:00+02:00",
                "provider": "Nasdaq Nordic",
            }]
        },
        "Sverige",
    )
    assert report is not None
    assert report["Rapport läst"] is True
    assert report["Rapport textlängd"] >= 1500
    assert report["Guidance nämns"] is True


def test_secondary_report_event_is_not_fetched(monkeypatch):
    calls = {"count": 0}

    def _boom(*_args, **_kwargs):
        calls["count"] += 1
        raise AssertionError("secondary source should not be fetched")

    monkeypatch.setattr("report_fetcher.urlopen", _boom)
    report = verify_primary_report_from_events(
        {
            "news": [{
                "title": "Example AB Q3 quarterly report",
                "link": "https://finance.yahoo.com/news/example-q3",
                "published_at": "2026-09-01T08:00:00+02:00",
                "provider": "Yahoo",
            }]
        },
        "Sverige",
    )
    assert report is None
    assert calls["count"] == 0
