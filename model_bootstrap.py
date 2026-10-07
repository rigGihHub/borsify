"""Refresh model APIs once when Streamlit retains imports during a hot deploy."""
import importlib

RELEASE = "4.41.8-research-breadth"
_MODULES = ["ecb_fx", "data_acquisition", "data_trust", "source_health_dashboard", "research_merge", "deep_case_engine", "dividend_units", "stockanalysis_fundamentals", "fundamental_acquisition", "scan_snapshot_cache", "analysis_confidence", "business_report_evidence", "research_rotation", "prospective_score_audit", "business_outlook", "lifetime_suitability", "purchase_consistency", "analyst_case", "decision_brief", "first_choice_gate", "business_management_intelligence", "top_pick_explainer", "horizon_rankings", "horizon_alternatives", "up_and_coming", "issuer_report_sources", "report_sources", "report_reader", "report_verification", "report_fetcher", "inflection_engine", "post_report_drift", "report_delta_engine", "report_delta_memory", "recommendation_ledger", "independent_case_validation", "score_calibration", "false_negative_analysis", "position_entry_guidance", "buy_card", "market_implied_expectations", "case_ai"]

def ensure_current_model_modules():
    for name in _MODULES:
        module = importlib.import_module(name)
        if getattr(module, "_borsify_release", None) != RELEASE:
            module = importlib.reload(module)
            module._borsify_release = RELEASE
