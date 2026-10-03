"""Refresh model APIs once when Streamlit retains imports during a hot deploy."""
import importlib

RELEASE = "4.40.0-report-queue"
_MODULES = ["issuer_report_sources", "report_sources", "report_reader", "report_verification", "report_fetcher", "inflection_engine", "post_report_drift", "report_delta_engine", "report_delta_memory", "recommendation_ledger", "independent_case_validation", "score_calibration", "false_negative_analysis", "position_entry_guidance", "buy_card", "market_implied_expectations", "case_ai", "horizon_rankings"]

def ensure_current_model_modules():
    for name in _MODULES:
        module = importlib.import_module(name)
        if getattr(module, "_borsify_release", None) != RELEASE:
            module = importlib.reload(module)
            module._borsify_release = RELEASE
