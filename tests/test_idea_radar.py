import pandas as pd

from idea_radar import IdeaSource, parse_feed, map_mentions, build_verified_ideas


def test_parse_rss_and_match_company():
    xml = b'''<?xml version="1.0"?><rss><channel><item><title>Investor ser intressant ut efter rapporten</title><link>https://example.test/a</link><pubDate>Sun, 31 Aug 2026 12:00:00 GMT</pubDate><description>Diskussion om Investor.</description></item></channel></rss>'''
    source = IdeaSource("Testmedia", "media", "https://example.test/feed")
    feed = pd.DataFrame(parse_feed(xml, source))
    stocks = pd.DataFrame([{"Ticker": "INVE-B.ST", "Namn": "Investor AB (publ)"}])
    mentions = map_mentions(feed, stocks)
    assert len(mentions) == 1
    assert mentions.iloc[0]["Ticker"] == "INVE-B.ST"
    assert mentions.iloc[0]["Antal omnämnanden"] == 1


def test_external_mention_does_not_override_weak_borsify_check():
    mentions = pd.DataFrame([{
        "Ticker": "TEST.ST", "Namn": "Test AB", "Antal omnämnanden": 8, "Källor": 2,
        "Forum": 4, "Media": 4, "Senast nämnd": pd.Timestamp("2026-08-31"), "Rubriker": []
    }])
    scored = pd.DataFrame([{
        "Ticker": "TEST.ST", "Namn": "Test AB", "Borsify Score": 45, "INVEST Score": 40,
        "SWING Score": 55, "REVERSAL Score": 60, "Värdering": 50, "Kvalitet": 35, "Risk": 40,
        "Direktavkastning": 0.0, "P/E": 30, "ROE": 0.05, "Skuld/eget kapital": 250,
        "Riskflaggor": "Hög skuld", "Datatäckning": 0.9,
    }])
    ideas = build_verified_ideas(mentions, scored)
    assert ideas.iloc[0]["Borsify-granskning"] == "Uppslag, inte fynd"
    assert ideas.iloc[0]["Upptäcktsstyrka"] > 50


def test_forum_only_discovery_is_capped_below_strongest_level():
    from idea_radar import discovery_strength
    row = pd.Series({
        "Antal omnämnanden": 50,
        "Viktade omnämnanden": 50,
        "Källor": 3,
        "Mediekällor": 0,
        "Senast nämnd": pd.Timestamp("2026-08-31"),
    })
    score = discovery_strength(row, now=pd.Timestamp("2026-08-31"))
    assert score <= 68


def test_google_style_rss_keeps_original_publisher_when_available():
    xml = b'''<?xml version="1.0"?><rss><channel><item><title>Investor hojs - EFN</title><link>https://example.test/a</link><pubDate>Sun, 31 Aug 2026 12:00:00 GMT</pubDate><source>EFN</source><description>Investor analyseras.</description></item></channel></rss>'''
    source = IdeaSource("Samlat flode", "media", "https://example.test/feed", category="Analys")
    rows = parse_feed(xml, source)
    assert rows[0]["publisher"] == "EFN"
    assert rows[0]["category"] == "Analys"
