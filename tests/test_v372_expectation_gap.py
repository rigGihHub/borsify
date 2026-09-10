from pathlib import Path
from expectation_gap import build_expectation_gap


def base(**extra):
    r={
        "Förändringsbekräftelse kandidat": True,
        "Förändringsbekräftelse positiva familjer": "Rapport, Konsensus",
        "Förändringsbekräftelse negativa familjer": "",
        "Konsensus bullish andel": 0.65,
        "Konsensus analytiker antal": 8,
        "Riktkurs potential": 0.22,
        "Crowded varning": False,
        "Crowded stark varning": False,
    }
    r.update(extra)
    return r


def test_favorable_gap_requires_confirmed_change_and_room_in_expectations():
    x=build_expectation_gap(base())
    assert x["Expectation Gap kandidat"] is True
    assert x["Expectation Gap status"] == "Förbättring före förväntningarna"


def test_crowded_expectations_block_favorable_gap():
    x=build_expectation_gap(base(**{"Crowded varning":True,"Konsensus bullish andel":0.9,"Riktkurs potential":0.04}))
    assert x["Expectation Gap kandidat"] is False
    assert x["Expectation Gap varning"] is True


def test_thin_consensus_never_invents_gap():
    x=build_expectation_gap(base(**{"Konsensus analytiker antal":3}))
    assert x["Expectation Gap kandidat"] is False
    assert x["Expectation Gap status"] == "För lite förväntningsdata"


def test_unconfirmed_change_cannot_be_gap():
    x=build_expectation_gap(base(**{"Förändringsbekräftelse kandidat":False,"Förändringsbekräftelse positiva familjer":"Rapport"}))
    assert x["Expectation Gap kandidat"] is False


def test_small_target_upside_is_warning_not_favorable():
    x=build_expectation_gap(base(**{"Riktkurs potential":0.03}))
    assert x["Expectation Gap kandidat"] is False
    assert x["Expectation Gap varning"] is True


def test_release_and_ui_present():
    app=Path('app.py').read_text()
    assert 'APP_VERSION = "3.73.0"' in app
    assert 'Expectation Gap – förbättring kontra förväntningar' in app
