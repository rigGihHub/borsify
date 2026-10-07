"""Refresh model APIs once when Streamlit retains imports during a hot deploy."""
import importlib

RELEASE = "4.41.5-business-outlook"
_MODULES = ["ecb_fx", "data_acquisition", "data_trust", "source_health_dashboard", "research_merge", "dividend_units", "stockanalysis_fundamentals", "fundamental_acquisition", "scan_snapshot_cache", "analysis_confidence", "purchase_consistency", "business_outlook", "analyst_case", "decision_brief", "first_choice_gate", "business_management_intelligence", "top_pick_explainer", "horizon_rankings", "horizon_alternatives", "up_and_coming", "issuer_report_sources", "report_sources", "report_reader", "report_verification", "report_fetcher", "inflection_engine", "post_report_drift", "report_delta_engine", "report_delta_memory", "recommendation_ledger", "independent_case_validation", "score_calibration", "false_negative_analysis", "position_entry_guidance", "buy_card", "market_implied_expectations", "case_ai"]

def ensure_current_model_modules():
    for name in _MODULES:
        module = importlib.import_module(name)
        if getattr(module, "_borsify_release", None) != RELEASE:
            module = importlib.reload(module)
            module._borsify_release = RELEASE
