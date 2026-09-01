import numpy as np

from mispricing_engine import (
    required_eps_cagr,
    fcf_growth_hurdle,
    build_mispricing_assessment,
    apply_mispricing_gate,
    mispricing_rank_value,
)


def test_required_eps_cagr_is_zero_when_return_and_multiple_offset():
    # forward P/E 20 -> exit P/E 20 requires exactly the return hurdle as EPS growth.
    got = required_eps_cagr(20, 20, 0.10, 5)
    assert abs(got - 0.10) < 1e-9


def test_multiple_compression_requires_more_growth():
    assert required_eps_cagr(30, 20, 0.10, 5) > 0.10


def test_fcf_hurdle_is_transparent_difference():
    assert abs(fcf_growth_hurdle(0.06, 0.10) - 0.04) < 1e-9


def test_strong_growth_and_low_trap_can_show_possible_mispricing():
    snapshot = {"Forward P/E": 14, "FCF-yield": 0.07, "Vinsttillväxt": 0.12}
    deep = {
        "FCF CAGR": 0.15, "Vinst CAGR": 0.13, "Omsättning CAGR": 0.10,
        "Value Trap Risk": 10, "Deep Confidence": 80, "Inflection Score": 72,
    }
    out = build_mispricing_assessment(snapshot, deep)
    assert out["Mispricing Signal"] in {"Tydlig möjlig felprissättning", "Möjlig felprissättning"}
    assert out["Mispricing stöd"] >= 1


def test_demanding_valuation_with_slow_growth_is_challenged():
    snapshot = {"Forward P/E": 35, "FCF-yield": 0.02}
    deep = {
        "FCF CAGR": 0.03, "Vinst CAGR": 0.04, "Omsättning CAGR": 0.04,
        "Value Trap Risk": 15, "Deep Confidence": 80, "Inflection Score": 45,
    }
    out = build_mispricing_assessment(snapshot, deep)
    assert out["Mispricing Signal"] == "Marknaden kan vara mer rimlig än caset"
    assert out["Mispricing motbevis"] >= 2


def test_high_value_trap_risk_blocks_strong_conclusion():
    snapshot = {"Forward P/E": 10, "FCF-yield": 0.09}
    deep = {
        "FCF CAGR": 0.18, "Vinst CAGR": 0.16, "Omsättning CAGR": 0.12,
        "Value Trap Risk": 70, "Deep Confidence": 85, "Inflection Score": 75,
    }
    out = build_mispricing_assessment(snapshot, deep)
    assert out["Mispricing Signal"] != "Tydlig möjlig felprissättning"
    assert out["Mispricing motbevis"] >= 2


def test_missing_valuation_data_stays_unassessed():
    out = build_mispricing_assessment({}, {"FCF CAGR": 0.10, "Deep Confidence": 90})
    assert out["Mispricing Signal"] == "Kan inte bedömas"
    assert out["Mispricing-lins antal"] == 0


def test_bad_mispricing_can_downgrade_but_good_one_does_not_promote():
    bad = apply_mispricing_gate({"Djupkontroll": "Klarar djupkontroll", "Mispricing Signal": "Marknaden kan vara mer rimlig än caset"})
    assert bad["Djupkontroll"] == "Kräver extra kontroll"
    good = apply_mispricing_gate({"Djupkontroll": "Neutral djupkontroll", "Mispricing Signal": "Tydlig möjlig felprissättning"})
    assert good["Djupkontroll"] == "Neutral djupkontroll"


def test_mispricing_rank_value_prefers_supported_gap():
    assert mispricing_rank_value({"Mispricing Signal": "Tydlig möjlig felprissättning"}) > mispricing_rank_value({"Mispricing Signal": "Ingen tydlig felprissättning"})
