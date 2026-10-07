from datetime import date
from contextlib import nullcontext
from types import SimpleNamespace
import pandas as pd
from business_outlook import business_context, add_business_context, render_business_context
from analyst_case import analyst_case
from case_ai import build_case_ai_context


def test_verified_company_exposure_is_specific_not_sector_guess():
    oil = business_context({"Ticker": "HAFNI.OL", "Sektor": "Technology"})
    lpg = business_context({"Ticker": "BWLPG.OL"})
    assert oil["Bransch klassificering"] == "tankers"
    assert "oljeprodukter" in oil["Verksamhet kort"]
    assert lpg["Bransch klassificering"] == "lpg"
    assert "inte LNG" in lpg["Bolagets framtidssatsning"]
    assert "iea.org" not in str(lpg["Bransch källor"])


def test_unknown_and_nan_never_invent_business_or_growth():
    unknown = business_context({"Ticker": "UNKNOWN", "Sektor": float('nan'), "Bransch": None})
    assert not unknown["Bransch bedömd"]
    assert "saknas" in unknown["Verksamhet kort"]
    assert "inte ett tecken på låg risk" in unknown["Bransch hot"]


def test_vendor_original_is_labelled_and_classification_uses_industry_not_name():
    result = business_context({"Ticker": "NOTAI", "Namn": "AI Winner", "Bransch": "Publishing", "Verksamhetsbeskrivning": "Publishes books. Serves readers. More text.", "Fundamental hämtad": "2026-10-07"})
    assert result["Bransch klassificering"] == "media"
    assert result["Verksamhet kort"] == "Publishes books. Serves readers."
    assert "originaltext" in result["Verksamhet källstatus"]
    assert "AI" not in result["Bransch möjlighet"]


def test_stale_company_profiles_are_flagged_and_scores_unchanged():
    row = {"Ticker": "NETC.CO", "Borsify slutbetyg": 62, "Omsättningstillväxt": -.2}
    assert "behöver uppdateras" in business_context(row, date(2027, 10, 7))["Verksamhet källstatus"]
    out = add_business_context(pd.DataFrame([row]))
    assert out.iloc[0]["Borsify slutbetyg"] == 62
    assert "-20.0%" in out.iloc[0]["Bransch bolagskoppling"]
    assert "En enskild period" in out.iloc[0]["Bransch bolagskoppling"]
    pd.testing.assert_frame_equal(add_business_context(out), out)


def test_industry_reaches_thesis_risk_review_and_ai_context():
    row = {"Ticker": "HAFNI.OL"}
    thesis, risk, review = analyst_case(row)
    assert "Verksamhet:" in thesis and "Branschbedömning:" in thesis
    assert "Branschhot:" in risk and "Branschkontroll:" in review
    ai = build_case_ai_context(row, "lifetime")
    assert ai["case_data"]["Bransch hot"] == business_context(row)["Bransch hot"]
    assert ai["case_data"]["Verksamhet källa"].startswith("https://hafnia.com")


def test_cards_show_sources_and_distinguish_analysis_from_facts():
    shown = []
    st = SimpleNamespace(markdown=shown.append, write=shown.append, caption=shown.append, expander=lambda *a, **k: nullcontext())
    render_business_context(st, {"Ticker": "NETC.CO"}, compact=True)
    text = " ".join(shown)
    assert "Vad gör bolaget?" in text and "Risk:" in text and "Möjlighet:" in text
    assert "villkorade bedömning" in text and "2026" in text
    assert "https://netcompany.com/about-us/" in text and "https://www.oecd.org" in text
