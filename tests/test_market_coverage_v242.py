from pathlib import Path

def test_v242_contains_all_15_direct_market_countries_and_country_filter():
    text=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")
    for country in [
        "Sverige","USA","Kanada","Danmark","Norge","Finland","Tyskland","Storbritannien",
        "Frankrike","Nederländerna","Belgien","Portugal","Italien","Spanien","Schweiz",
    ]:
        assert country in text
    assert "Filtrera Topplistor på land" in text
    assert "CANADA_LARGE_TICKERS" in text
    assert "FRANCE_LARGE_TICKERS" in text
    assert "SWITZERLAND_LARGE_TICKERS" in text
