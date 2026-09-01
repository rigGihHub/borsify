import pandas as pd

from idea_radar import IdeaSource, parse_feed, map_mentions, build_verified_ideas, classify_event


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


def test_media_pulse_marks_recent_cluster():
    now = pd.Timestamp.utcnow().tz_localize(None)
    rows = []
    for i in range(3):
        rows.append({
            "source": f"Media{i}", "publisher": f"Media{i}", "kind": "media", "category": "Ekonomimedia",
            "source_weight": 1.0, "title": f"Investor nyhet {i}", "summary": "Investor rapport",
            "link": f"https://example.test/{i}", "published": now - pd.Timedelta(hours=2+i),
        })
    feed = pd.DataFrame(rows)
    stocks = pd.DataFrame([{"Ticker": "INVE-B.ST", "Namn": "Investor AB"}])
    mentions = map_mentions(feed, stocks)
    assert mentions.iloc[0]["Omnämnanden 24h"] == 3
    assert mentions.iloc[0]["Mediepuls"] == "Ökad uppmärksamhet"


def test_strong_media_plus_fundamentals_creates_combination_signal_without_changing_borsify_score():
    now = pd.Timestamp.utcnow().tz_localize(None)
    mentions = pd.DataFrame([{
        "Ticker": "GOOD.ST", "Namn": "Good AB", "Antal omnämnanden": 4, "Källor": 3,
        "Forum": 0, "Media": 4, "Senast nämnd": now, "Rubriker": [],
        "Mediekällor": 3, "Forumkällor": 0, "Viktade omnämnanden": 4.0,
        "Omnämnanden 24h": 3, "Omnämnanden 7d": 4, "Mediepuls": "Ökad uppmärksamhet",
    }])
    scored = pd.DataFrame([{
        "Ticker": "GOOD.ST", "Namn": "Good AB", "Borsify Score": 78, "INVEST Score": 76,
        "SWING Score": 60, "REVERSAL Score": 55, "Värdering": 68, "Kvalitet": 75, "Risk": 70,
        "Direktavkastning": 0.03, "P/E": 16, "ROE": 0.20, "Skuld/eget kapital": 45,
        "Riskflaggor": "—", "Datatäckning": 0.95,
    }])
    ideas = build_verified_ideas(mentions, scored)
    assert ideas.iloc[0]["Kombinationssignal"] == "Ovanligt intressant kombination"
    assert ideas.iloc[0]["Borsify Score"] == 78
    assert ideas.iloc[0]["Idéprioritet"] > 70


def test_forum_attention_alone_cannot_create_top_combination():
    now = pd.Timestamp.utcnow().tz_localize(None)
    mentions = pd.DataFrame([{
        "Ticker": "FORUM.ST", "Namn": "Forum AB", "Antal omnämnanden": 30, "Källor": 2,
        "Forum": 30, "Media": 0, "Senast nämnd": now, "Rubriker": [],
        "Mediekällor": 0, "Forumkällor": 2, "Viktade omnämnanden": 18.0,
        "Omnämnanden 24h": 12, "Omnämnanden 7d": 30, "Mediepuls": "Ökad uppmärksamhet",
    }])
    scored = pd.DataFrame([{
        "Ticker": "FORUM.ST", "Namn": "Forum AB", "Borsify Score": 80, "INVEST Score": 75,
        "SWING Score": 60, "REVERSAL Score": 55, "Värdering": 70, "Kvalitet": 76, "Risk": 72,
        "Direktavkastning": 0.02, "P/E": 15, "ROE": 0.22, "Skuld/eget kapital": 35,
        "Riskflaggor": "—", "Datatäckning": 0.95,
    }])
    ideas = build_verified_ideas(mentions, scored)
    assert ideas.iloc[0]["Kombinationssignal"] != "Ovanligt intressant kombination"


def test_event_classifier_identifies_common_company_events():
    assert classify_event("Bolaget vinstvarnar efter svagare försäljning", "") [0] == "Vinstvarning / tydlig försämring"
    assert "Rapport / resultat" in classify_event("Investor rapport: högre rörelseresultat", "")
    assert "Insiderhandel" in classify_event("VD gör stort insynsköp i bolaget", "")
    assert "Order / kontrakt" in classify_event("Bolaget vinner kontrakt värt 500 MSEK", "")
    assert "Förvärv / fusion / bud" in classify_event("Bolaget köper konkurrent i nytt förvärv", "")


def test_map_mentions_explains_why_stock_is_in_media():
    now = pd.Timestamp.utcnow().tz_localize(None)
    feed = pd.DataFrame([{
        "source": "Testmedia", "publisher": "Testmedia", "kind": "media", "category": "Bolagshändelse",
        "source_weight": 1.0, "title": "Investor höjer utdelningen efter rapport",
        "summary": "Investor publicerar rapport och föreslår utdelning.", "link": "https://example.test/a", "published": now,
    }])
    stocks = pd.DataFrame([{"Ticker": "INVE-B.ST", "Namn": "Investor AB"}])
    mentions = map_mentions(feed, stocks)
    assert mentions.iloc[0]["Huvudhändelse"] == "Rapport / resultat"
    assert "Utdelning / återköp" in mentions.iloc[0]["Händelsetyper"]
    assert "rapport" in mentions.iloc[0]["Händelseförklaring"].lower()


def test_forum_without_clear_event_is_labeled_forum_discussion():
    now = pd.Timestamp.utcnow().tz_localize(None)
    feed = pd.DataFrame([{
        "source": "Forum", "publisher": "Forum", "kind": "forum", "category": "Forum",
        "source_weight": 0.5, "title": "Vad tycker ni om Investor?", "summary": "Investor känns intressant",
        "link": "https://example.test/f", "published": now,
    }])
    stocks = pd.DataFrame([{"Ticker": "INVE-B.ST", "Namn": "Investor AB"}])
    mentions = map_mentions(feed, stocks)
    assert mentions.iloc[0]["Huvudhändelse"] == "Forumdiskussion"


def test_case_impact_flags_profit_warning_as_new_risk():
    from idea_radar import case_impact_assessment
    row = pd.Series({
        "Huvudhändelse": "Vinstvarning / tydlig försämring",
        "Händelsetyper": ["Vinstvarning / tydlig försämring"],
        "Risk": 65,
    })
    label, explanation, level = case_impact_assessment(row)
    assert label == "Ny risk – kontrollera direkt"
    assert level == 3
    assert "vinstvarning" in explanation.lower()


def test_case_impact_does_not_treat_target_price_as_fundamental_change():
    from idea_radar import case_impact_assessment
    row = pd.Series({
        "Huvudhändelse": "Analys / riktkurs",
        "Händelsetyper": ["Analys / riktkurs"],
        "Borsify Score": 82,
    })
    label, explanation, level = case_impact_assessment(row)
    assert label == "Troligen sekundär information"
    assert level == 1
    assert "ändrar inte bolagets verksamhet" in explanation


def test_build_verified_ideas_includes_case_impact_columns():
    mentions = pd.DataFrame([{
        "Ticker": "TEST.ST", "Namn": "Test AB", "Antal omnämnanden": 1, "Källor": 1,
        "Forum": 0, "Media": 1, "Senast nämnd": pd.Timestamp("2026-08-31"), "Rubriker": [],
        "Mediekällor": 1, "Forumkällor": 0, "Viktade omnämnanden": 1.0,
        "Omnämnanden 24h": 1, "Omnämnanden 7d": 1, "Mediepuls": "Nytt omnämnande",
        "Huvudhändelse": "Rapport / resultat", "Händelsetyper": ["Rapport / resultat"],
        "Händelseförklaring": "Rapport.",
    }])
    scored = pd.DataFrame([{
        "Ticker": "TEST.ST", "Namn": "Test AB", "Borsify Score": 70, "INVEST Score": 70,
        "SWING Score": 55, "REVERSAL Score": 50, "Värdering": 60, "Kvalitet": 70, "Risk": 65,
        "Direktavkastning": 0.02, "P/E": 15, "ROE": 0.15, "Skuld/eget kapital": 40,
        "Riskflaggor": "—", "Datatäckning": 0.9,
    }])
    ideas = build_verified_ideas(mentions, scored)
    assert ideas.iloc[0]["Case Impact"] == "Kan ändra investeringscaset"
    assert int(ideas.iloc[0]["Case Impact Nivå"]) == 3
