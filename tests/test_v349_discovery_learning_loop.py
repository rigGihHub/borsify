import pandas as pd

from discovery_learning_loop import build_discovery_learning_proposals, discovery_learning_summary


def _row(pattern, misses=5, over=1.5, med=.20):
    return {"pattern": pattern, "misses": misses, "miss_share": .5, "cohort_share": .25,
            "overrepresentation": over, "median_return": med, "status": "Återkommande missmönster"}


def test_strong_pattern_creates_prospective_challenger_proposal_only():
    proposals = build_discovery_learning_proposals(pd.DataFrame([_row("Dyra kvalitetsbolag", 6, 2.0)]))
    assert len(proposals) == 1
    assert proposals.iloc[0]["status"] == "Redo för prospektiv challenger"
    assert "extra kandidatplats" in proposals.iloc[0]["proposal"]
    assert "Ingen produktionsändring" in proposals.iloc[0]["next_step"]


def test_weak_pattern_never_becomes_ready():
    proposals = build_discovery_learning_proposals(pd.DataFrame([_row("Vändningscase", 3, 2.0)]))
    assert proposals.iloc[0]["status"] == "Samla mer underlag"


def test_overrepresentation_threshold_is_required():
    proposals = build_discovery_learning_proposals(pd.DataFrame([_row("Hög kvalitet", 8, 1.2)]))
    assert proposals.iloc[0]["status"] == "Samla mer underlag"


def test_unknown_or_unfrozen_pattern_is_not_invented_into_action():
    proposals = build_discovery_learning_proposals(pd.DataFrame([_row("Ingen tydlig fryst faktor", 10, 3.0)]))
    assert proposals.empty


def test_summary_never_claims_automatic_learning():
    proposals = build_discovery_learning_proposals(pd.DataFrame([_row("Svagt marknadsläge", 7, 1.8)]))
    summary = discovery_learning_summary(proposals)
    assert summary["status"] == "Challengerförslag finns"
    assert "ändras inte automatiskt" in summary["text"]
