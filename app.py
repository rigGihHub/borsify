Warning: truncated output (original token count: 134700)
Total output lines: 8363

from __future__ import annotations

import math
import re
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from typing import Any
from urllib.parse import quote

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from fundamental_acquisition import fetch_fundamentals as _fetch_fundamentals_source
from data_acquisition import (
    bulk_price_history as _bulk_price_history_source,
    single_price_history as _single_price_history_source,
    fx_rates_to_sek as _fx_rates_to_sek_source,
    index_snapshot as _index_snapshot_source,
    deep_statements as _deep_statements_source,
)

from idea_radar import fetch_public_idea_flow, map_mentions, build_verified_ideas
from fx import FX_TO_SEK_SYMBOLS, major_currency, quote_amount_to_sek, major_amount_to_sek
from case_journal import assess_case_change, journal_table
from case_breaker import evaluate_case_breakers
from case_alert import evaluate_case_alert
from daily_focus import build_daily_focus, focus_context
from since_last_visit import build_since_last_visit, visit_label
from deep_case_engine import build_deep_metrics, assess_deep_case, deep_rank_key
from earnings_quality import build_earnings_quality_metrics, assess_earnings_quality, apply_earnings_quality_gate
from investment_discipline import build_investment_discipline_metrics, assess_investment_discipline, apply_investment_discipline_gate
from evidence_families import build_evidence_families, evidence_family_rows
from data_trust import add_data_trust
from fundamental_data_confidence import assess_fundamental_data_confidence
from decision_language import simplify_decision_text
from fundamental_redundancy import assess_fundamental_redundancy
from search_filters import apply_country_price_filters
from search_horizon import SEARCH_HORIZONS, apply_search_horizon
from search_explanation import (
    intent_match_reason, horizon_match_reason, requirement_statuses,
    main_risk_text, data_status_text, near_miss_reason,
)
from fundamental_cache import clear_fundamentals_cache, CACHE_MAX_AGE_HOURS
from scan_snapshot_cache import get_scan_snapshot, put_scan_snapshot, clear_scan_snapshots
from first_choice_gate import add_first_choice_gate
from buy_now_selection import select_buy_now
from price_batching import partial_fallback_symbols, symbol_batches
from first_choice_audit import build_first_choice_record, save_first_choice_records
try:
    # Streamlit Cloud can briefly retain an older imported module while deploying a
    # commit that adds a new helper. Cold-start history is optional and must never
    # prevent the core application from starting.
    from first_choice_audit import latest_first_choice
except ImportError:
    def latest_first_choice(*_args, **_kwargs):
        return None
from up_and_coming import select_up_and_coming
from scan_pipeline import assess_price_history
from staged_scan_validation import validate_candidate_pool, activation_readiness
from prefilter_history import save_prefilter_validation, get_prefilter_validation_history
from inflection_engine import build_inflection_metrics, assess_inflection, apply_inflection_gate, inflection_rank_value
from mispricing_engine import build_mispricing_assessment, apply_mispricing_gate, mispricing_rank_value
from sector_valuation import sector_aware_valuation
from scenario_engine import build_scenarios
from fundamental_value_range import build_fundamental_value_range
from case_quality_gate import build_case_quality_gate, case_gate_rank_key
from catalyst_engine import build_catalyst_assessment
from why_now_engine import build_why_now_assessment
from news_impact_engine import build_news_impact_assessment
from news_flow_monitor import build_news_flow_monitor
from news_surprise_response import build_news_surprise_response
from news_event_memory import apply_news_event_memory
from fresh_change_detector import build_fresh_change
from fundamental_change_radar import add_fundamental_change_radar
from estimate_revision_radar import add_estimate_revision_radar
from expectation_acceleration_engine import build_expectation_acceleration
from expectation_change import build_expectation_change
from post_report_drift import build_post_report_drift
from report_delta_engine import build_report_delta
from report_fetcher import verify_primary_report_from_events
from report_verification import report_data_provenance
from capital_allocation_insider_radar import build_capital_allocation_insider_radar
from management_signal_layer import build_management_signal
from management_signal_memory import snapshot_from_management_signal, previous_management_snapshot, save_management_snapshot, compare_management_signal_memory, ensure_management_signal_memory_table
from consensus_change_engine import build_consensus_change
from consensus_change_memory import snapshot_from_result, previous_snapshot, save_snapshot, compare_consensus_memory, ensure_consensus_memory_table
from crowded_narrative import build_crowded_narrative
from expectation_gap import build_expectation_gap
from report_delta_memory import snapshot_from_report_delta, previous_report_snapshot, save_report_snapshot, compare_report_delta_memory, ensure_report_delta_memory_table
from change_confirmation_engine import build_change_confirmation
from confirmed_why_now import build_confirmed_why_now
from sector_readthrough_engine import add_sector_readthrough
from value_chain_readthrough_engine import add_value_chain_readthrough
from verified_relationship_engine import add_verified_relationships, load_verified_relationships
from relationship_data_builder import relationship_registry_health
from relationship_change_radar import add_relationship_change_radar
from momentum_12_1 import momentum_12_1_return, momentum_12_1_score, momentum_12_1_label
from idiosyncratic_volatility import apply_idiosyncratic_volatility
from short_term_engine import assess_short_term_case, short_term_rank_key
from short_edge_lab import (
    build_point_in_time_short_signals, add_forward_returns, evaluate_thresholds,
    walk_forward_threshold_test, component_bucket_analysis, summarize_edge,
)
from daytrade_validation import (
    build_point_in_time_daytrade, evaluate_daytrade, walk_forward_fixed_gate,
    validation_grade, compare_horizons,
)
from daytrade_universe_validation import (
    split_downloaded_histories, validate_universe, universe_validation_label,
)
from recommendation_ledger import (
    build_recommendation_records, evaluate_record_from_history,
    outcome_summary, outcome_summary_by_horizon, calibration_by_final_score, score_calibration_warning, calibration_by_gate, calibration_by_deal_conviction,
)
from recommendation_relevance import apply_recommendation_relevance
from recommendation_failure_analysis import (
    failed_recommendation_analysis, failure_pattern_summary,
    failure_pattern_analysis, failure_pattern_overview,
)
from independent_case_validation import independence_audit, independent_case_sample
from false_negative_analysis import (
    false_negative_analysis, false_negative_summary, rejection_rule_audit,
    rejection_rule_audit_summary,
)
from recommendation_learning import (
    learning_summary, learning_tables, score_band_monotonicity, data_limits_note,
    MIN_COHORT,
)
from signal_ablation import short_signal_ablation, ablation_summary, MIN_ABLATION_CASES
from literature_signal_validation import (
    validate_literature_signals, literature_signal_summary, MIN_SIGNAL_CASES, MIN_GROUP_CASES,
)
from news_underreaction_validation import validation_table as news_underreaction_validation_table, validation_summary as news_underreaction_validation_summary, MIN_TOTAL_CASES as NEWS_UNDERREACTION_MIN_CASES, MIN_GROUP_CASES as NEWS_UNDERREACTION_MIN_GROUP
from expectation_gap_validation import validation_table as expectation_gap_validation_table, validation_summary as expectation_gap_validation_summary, MIN_TOTAL_CASES as EXPECTATION_GAP_MIN_CASES, MIN_GROUP_CASES as EXPECTATION_GAP_MIN_GROUP
from prospective_signal_scorecard import build_prospective_signal_scorecard, scorecard_summary as prospective_signal_scorecard_summary, STATUS_REVIEW as SCORECARD_REVIEW, STATUS_SUPPORT as SCORECARD_SUPPORT
from research_kill_promote_queue import build_research_queue, research_queue_summary, ACTION_REVIEW as RESEARCH_REVIEW, ACTION_PROMOTE as RESEARCH_PROMOTE
from research_review_dossier import build_review_dossiers, dossier_summary as research_dossier_summary
from research_dossier_robustness import apply_dossier_robustness
from research_incremental_value import apply_incremental_value
from research_cost_turnover import apply_cost_turnover
from research_data_quality import apply_data_quality
from research_signal_decision_gate import apply_signal_decision_gate, decision_gate_summary, DECISION_PAUSE as SIGNAL_GATE_PAUSE, DECISION_PROMOTE as SIGNAL_GATE_PROMOTE
from signal_governance import (
    build_signal_governance, signal_governance_summary,
    ACTION_KEEP, ACTION_MIXED, ACTION_DEEMPHASISE, ACTION_RETIRE, ACTION_WAIT,
    MIN_REVIEW_HORIZONS, MIN_RETIRE_HORIZONS, MIN_REVIEW_CASES, MIN_RETIRE_CASES,
)
from score_calibration import score_calibration_table, score_calibration_summary, MIN_CALIBRATION_CASES, MIN_BAND_CASES
from champion_challenger import (
    champion_challenger_table, challenger_governance, challenger_summary,
    ACTION_CONTINUE as CHALLENGER_CONTINUE, ACTION_KEEP as CHALLENGER_KEEP,
)

from prospective_challenger_registry import (
    registry_table as prospective_registry_table, prospective_challenger_results,
    prospective_governance, prospective_summary, default_prospective_challengers, STATUS_CANDIDATE as PROSPECTIVE_CANDIDATE,
)
from model_promotion_protocol import (
    model_promotion_protocol, promotion_summary, rollback_plan,
    STATUS_REVIEW as PROMOTION_REVIEW, STATUS_BLOCK as PROMOTION_BLOCK,
)
from model_change_log import model_change_log_table
from production_model_registry import registry_summary, registry_history
from production_policy_registry import policy_registry_summary, policy_registry_history
from policy_health_monitor import policy_health_table, policy_health_summary
from policy_root_cause_diagnostics import policy_root_cause_table, policy_root_cause_summary
from evidence_maturity_dashboard import build_evidence_maturity_dashboard, evidence_maturity_summary
from model_health_monitor import model_health_table, model_health_summary
from root_cause_diagnostics import prepare_root_cause_sample, root_cause_table, root_cause_summary
from failure_cohort_diagnostics import prepare_failure_cohort_sample, failure_cohort_table, failure_cohort_summary
from interaction_diagnostics import prepare_interaction_sample, interaction_archetype_table, interaction_archetype_summary
from regime_archetype_diagnostics import regime_archetype_table, regime_archetype_consistency, regime_archetype_summary
from regime_selection_policy import regime_selection_policy_table, regime_selection_policy_summary
from prospective_policy_registry import (
    registry_table as prospective_policy_registry_table, prospective_policy_results,
    prospective_policy_governance, prospective_policy_summary,
    STATUS_CANDIDATE as PROSPECTIVE_POLICY_CANDIDATE,
)
from policy_promotion_protocol import (
    policy_promotion_protocol, policy_promotion_summary,
    STATUS_REVIEW as POLICY_PROMOTION_REVIEW, STATUS_BLOCK as POLICY_PROMOTION_BLOCK,
)
from case_plan import apply_case_plans
from horizon_rankings import top_three, top_ranked, add_horizon_scores
from horizon_signals import add_action_signals, signal_legend
from entry_timing import add_entry_timing, assess_entry_timing
from decision_axes import add_company_quality, assess_company_quality
from position_entry_guidance import add_position_entry_guidance, assess_position_entry
from good_deal import add_good_deal, assess_good_deal
from negative_overreaction import add_negative_overreaction, assess_negative_overreaction
from mispriced_acceleration import add_mispriced_acceleration, assess_mispriced_acceleration
from hidden_inflection import add_hidden_inflection, assess_hidden_inflection
from quality_compounder_ignored import add_quality_compounder_ignored, assess_quality_compounder_ignored
from underfollowed_quality import add_underfollowed_quality, assess_underfollowed_quality
from earnings_power_noise import add_earnings_power_noise, assess_earnings_power_noise
from operating_leverage_setup import add_operating_leverage_setup, assess_operating_leverage_setup
from balance_sheet_optionality import add_balance_sheet_optionality, assess_balance_sheet_optionality
from cash_conversion_inflection import add_cash_conversion_inflection, assess_cash_conversion_inflection
from margin_recovery_before_consensus import add_margin_recovery_before_consensus, assess_margin_recovery_before_consensus
from revision_breadth import add_revision_breadth, assess_revision_breadth
from deal_conviction import add_deal_conviction, assess_deal_conviction
from exceptional_deal_nose import add_exceptional_deal_nose, assess_exceptional_deal
from value_trap_discriminator import add_value_trap_test, assess_value_trap_vs_market_wrong
from early_mispricing_window import add_early_mispricing_window, assess_early_mispricing_window
from market_blind_spot import add_market_blind_spot, assess_market_blind_spot
from catalyst_to_recognition import add_catalyst_to_recognition, assess_catalyst_to_recognition
from recognition_window import add_recognition_window, assess_recognition_window
from decision_brief import add_decision_briefs, build_decision_brief
from runtime_diagnostics import record_runtime_issue, resolve_runtime_issue, runtime_health
from market_implied_expectations import add_market_implied_expectations, assess_market_implied_expectations
from data_failure_transparency import add_failure_transparency, assess_failure_transparency
from source_health_dashboard import build_source_health_rows, summarize_source_health
from analysis_confidence import add_analysis_confidence, assess_analysis_confidence
from confidence_decision_support import add_confidence_adjusted_decision, assess_confidence_adjusted_decision
from decision_quality_calibration import calibration_table as decision_quality_table, compare_strong_idea_groups, MIN_CASES_PER_QUADRANT
from model_health import assess_model_health
from model_risk_register import build_model_risk_register, summarize_model_risks
from risk_to_roadmap import build_risk_roadmap, roadmap_focus
from roadmap_execution_guard import build_execution_plan, next_safe_work_item
from business_management_intelligence import add_business_management_intelligence, assess_business_management_intelligence
from sector_kpi_engine import extract_sector_kpis
from kpi_inflection import add_kpi_inflection, assess_kpi_inflection
from inflection_sequence import events_from_snapshot, save_events, history as inflection_sequence_history, summarize_sequence
from false_start_confirmation import classify_early_signals, summarize_false_starts, calibration_by_outcome
from signal_evidence_lab import build_signal_evidence, redundancy_matrix, redundancy_pairs, lab_summary
from signal_governance import nominate_signal_actions, governance_summary
from management_promise_delivery import parse_explicit_guidance, save_management_promises, promises_for_symbol, assess_promise_delivery, ensure_management_promise_table
from top_pick_explainer import explain_top_pick
from challenger_path import challenger_paths
from horizon_signal_changes import add_change_signals, dropped_from_top10
from horizon_change_reasons import add_change_reasons, snapshot_details
from relative_strength import add_relative_strength
from case_readiness import add_case_readiness
from decision_tiebreaker import rank_close_daily_candidates
from finalist_selection import select_deep_finalist_pool
from investment_company_engine import add_investment_company_context
from near_buy import near_buy_candidates
from portfolio_advisor import assess_holding
from market_universe import load_avanza_universe, universe_symbols, coverage_table, breadth_summary, audit_catalog, catalog_integrity_summary
from universe_manager import nordic_total, universe_health, scan_result_user_text
from universe_quality import apply_universe_quality, filter_rankable_universe, quality_summary
from qc_history import evolve_qc_state, is_quarantined, scan_health, quarantine_summary, should_record_qc_outcome
from case_ai import build_case_ai_input, build_case_ai_instructions, local_case_explanation
from ai_cost import token_usage, estimate_usage_cost, format_cost_usd
from user_score import add_user_scores

from edge_lab import (
    build_technical_history, summarize_backtest, summarize_universe_backtest,
    build_market_regime_history, summarize_backtest_by_regime, summarize_universe_backtest_by_regime,
    walk_forward_backtest, summarize_trading_friction, simulate_portfolio_backtest,
)

try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore

try:
    from supabase import Client, create_client
except Exception:
    Client = Any  # type: ignore
    create_client = None

APP_VERSION = "4.39.2"

def _borsify_today() -> str:
    """Runtime calendar date for point-in-time snapshots; never hardcode release date."""
    return pd.Timestamp.now(tz="Europe/Stockholm").date().isoformat()

APP_NAME = "Borsify"
APP_DOMAIN = "borsify.se"
from discovery_engine import build_discovery_pool, discovery_coverage_summary
from missed_winners_engine import build_universe_snapshot, evaluate_snapshot_cohort, missed_winner_summary, HORIZONS as MISSED_WINNER_HORIZONS
from missed_winner_patterns import build_miss_pattern_table, miss_pattern_summary
from discovery_learning_loop import build_discovery_learning_proposals, discovery_learning_summary
from discovery_champion_challenger import discovery_selection_flags, registry_table as discovery_registry_table, prospective_discovery_results, discovery_challenger_summary

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "borsify.db"
UNIVERSE_PATH = APP_DIR / "universe.csv"
AVANZA_UNIVERSE_PATH = APP_DIR / "avanza_universe.csv"

# Beginner-friendly discovery goals used by the sidebar search.
# Keep this as one shared source of truth so the UI cannot reference an
# undefined name after copy/refactor changes.
DISCOVERY_INTENTS = [
    "Bästa möjligheter just nu",
    "Bra långsiktig investering",
    "Utdelningsaktier",
    "Billiga kvalitetsbolag",
    "Aktier som fallit mycket",
    "Kortsiktigt köpläge",
    "Stabilare aktier",
]

OMXS30_TICKERS = [
    "ABB.ST", "ADDT-B.ST", "ALFA.ST", "ASSA-B.ST", "AZN.ST", "ATCO-A.ST",
    "BOL.ST", "EPI-A.ST", "EQT.ST", "ERIC-B.ST", "ESSITY-B.ST", "EVO.ST",
    "HM-B.ST", "HEXA-B.ST", "INDU-C.ST", "INVE-B.ST", "LIFCO-B.ST", "NIBE-B.ST",
    "NDA-SE.ST", "SAAB-B.ST", "SAND.ST", "SCA-B.ST", "SEB-A.ST", "SHB-A.ST",
    "SKF-B.ST", "SWED-A.ST", "TEL2-B.ST", "TELIA.ST", "VOLV-B.ST", "SKA-B.ST",
]

# Bred svensk bevakningslista. Detta är ett kuraterat urval av likvida svenska
# stor- och medelstora bolag, inte en officiell eller komplett Nasdaq-lista.
SWEDEN_BROAD_TICKERS = list(dict.fromkeys(OMXS30_TICKERS + [
    "AAK.ST", "AFRY.ST", "ALLEI.ST", "ARJO-B.ST", "AXFO.ST", "BALD-B.ST",
    "BEIJ-B.ST", "BETS-B.ST", "BILL.ST", "BIOT.ST", "BUFAB.ST",
    "CAST.ST", "CAT-B.ST", "CINT.ST", "DOM.ST", "ELAN-B.ST", "ELUX-B.ST",
    "EMBRAC-B.ST", "ENGCON-B.ST", "FABG.ST", "GETI-B.ST",
    "HOLM-B.ST", "HUSQ-B.ST", "INDT.ST", "KINV-B.ST", "LATO-B.ST",
    "LUG.ST", "LAGR-B.ST", "MEKO.ST", "MTRS.ST", "MYCR.ST", "NCC-B.ST", "NOBI.ST", "NOLA-B.ST",
    "NP3.ST", "NYF.ST", "PEAB-B.ST", "RATO-B.ST", "SDIP-B.ST", "SECT-B.ST",
    "SINCH.ST", "SOBI.ST", "SSAB-A.ST", "SWECO-B.ST", "HEXPOL-B.ST",
    "SYNSAM.ST", "THULE.ST", "TREL-B.ST", "VIT-B.ST",
    "WALL-B.ST", "WIHL.ST"
]))

# Kuraterade startuniversum för utländska marknader. Fokus ligger på stora och
# relativt likvida bolag för att hålla första internationella versionen robust.
US_LARGE_TICKERS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "BRK-B", "LLY", "AVGO", "JPM",
    "V", "MA", "XOM", "COST", "WMT", "NFLX", "ORCL", "JNJ", "PG", "HD",
    "BAC", "KO", "ABBV", "CVX", "CRM", "AMD", "PEP", "TMO", "CSCO", "MCD",
    "IBM", "GE", "CAT", "GS", "AXP", "AMGN", "TXN", "INTU", "QCOM", "NOW"
]

NORDIC_LARGE_TICKERS = [
    # Danmark
    "NOVO-B.CO", "DSV.CO", "MAERSK-B.CO", "CARL-B.CO", "VWS.CO", "ORSTED.CO", "COLO-B.CO", "GMAB.CO",
    "DANSKE.CO", "PNDORA.CO", "ROCK-B.CO", "TRYG.CO",
    # Norge
    "EQNR.OL", "DNB.OL", "KOG.OL", "TEL.OL", "MOWI.OL", "NHY.OL", "YAR.OL", "ORK.OL",
    "AKRBP.OL", "SALM.OL", "TOM.OL", "GJF.OL",
    # Finland
    "NOKIA.HE", "KNEBV.HE", "SAMPO.HE", "FORTUM.HE", "UPM.HE", "NESTE.HE", "WRT1V.HE", "METSO.HE",
    "STERV.HE", "KESKOB.HE", "ELISA.HE", "ORNBV.HE"
]

GERMANY_LARGE_TICKERS = [
    "SAP.DE", "SIE.DE", "ALV.DE", "DTE.DE", "AIR.DE", "MUV2.DE", "MBG.DE", "BMW.DE", "VOW3.DE",
    "BAS.DE", "BAYN.DE", "DB1.DE", "DHL.DE", "RWE.DE", "IFX.DE", "ADS.DE", "HEN3.DE", "BEI.DE",
    "FRE.DE", "HEI.DE", "MTX.DE", "SY1.DE", "VNA.DE", "CON.DE", "PAH3.DE", "ENR.DE", "SHL.DE", "QIA.DE"
]

UK_LARGE_TICKERS = [
    "AZN.L", "SHEL.L", "HSBA.L", "ULVR.L", "RIO.L", "BP.L", "GSK.L", "REL.L", "LSEG.L", "BA.L",
    "DGE.L", "NG.L", "BATS.L", "GLEN.L", "BARC.L", "LLOY.L", "RR.L", "CPG.L", "AAL.L", "PRU.L",
    "IMB.L", "VOD.L", "STAN.L", "EXPN.L", "III.L", "ANTO.L", "SSE.L", "NWG.L"
]

CANADA_LARGE_TICKERS = [
    "RY.TO", "TD.TO", "SHOP.TO", "ENB.TO", "CNR.TO", "CP.TO", "BMO.TO", "BNS.TO",
    "TRI.TO", "CNQ.TO", "SU.TO", "MFC.TO", "BCE.TO", "T.TO", "WCN.TO", "CSU.TO",
    "ATD.TO", "QSR.TO", "NTR.TO", "ABX.TO", "AEM.TO", "FTS.TO", "SLF.TO", "GWO.TO"
]

FRANCE_LARGE_TICKERS = [
    "MC.PA", "OR.PA", "TTE.PA", "SAN.PA", "AIR.PA", "SU.PA", "BNP.PA", "EL.PA",
    "SAF.PA", "AI.PA", "CS.PA", "RI.PA", "DG.PA", "KER.PA", "HO.PA", "ENGI.PA",
    "VIE.PA", "CAP.PA", "ORA.PA", "GLE.PA", "STLAP.PA", "ML.PA"
]

NETHERLANDS_LARGE_TICKERS = [
    "ASML.AS", "SHELL.AS", "INGA.AS", "ADYEN.AS", "PRX.AS", "PHIA.AS", "HEIA.AS",
    "UNA.AS", "WKL.AS", "AKZA.AS", "ASM.AS", "RAND.AS", "KPN.AS", "NN.AS", "AGN.AS"
]

BELGIUM_LARGE_TICKERS = [
    "ABI.BR", "UCB.BR", "KBC.BR", "GBLB.BR", "AGS.BR", "SOLB.BR", "UMI.BR",
    "ELI.BR", "COLR.BR", "ACKB.BR"
]

ITALY_LARGE_TICKERS = [
    "ENEL.MI", "ENI.MI", "ISP.MI", "UCG.MI", "STM.MI", "RACE.MI", "G.MI",
    "PRY.MI", "LDO.MI", "MB.MI", "TIT.MI", "AMP.MI", "SRG.MI", "TRN.MI"
]

SPAIN_LARGE_TICKERS = [
    "SAN.MC", "IBE.MC", "ITX.MC", "BBVA.MC", "TEF.MC", "REP.MC", "FER.MC",
    "CABK.MC", "AENA.MC", "ACS.MC", "AMS.MC", "GRF.MC"
]

SWITZERLAND_LARGE_TICKERS = [
    "NESN.SW", "ROG.SW", "NOVN.SW", "UBSG.SW", "ABBN.SW", "ZURN.SW", "CFR.SW",
    "SIKA.SW", "GIVN.SW", "LONN.SW", "HOLN.SW", "SCMN.SW", "SGSN.SW", "LOGN.SW"
]

PORTUGAL_LARGE_TICKERS = [
    "EDP.LS", "GALP.LS", "JMT.LS", "BCP.LS", "SON.LS", "REN.LS", "CTT.LS", "SEM.LS"
]

# Ett medvetet begränsat globalt radaruniversum. Syftet är att hitta kandidater över flera
# marknader utan att göra varje Streamlit-körning orimligt tung. Varje region finns kvar
# separat om användaren vill göra en bredare regional analys.
GLOBAL_RADAR_TICKERS = list(dict.fromkeys(
    SWEDEN_BROAD_TICKERS
    + US_LARGE_TICKERS
    + NORDIC_LARGE_TICKERS
    + GERMANY_LARGE_TICKERS
    + UK_LARGE_TICKERS
    + CANADA_LARGE_TICKERS
    + FRANCE_LARGE_TICKERS
    + NETHERLANDS_LARGE_TICKERS
    + BELGIUM_LARGE_TICKERS
    + ITALY_LARGE_TICKERS
    + SPAIN_LARGE_TICKERS
    + SWITZERLAND_LARGE_TICKERS
    + PORTUGAL_LARGE_TICKERS
))

MARKET_CONFIGS = {
    "Sverige + Norge + Danmark": {"currency": "blandat", "benchmark": "VT", "benchmark_name": "Globalt aktieindex (VT)"},
    "Sverige": {"currency": "SEK", "benchmark": "^OMXS30", "benchmark_name": "OMXS30"},
    "USA": {"currency": "USD", "benchmark": "^GSPC", "benchmark_name": "S&P 500"},
    "Norden exkl. Sverige": {"currency": "lokal valuta", "benchmark": None, "benchmark_name": "—"},
    "Tyskland": {"currency": "EUR", "benchmark": "^GDAXI", "benchmark_name": "DAX"},
    "Storbritannien": {"currency": "GBP", "benchmark": "^FTSE", "benchmark_name": "FTSE 100"},
    "Kanada": {"currency": "CAD", "benchmark": "^GSPTSE", "benchmark_name": "S&P/TSX Composite"},
    "Frankrike": {"currency": "EUR", "benchmark": "^FCHI", "benchmark_name": "CAC 40"},
    "Nederländerna": {"currency": "EUR", "benchmark": "^AEX", "benchmark_name": "AEX"},
    "Belgien": {"currency": "EUR", "benchmark": "^BFX", "benchmark_name": "BEL 20"},
    "Italien": {"currency": "EUR", "benchmark": "FTSEMIB.MI", "benchmark_name": "FTSE MIB"},
    "Spanien": {"currency": "EUR", "benchmark": "^IBEX", "benchmark_name": "IBEX 35"},
    "Schweiz": {"currency": "CHF", "benchmark": "^SSMI", "benchmark_name": "SMI"},
    "Portugal": {"currency": "EUR", "benchmark": "PSI20.LS", "benchmark_name": "PSI"},
    "Alla marknader": {"currency": "blandat", "benchmark": "VT", "benchmark_name": "Globalt aktieindex (VT)"},
}

MARKET_UNIVERSES = {
    "Sverige + Norge + Danmark": SWEDEN_BROAD_TICKERS + NORDIC_LARGE_TICKERS,
    "Sverige": SWEDEN_BROAD_TICKERS,
    "USA": US_LARGE_TICKERS,
    "Norden exkl. Sverige": NORDIC_LARGE_TICKERS,
    "Tyskland": GERMANY_LARGE_TICKERS,
    "Storbritannien": UK_LARGE_TICKERS,
    "Kanada": CANADA_LARGE_TICKERS,
    "Frankrike": FRANCE_LARGE_TICKERS,
    "Nederländerna": NETHERLANDS_LARGE_TICKERS,
    "Belgien": BELGIUM_LARGE_TICKERS,
    "Italien": ITALY_LARGE_TICKERS,
    "Spanien": SPAIN_LARGE_TICKERS,
    "Schweiz": SWITZERLAND_LARGE_TICKERS,
    "Portugal": PORTUGAL_LARGE_TICKERS,
    "Alla marknader": GLOBAL_RADAR_TICKERS,
}


PROFILE_WEIGHTS = {
    "Balanserad": {"valuation": .34, "quality": .28, "setup": .18, "income": .08, "risk": .12},
    "Värde": {"valuation": .50, "quality": .22, "setup": .10, "income": .08, "risk": .10},
    "Kvalitet": {"valuation": .20, "quality": .46, "setup": .10, "income": .08, "risk": .16},
    "Utdelning": {"valuation": .20, "quality": .22, "setup": .08, "income": .38, "risk": .12},
    "Turnaround": {"valuation": .27, "quality": .12, "setup": .43, "income": .03, "risk": .15},
}

SIGNAL_KINDS = [
    "Ny i topp 10",
    "Score lyfter",
    "Scoregräns passerad",
    "Målkurs nådd",
    "Kraftigt dagsfall",
    "Score faller",
]

@dataclass
class ScanConfig:
    min_market_cap_bsek: float
    min_turnover_msek: float
    require_positive_earnings: bool
    top_n: int
    profile: str


def _num(value: Any) -> float:
    try:
        if value is None:
            return np.nan
        val = float(value)
        return val if math.isfinite(val) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _pct_change(series: pd.Series, periods: int) -> float:
    s = series.dropna()
    if len(s) <= periods:
        return np.nan
    old, new = _num(s.iloc[-periods - 1]), _num(s.iloc[-1])
    return new / old - 1 if np.isfinite(old) and old != 0 and np.isfinite(new) else np.nan


def _rsi(close: pd.Series, period: int = 14) -> float:
    s = close.dropna().astype(float)
    if len(s) < period + 2:
        return np.nan
    delta = s.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return _num((100 - 100 / (1 + rs)).iloc[-1])


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fundamentals(symbol: str) -> dict[str, Any]:
    """Cached-compatible wrapper around the dedicated fundamental acquisition layer."""
    payload, health = _fetch_fundamentals_source(symbol, DB_PATH, major_currency, CACHE_MAX_AGE_HOURS)
    st.session_state.setdefault("bq_source_health_fundamentals", {})[symbol] = health
    payload["Fundamental source status"] = str(health.get("status") or "")
    payload["Fundamental source errors"] = "; ".join(map(str, health.get("errors") or []))
    payload["Fundamental source attempts"] = int(health.get("attempts") or 0) if isinstance(health.get("attempts"), (int,float)) else 0
    payload["Fundamental circuit open"] = bool(health.get("circuit_open"))
    return payload

@st.cache_data(ttl=900, show_spinner=False)
def fetch_bulk_price_history(symbols: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    """Cached wrapper around the external market-data acquisition layer."""
    result, health = _bulk_price_history_source(symbols)
    st.session_state["bq_source_health_bulk_prices"] = health
    return result

@st.cache_data(ttl=900, show_spinner=False)
def fetch_single_price_history(symbol: str) -> pd.DataFrame:
    """Cached fallback wrapper around the external market-data acquisition layer."""
    result, health = _single_price_history_source(symbol)
    st.session_state.setdefault("bq_source_health_single_prices", {})[symbol] = health
    return result

def _price_snapshot(symbol: str, hist: pd.DataFrame, fundamentals: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {"Ticker": symbol}
    if hist is None or hist.empty or "Close" not in hist.columns:
        row["error"] = "Ingen kurshistorik"
        return row
    hist = hist.dropna(subset=["Close"]).copy()
    if hist.empty:
        row["error"] = "Ingen kurshistorik"
        return row
    close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
    if close.empty:
        row["error"] = "Ingen giltig stängningskurs"
        return row
    price = _num(close.iloc[-1]); prev = _num(close.iloc[-2]) if len(close) >= 2 else np.nan
    high_52, low_52 = _num(close.max()), _num(close.min())
    sma50 = _num(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else np.nan
    sma200 = _num(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else np.nan
    avg20_volume = last_volume = np.nan
    if "Volume" in hist.columns:
        volume = pd.to_numeric(hist["Volume"], errors="coerce")
        avg20_volume, last_volume = _num(volume.tail(20).mean()), _num(volume.iloc[-1])
    market_cap = _num(fundamentals.get("Börsvärde BSEK"))
    target = _num(fundamentals.get("Analytikermål"))
    last_ts = pd.to_datetime(close.index[-1], errors="coerce")
    price_date = last_ts.date().isoformat() if not pd.isna(last_ts) else "—"
    row.update(fundamentals)
    row.update({
        "Pris": price, "Prisdatum": price_date,
        "Dagsförändring": price / prev - 1 if np.isfinite(prev) and prev != 0 else np.nan,
        "1 mån": _pct_change(close, 21), "3 mån": _pct_change(close, 63), "6 mån": _pct_change(close, 126),
        "12–1 momentum": momentum_12_1_return(close),
        "12–1 momentum score": momentum_12_1_score(momentum_12_1_return(close)),
        "12–1 momentum status": momentum_12_1_label(momentum_12_1_return(close)),
        "1 år": _pct_change(close, min(251, max(len(close) - 1, 1))),
        "52v från topp": price / high_52 - 1 if np.isfinite(high_52) and high_52 else np.nan,
        "52v från botten": price / low_52 - 1 if np.isfinite(low_52) and low_52 else np.nan,
        "SMA50": sma50, "SMA200": sma200,
        "Avstånd SMA200": price / sma200 - 1 if np.isfinite(sma200) and sma200 else np.nan,
        "RSI14": _rsi(close),
        "Volymkvot": last_volume / avg20_volume if np.isfinite(avg20_volume) and avg20_volume > 0 else np.nan,
        "Omsättning lokal M/dag": avg20_volume * price / 1e6 if np.isfinite(avg20_volume) and np.isfinite(price) else np.nan,
        "Omsättning MSEK/dag": avg20_volume * price / 1e6 if np.isfinite(avg20_volume) and np.isfinite(price) else np.nan,
        "Analytikerpotential": target / price - 1 if np.isfinite(target) and np.isfinite(price) and price > 0 else np.nan,
        "Yahoo": f"https://finance.yahoo.com/quote/{quote(symbol)}", "_history": hist.tail(260),
    })
    return row


@st.cache_data(ttl=900, show_spinner=False)
def fetch_fx_rates_to_sek(currencies: tuple[str, ...]) -> dict[str, float]:
    """Cached wrapper around FX acquisition; source health is retained for diagnostics."""
    rates, health = _fx_rates_to_sek_source(currencies, FX_TO_SEK_SYMBOLS, major_currency)
    st.session_state["bq_source_health_fx"] = health
    return rates

def add_sek_conversions(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float], list[str]]:
    """Add comparable SEK price, market-cap and turnover columns without changing source values."""
    if df.empty:
        return df.copy(), {"SEK": 1.0}, []
    out = df.copy()
    quote_ccy = out.get("Valuta", pd.Series("SEK", index=out.index)).fillna("SEK").astype(str)
    fin_ccy = out.get("Finansiell valuta", quote_ccy).fillna(quote_ccy).astype(str)
    currencies = tuple(sorted(set(quote_ccy.tolist() + fin_ccy.tolist())))
    rates = fetch_fx_rates_to_sek(currencies)
    missing = sorted({major_currency(c) for c in currencies if major_currency(c) not in rates and major_currency(c) != "SEK"})

    out["Pris SEK"] = [quote_amount_to_sek(v, c, rates) for v, c in zip(out.get("Pris", pd.Series(np.nan, index=out.index)), quote_ccy)]
    local_cap = out.get("Börsvärde lokal mdr", out.get("Börsvärde BSEK", pd.Series(np.nan, index=out.index)))
    out["Börsvärde BSEK"] = [major_amount_to_sek(v, c, rates) for v, c in zip(local_cap, fin_ccy)]
    local_turn = out.get("Omsättning lokal M/dag", out.get("Omsättning MSEK/dag", pd.Series(np.nan, index=out.index)))
    out["Omsättning MSEK/dag"] = [quote_amount_to_sek(v, c, rates) for v, c in zip(local_turn, quote_ccy)]
    out["FX till SEK"] = [rates.get(major_currency(c), np.nan) for c in quote_ccy]
    return out, rates, missing


def fmt_price_with_sek(row: pd.Series | dict[str, Any]) -> str:
    price = _num(row.get("Pris"))
    ccy = str(row.get("Valuta") or "")
    sek = _num(row.get("Pris SEK"))
    if not np.isfinite(price):
        return "—"
    major = major_currency(ccy)
    base = f"{price:.2f} {ccy}".strip()
    if major == "SEK" or not np.isfinite(sek):
        return base
    return f"{base} · ≈ {sek:,.0f} SEK".replace(",", " ")


@st.cache_data(ttl=900, show_spinner=False)
def fetch_index_snapshot(symbol: str = "^OMXS30") -> dict[str, float]:
    """Cached wrapper around benchmark acquisition."""
    result, health = _index_snapshot_source(symbol)
    st.session_state["bq_source_health_index"] = health
    return result

def _percentile_score(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    valid = s.notna()
    out = pd.Series(50.0, index=s.index, dtype=float)
    if valid.sum() >= 2:
        pct = s[valid].rank(pct=True, method="average") * 100
        if not higher_is_better:
            pct = 100 - pct + (100 / valid.sum())
        out.loc[valid] = pct.clip(0, 100)
    return out


def _sector_percentile_score(df: pd.DataFrame, column: str, higher_is_better: bool = True) -> pd.Series:
    """Compare valuation mainly inside sector; fall back to whole universe when sector sample is tiny."""
    result = _percentile_score(df[column], higher_is_better)
    sectors = df["Sektor"].fillna("Okänd")
    for sector, idx in sectors.groupby(sectors).groups.items():
        if sector == "Okänd" or len(idx) < 3:
            continue
        local = _percentile_score(df.loc[idx, column], higher_is_better)
        result.loc[idx] = local
    return result


def _mean_scores(parts: list[pd.Series]) -> pd.Series:
    return pd.concat(parts, axis=1).mean(axis=1) if parts else pd.Series(dtype=float)


def _risk_score(out: pd.DataFrame) -> pd.Series:
    risk = pd.Series(75.0, index=out.index)
    debt = pd.to_numeric(out["Skuld/eget kapital"], errors="coerce")
    roe = pd.to_numeric(out["ROE"], errors="coerce")
    margin = pd.to_numeric(out["Vinstmarginal"], errors="coerce")
    draw = pd.to_numeric(out["52v från topp"], errors="coerce")
    dist = pd.to_numeric(out["Avstånd SMA200"], errors="coerce")
    m3 = pd.to_numeric(out["3 mån"], errors="coerce")
    risk -= np.where(debt > 300, 25, np.where(debt > 200, 15, 0))
    risk -= np.where(roe < 0, 18, 0)
    risk -= np.where(margin < 0, 18, 0)
    risk -= np.where(draw < -.50, 16, np.where(draw < -.35, 8, 0))
    risk -= np.where((dist < -.10) & (m3 < -.15), 18, 0)
    return risk.clip(0, 100)


def add_scores(df: pd.DataFrame, profile: str) -> pd.DataFrame:
    out = df.copy()
    pe = out["P/E"].where(out["P/E"].between(2, 100))
    fpe = out["Forward P/E"].where(out["Forward P/E"].between(2, 100))
    pb = out["P/B"].where(out["P/B"].between(.1, 30))
    ev = out["EV/EBITDA"].where(out["EV/EBITDA"].between(0, 80))
    fcfy = out["FCF-yield"].where(out["FCF-yield"].between(-.5, .5))
    temp = out.assign(**{"P/E": pe, "Forward P/E": fpe, "P/B": pb, "EV/EBITDA": ev, "FCF-yield": fcfy})

    # v2.91: valuation is sector-aware. Different business models use different
    # valuation lenses, and missing metrics no longer silently contribute neutral 50s.
    # Analyst target potential remains deliberately excluded from Valuation.
    valuation_detail = sector_aware_valuation(temp)
    valuation = valuation_detail["Värdering"]
    debt = out["Skuld/eget kapital"].where(out["Skuld/eget kapital"].between(0, 1000))
    quality = _mean_scores([
        _percentile_score(out["ROE"].clip(-1, 2), True), _percentile_score(out["Vinstmarginal"].clip(-1, 1), True),
        _percentile_score(out["Omsättningstillväxt"].clip(-1, 2), True), _percentile_score(out["Vinsttillväxt"].clip(-1, 3), True),
        _percentile_score(debt, False),
    ])

    drawdown = pd.to_numeric(out["52v från topp"], errors="coerce")
    dip_score = pd.Series(100 * np.exp(-((drawdown + .18) / .18) ** 2), index=out.index).where(drawdown.notna(), 50).clip(0, 100)
    rsi = pd.to_numeric(out["RSI14"], errors="coerce")
    rsi_score = pd.Series(100 * np.exp(-((rsi - 43) / 18) ** 2), index=out.index).where(rsi.notna(), 50).clip(0, 100)
    momentum = _percentile_score(out["3 mån"].clip(-.8, 1.5), True)
    trend = pd.Series(50.0, index=out.index)
    dist200 = pd.to_numeric(out["Avstånd SMA200"], errors="coerce")
    trend.loc[dist200 >= 0] = 70; trend.loc[(dist200 < 0) & (dist200 >= -.10)] = 50
    trend.loc[(dist200 < -.10) & (dist200 >= -.25)] = 30; trend.loc[dist200 < -.25] = 10
    setup = .35 * dip_score + .25 * rsi_score + .25 * momentum + .15 * trend

    dy = out["Direktavkastning"].where(out["Direktavkastning"].between(0, .15))
    payout = out["Utdelningsandel"].where(out["Utdelningsandel"].between(0, 2))
    payout_quality = pd.Series(50.0, index=out.index)
    payout_quality.loc[payout.between(.25, .75)] = 85
    payout_quality.loc[payout.between(.75, 1.0)] = 65
    payout_quality.loc[payout > 1.0] = 25
    income = .70 * _percentile_score(dy, True) + .30 * payout_quality
    risk = _risk_score(out)

    out["Värdering"] = valuation.round(1)
    for col in ["Värderingsprofil", "Värderingsunderlag", "Värderingsmått antal", "Värdering täckning", "Värderingsnotis"]:
        out[col] = valuation_detail[col]
    out["Kvalitet"] = quality.round(1); out["Marknadsläge"] = setup.round(1)
    out["Utdelning"] = income.round(1); out["Risk"] = risk.round(1)
    w = PROFILE_WEIGHTS[profile]
    base = sum(out[name] * w[key] for name, key in [("Värdering","valuation"),("Kvalitet","quality"),("Marknadsläge","setup"),("Utdelning","income"),("Risk","risk")])
    coverage_cols = ["P/E", "Forward P/E", "EV/EBITDA", "FCF-yield", "ROE", "Vinstmarginal", "Omsättningstillväxt", "Skuld/eget kapital"]
    coverage = out[coverage_cols].notna().mean(axis=1)
    out["Datatäckning"] = coverage
    out["Borsify Score"] = (base * (.80 + .20 * coverage)).round(1).clip(0, 100)
    out["Riskflaggor"] = out.apply(_risk_flags, axis=1)
    out["Signal"] = out.apply(_signal_label, axis=1)
    out["Varför"] = out.apply(_why_text, axis=1)

    # v2.1: three distinct horizons. These are screening scores, not forecasts.
    # v2.27: growth no longer includes FCF-yield. FCF-yield is a valuation/cash-return
    # measure and previously leaked the same information into both valuation and growth.
    growth = _mean_scores([
        _percentile_score(out["Omsättningstillväxt"].clip(-1, 2), True),
        _percentile_score(out["Vinsttillväxt"].clip(-1, 3), True),
    ])
    invest = .34 * valuation + .31 * quality + .18 * risk + .12 * growth + .05 * setup

    vol_ratio = pd.to_numeric(out.get("Volymkvot", pd.Series(np.nan, index=out.index)), errors="coerce")
    vol_score = ((vol_ratio - .7) / 1.1 * 100).clip(0, 100).fillna(45)
    dist200 = pd.to_numeric(out["Avstånd SMA200"], errors="coerce")
    trend_score = pd.Series(45.0, index=out.index)
    trend_score.loc[dist200.between(0, .20)] = 85
    trend_score.loc[dist200.between(-.05, 0, inclusive="left")] = 65
    trend_score.loc[dist200 > .20] = 65
    trend_score.loc[dist200 < -.10] = 20
    swing = .48 * setup + .18 * trend_score + .17 * vol_score + .10 * risk + .07 * quality

    daily = pd.to_numeric(out["Dagsförändring"], errors="coerce")
    draw = pd.to_numeric(out["52v från topp"], errors="coerce")
    rsi_num = pd.to_numeric(out["RSI14"], errors="coerce")
    selloff = ((-daily - .015) / .10 * 100).clip(0, 100).fillna(0)
    draw_score = ((-draw - .08) / .32 * 100).clip(0, 100).fillna(25)
    oversold = ((48 - rsi_num) / 23 * 100).clip(0, 100).fillna(30)
    reversal = .27 * selloff + .20 * draw_score + .18 * oversold + .16 * quality + .12 * risk + .07 * valuation
    severe_mask = out["Riskflaggor"].astype(str).apply(lambda x: any(term in x for term in SEVERE_RISK_TERMS))
    reversal = reversal.where(~severe_mask, np.minimum(reversal, 62))

    out["Growth Score"] = growth.round(1).clip(0, 100)
    out["INVEST Score"] = invest.round(1).clip(0, 100)
    out["SWING Score"] = swing.round(1).clip(0, 100)
    out["REVERSAL Score"] = reversal.round(1).clip(0, 100)
    return out.sort_values(["Borsify Score", "Datatäckning"], ascending=[False, False])


def _risk_flags(row: pd.Series) -> str:
    flags: list[str] = []
    pe, roe, debt, margin = map(_num, [row.get("P/E"), row.get("ROE"), row.get("Skuld/eget kapital"), row.get("Vinstmarginal")])
    draw, dist, m3, cov = map(_num, [row.get("52v från topp"), row.get("Avstånd SMA200"), row.get("3 mån"), row.get("Datatäckning")])
    if not np.isfinite(pe) or pe <= 0: flags.append("svag/okänd vinstvärdering")
    if np.isfinite(roe) and roe < 0: flags.append("negativ ROE")
    if np.isfinite(margin) and margin < 0: flags.append("negativ marginal")
    if np.isfinite(debt) and debt > 200: flags.append("hög skuldsättning")
    if np.isfinite(draw) and draw < -.45: flags.append(">45 % från 52v-topp")
    if np.isfinite(dist) and dist < -.10 and np.isfinite(m3) and m3 < -.15: flags.append("fallande lång trend")
    if np.isfinite(cov) and cov < .50: flags.append("begränsad information om bolagets ekonomi")
    return ", ".join(flags) if flags else "—"


def _signal_label(row: pd.Series) -> str:
    score = _num(row.get("Borsify Score")); flags = str(row.get("Riskflaggor", ""))
    severe = any(x in flags for x in ["negativ ROE", "negativ marginal", "hög skuldsättning", "fallande lång trend"])
    if score >= 78 and not severe: return "Starkt fyndläge"
    if score >= 68: return "Intressant"
    if score >= 58: return "Bevaka"
    return "Svag signal"


def _why_text(row: pd.Series) -> str:
    reasons: list[str] = []
    if _num(row.get("Värdering")) >= 70: reasons.append("billig värdering relativt sektor")
    if _num(row.get("Kvalitet")) >= 70: reasons.append("stark kvalitet")
    if _num(row.get("Marknadsläge")) >= 70: reasons.append("attraktiv rekyl/setup")
    if _num(row.get("Utdelning")) >= 75: reasons.append("stark utdelningsprofil")
    dd, rsi, upside = _num(row.get("52v från topp")), _num(row.get("RSI14")), _num(row.get("Analytikerpotential"))
    if np.isfinite(dd) and -.35 <= dd <= -.08: reasons.append(f"{abs(dd):.0%} under 52v-topp")
    if np.isfinite(rsi) and 30 <= rsi <= 48: reasons.append(f"RSI {rsi:.0f}")
    if np.isfinite(upside) and upside >= .10: reasons.append(f"analytikermål +{upside:.0%}")
    return "; ".join(reasons[:3]) if reasons else "ingen enskild faktor sticker ut"


SEVERE_RISK_TERMS = ["negativ ROE", "negativ marginal", "hög skuldsättning", "fallande lång trend"]


def _daily_case(row: pd.Series, profile: str) -> dict[str, Any]:
    """Create a compact, explainable 'why today' triage without pretending to be a buy recommendation."""
    score = _num(row.get("Borsify Score"))
    setup = _num(row.get("Marknadsläge"))
    quality = _num(row.get("Kvalitet"))
    valuation = _num(row.get("Värdering"))
    coverage = _num(row.get("Datatäckning"))
    daily = _num(row.get("Dagsförändring"))
    rsi = _num(row.get("RSI14"))
    draw = _num(row.get("52v från topp"))
    m3 = _num(row.get("3 mån"))
    flags = str(row.get("Riskflaggor", "—"))
    severe = any(term in flags for term in SEVERE_RISK_TERMS)

    prev = previous_score_snapshot(str(row.get("Ticker")), profile)
    prev_score = _num(prev.get("score")) if prev else np.nan
    delta = score - prev_score if np.isfinite(score) and np.isfinite(prev_score) else np.nan

    # 'Dagens relevans' deliberately remains separate from Borsify Score. It emphasizes
    # current setup and recent score improvement while risk gates can cap the result.
    delta_factor = 50.0 if not np.isfinite(delta) else float(np.clip(50 + delta * 4.0, 0, 100))
    relevance = (
        .55 * (score if np.isfinite(score) else 50)
        + .20 * (setup if np.isfinite(setup) else 50)
        + .10 * (quality if np.isfinite(quality) else 50)
        + .05 * (valuation if np.isfinite(valuation) else 50)
        + .10 * delta_factor
    )
    if np.isfinite(coverage) and coverage < .60:
        relevance -= 5
    if severe:
        relevance = min(relevance - 4, 69)
    # Investmentbolag kräver en annan värderingslogik än vanliga rörelsebolag.
    # Look-through-motorn skapar inget nytt score, men kan stoppa ett investmentbolag
    # från att bli toppcase när substans-/innehavsunderlaget är för svagt eller visar premie.
    investment_cap = _num(row.get("Investmentbolag rankningstak"))
    if bool(row.get("Investmentbolag", False)) and np.isfinite(investment_cap):
        relevance = min(relevance, investment_cap)
    relevance = float(np.clip(relevance, 0, 100))

    if relevance >= 75 and not severe:
        priority = "Hög"
    elif relevance >= 63:
        priority = "Medel"
    else:
        priority = "Låg"

    why_today: list[str] = []
    if np.isfinite(delta) and delta >= 3:
        why_today.append(f"Borsify Score har stigit {delta:+.1f} sedan föregående snapshot")
    elif np.isfinite(delta) and delta <= -3:
        why_today.append(f"Borsify Score har fallit {delta:+.1f} sedan föregående snapshot")
    if np.isfinite(setup) and setup >= 70:
        why_today.append("kursbilden är stark just nu")
    if np.isfinite(rsi) and 32 <= rsi <= 48:
        why_today.append("kursen har nyligen pressats ned utan att grundcaset behöver vara brutet")
    if np.isfinite(draw) and -.35 <= draw <= -.08:
        why_today.append(f"kursen är {abs(draw):.0%} under årets högsta nivå")
    if np.isfinite(m3) and m3 >= .08:
        why_today.append(f"aktien har gått {m3:+.0%} de senaste tre månaderna")
    if np.isfinite(daily) and daily <= -.04:
        why_today.append(f"aktien är ned {abs(daily):.1%} idag – kontrollera om fallet är nyhetsdrivet")
    if bool(row.get("Investmentbolag", False)):
        ic_status = str(row.get("Investmentbolag status") or "")
        if ic_status:
            why_today.insert(0, f"investmentbolag: {ic_status.lower()}")
    if not why_today:
        why_today.append("aktien är stark i helhetsanalysen, men inget tydligt nytt har hänt idag")

    changed: list[str] = []
    if prev:
        mapping = [("Värdering", "valuation"), ("Kvalitet", "quality"), ("Marknadsläge", "setup"), ("Utdelning", "income"), ("Risk", "risk")]
        diffs = []
        for label, key in mapping:
            now = _num(row.get(label)); old = _num(prev.get(key))
            if np.isfinite(now) and np.isfinite(old):
                diffs.append((abs(now-old), label, now-old))
        for _, label, d in sorted(diffs, reverse=True)[:2]:
            if abs(d) >= 1:
                changed.append(f"{label} {d:+.1f}")
    if not changed:
        changed.append("ingen tydlig komponentförändring registrerad ännu")

    caution: list[str] = []
    if flags and flags != "—":
        caution.extend([x.strip() for x in flags.split(",") if x.strip()][:2])
    if np.isfinite(coverage) and coverage < .60:
        caution.append(f"datatäckning bara {coverage:.0%}")
    if bool(row.get("Investmentbolag", False)):
        direct = str(row.get("Investmentbolag direktval") or "")
        if direct in {"Otillräcklig data", "Innehaven direkt kan vara bättre", "Ingen rättvis direktjämförelse"}:
            caution.insert(0, direct.lower())
    if not caution:
        caution.append("inga grova modellflaggor; kontrollera ändå rapport, kassaflöde och aktuell nyhetsbild")

    return {
        "Dagens relevans": round(relevance, 1),
        "Prioritet": priority,
        "Score Δ": delta,
        "Varför idag": "; ".join(why_today[:3]),
        "Förändrat": "; ".join(changed[:2]),
        "Kontrollera": "; ".join(caution[:3]),
        "Severe": severe,
    }


def build_daily_shortlist(df: pd.DataFrame, profile: str, limit: int = 5) -> pd.DataFrame:
    """Rank a small actionable shortlist from already screened shares.

    v3.38 keeps the existing daily relevance model in control. Only genuinely close
    candidates are separated with already-existing evidence quality and relative
    strength, so a tiny score difference no longer decides first place by itself.
    """
    if df.empty:
        return df.copy()

    # Relative strength is calculated against the full filtered scan so its peer/market
    # context is not distorted by looking only at the strongest 15 names. It remains
    # confirmation/tie-break evidence and cannot rescue a weak candidate.
    enriched = add_relative_strength(df)

    # Do not hit history storage for the entire market; the strongest 15 by base score
    # are enough candidates for the daily triage. Case Readiness is an evidence-quality
    # check, not a return forecast, and is used only after the daily shortlist gate.
    pool = enriched.sort_values(["Borsify Score", "Datatäckning"], ascending=[False, False]).head(15).copy()
    pool = add_case_readiness(pool, "long")
    cases = [_daily_case(row, profile) for _, row in pool.iterrows()]
    case_df = pd.DataFrame(cases, index=pool.index)
    for col in case_df.columns:
        pool[col] = case_df[col]

    ranked = rank_close_daily_candidates(pool)
    return ranked.head(limit).copy()


def add_full_deal_evidence(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    """Apply the existing advisory evidence stack without creating a new score."""
    ranked = add_action_signals(df, horizon)
    ranked = add_entry_timing(ranked, horizon)
    ranked = add_company_quality(ranked)
    ranked = add_position_entry_guidance(ranked)
    ranked = add_good_deal(ranked, horizon)
    ranked = add_negative_overreaction(ranked)
    ranked = add_mispriced_acceleration(ranked)
    ranked = add_hidden_inflection(ranked)
    ranked = add_quality_compounder_ignored(ranked, horizon)
    ranked = add_underfollowed_quality(ranked, horizon)
    ranked = add_earnings_power_noise(ranked, horizon)
    ranked = add_operating_leverage_setup(ranked, horizon)
    ranked = add_balance_sheet_optionality(ranked, horizon)
    ranked = add_cash_conversion_inflection(ranked)
    ranked = add_margin_recovery_before_consensus(ranked)
    ranked = add_revision_breadth(ranked)
    ranked = add_deal_conviction(ranked, horizon)
    ranked = add_analysis_confidence(ranked)
    ranked = add_confidence_adjusted_decision(ranked)
    ranked = add_exceptional_deal_nose(ranked, horizon)
    ranked = add_value_trap_test(ranked)
    ranked = add_early_mispricing_window(ranked)
    ranked = add_market_blind_spot(ranked)
    ranked = add_catalyst_to_recognition(ranked)
    ranked = add_recognition_window(ranked)
    ranked = add_market_implied_expectations(ranked)
    ranked = add_decision_briefs(ranked)
    return add_business_management_intelligence(ranked)


def build_evidence_gated_shortlist(df: pd.DataFrame, profile: str, limit: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select today's card from a diverse finalist pool and expose every blocker.

    The gate is deliberately not an alpha score. It only prevents a red entry,
    likely value trap, red company assessment or low-confidence analysis from being
    presented as a strong first choice. The incumbent score remains untouched.
    """
    if df is None or df.empty:
        empty = df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
        return empty, empty
    finalists = build_discovery_pool(df, max_candidates=min(12, len(df)))
    # The first-choice path must use the same specialist-adjusted headline score
    # as horizon lists, history and the recommendation ledger.
    finalists = add_user_scores(finalists)
    finalists = add_full_deal_evidence(finalists, "year")
    finalists = add_case_readiness(finalists, "long")
    # The first screen is explicitly a current-buy surface.  Evidence quality
    # alone is not enough: use the shared purchase and anti-chase gate so a
    # BEVAKA/AVVAKTA case can never be presented as today's strongest buy.
    finalists = select_buy_now(finalists, "medium")
    finalists = add_action_signals(finalists, "medium")
    cases = pd.DataFrame([_daily_case(row, profile) for _, row in finalists.iterrows()], index=finalists.index)
    finalists = finalists.drop(columns=[c for c in cases.columns if c in finalists.columns], errors="ignore").join(cases)

    finalists = add_first_choice_gate(finalists)
    approved = rank_close_daily_candidates(finalists[finalists["Förstaval godkänd"]].copy())
    return approved.head(limit).copy(), finalists


def scan_universe(symbols: list[str], progress_callback=None) -> tuple[pd.DataFrame, list[str]]:
    """Price-first scan with persistent fundamentals caching.

    Stage 1 validates quote/history data before any expensive Yahoo get_info call.
    Stage 2 fetches fundamentals only for symbols that can actually be ranked.
    A 24-hour SQLite cache avoids repeating unchanged fundamentals on reruns or
    after normal Streamlit cache clears.
    """
    symbols = list(dict.fromkeys(symbols))
    rows, errors = [], []
    metrics = {
        "requested": len(symbols),
        "price_usable": 0,
        "price_rejected_before_fundamentals": 0,
        "fundamental_candidates": 0,
        "fundamental_yahoo": 0,
        "fundamental_persistent_cache": 0,
        "single_price_fallbacks": 0,
        "price_batches": 0,
        "empty_price_batches": 0,
        "price_seconds": 0.0,
        "fundamental_seconds": 0.0,
    }

    price_started = time.perf_counter()
    price_map: dict[str, pd.DataFrame] = {}
    completed_prices = 0
    for batch in symbol_batches(symbols, batch_size=40):
        metrics["price_batches"] += 1
        if callable(progress_callback):
            progress_callback("prices", completed_prices, len(symbols))
        batch_map = fetch_bulk_price_history(batch)
        price_map.update(batch_map)
        if not batch_map and len(batch) > 1:
            metrics["empty_price_batches"] += 1
            errors.append(
                f"Kursbatch {metrics['price_batches']}: inget bulksvar för {len(batch)} aktier; "
                "enskilda fallback-anrop hoppades över för att undvika rate-limit/låsning"
            )
        for sym in partial_fallback_symbols(batch, batch_map, max_fallbacks=8):
            metrics["single_price_fallbacks"] += 1
            fallback = fetch_single_price_history(sym)
            if fallback is not None and not fallback.empty:
                price_map[sym] = fallback
        completed_prices += len(batch)
        if callable(progress_callback):
            progress_callback("prices", completed_prices, len(symbols))
    usable_histories: dict[str, pd.DataFrame] = {}

    for sym in symbols:
        hist = price_map.get(sym)
        if hist is None or hist.empty:
            errors.append(f"{sym}: ingen användbar kurshistorik efter batchhämtning")
            metrics["price_rejected_before_fundamentals"] += 1
            continue

        price_gate = assess_price_history(hist)
        if not bool(price_gate.get("usable")):
            errors.append(
                f"{sym}: prisdata stoppad före bolagsdata · "
                f"{price_gate.get('reason','otillräcklig kursdata')}"
            )
            metrics["price_rejected_before_fundamentals"] += 1
            continue

        usable_histories[sym] = hist

    metrics["price_seconds"] = round(time.perf_counter() - price_started, 3)
    metrics["price_usable"] = len(usable_histories)
    metrics["fundamental_candidates"] = len(usable_histories)

    fundamentals: dict[str, dict[str, Any]] = {}
    fundamental_started = time.perf_counter()
    completed_fundamentals = 0
    with ThreadPoolExecutor(max_workers=min(8, max(1, len(usable_histories)))) as executor:
        futures = {executor.submit(fetch_fundamentals, sym): sym for sym in usable_histories}
        for future in as_completed(futures):
            sym = futures[future]
            try:
                data = future.result()
                fundamentals[sym] = data
                source = str(data.get("_Fundamental cache") or "")
                if source == "Yahoo":
                    metrics["fundamental_yahoo"] += 1
                elif source == "beständig cache":
                    metrics["fundamental_persistent_cache"] += 1
            except Exception as exc:
                fundamentals[sym] = {
                    "Namn": sym, "Sektor": "Okänd", "Bransch": "Okänd",
                    "Valuta": "SEK", "Fundamental hämtad": "—",
                }
                errors.append(f"{sym}: information om bolagets ekonomi {type(exc).__name__}")
            completed_fundamentals += 1
            if callable(progress_callback):
                progress_callback("fundamentals", completed_fundamentals, len(usable_histories))
    metrics["fundamental_seconds"] = round(time.perf_counter() - fundamental_started, 3)

    for sym, hist in usable_histories.items():
        row = _price_snapshot(sym, hist, fundamentals.get(sym, {}))
        if row.get("error"):
            errors.append(f"{sym}: {row['error']}")
        else:
            rows.append(row)

    try:
        st.session_state["bq_scan_metrics"] = metrics
    except Exception:
        pass
    return (pd.DataFrame(rows) if rows else pd.DataFrame()), errors



@st.cache_data(ttl=43200, show_spinner=False)
def fetch_deep_statements(symbol: str) -> dict[str, Any]:
    """Fetch deep statements via the dedicated acquisition layer."""
    return _deep_statements_source(symbol)

def build_report_delta_with_provenance(
    inflection_metrics: dict[str, Any],
    post_report: dict[str, Any],
    raw: dict[str, Any] | None,
    row: pd.Series | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Keep Report Delta useful without overstating original-report coverage."""
    source = raw if isinstance(raw, dict) else {}
    result = build_report_delta(inflection_metrics, post_report, source.get("catalyst_events"))
    context = row if row is not None else {}
    verified_report = None
    try:
        verified_report = verify_primary_report_from_events(
            source.get("catalyst_events"),
            str(context.get("Land") or context.get("Landkod") or ""),
        )
    except Exception:
        verified_report = None
    result.update(report_data_provenance(source, verified_report))
    return result

def build_deep_longlist(df: pd.DataFrame, pool_size: int = 6, limit: int = 5) -> pd.DataFrame:
    """Deep-check a small multi-lens finalist pool using multi-year statements.

    Candidate selection keeps the strongest INVEST names but also opens a few slots
    for existing quality, lifetime, reversal and valuation lenses. Final ordering is
    still evidence-gate first; no new weighted mega-score is introduced.
    """
    if df.empty:
        return df.copy()
    # Discovery Engine 2.0: reserve deep-analysis capacity for different ways an
    # excellent stock can surface (one-year, lifetime, quality, valuation, reversal).
    # No new aggregate score is introduced; the existing deep gates remain decisive.
    discovery_pool = build_discovery_pool(df, max_candidates=max(18, pool_size * 2))

    # v3.53 Estimate Revision Radar 2.0: probe a bounded, diversified subset before
    # the final deep slots are locked. The fetch is cached and reused by the later
    # deep analysis. Missing analyst data never earns a slot.
    estimate_probe = discovery_pool.head(min(12, len(discovery_pool))).copy()
    estimate_records: dict[Any, dict[str, Any]] = {}
    if not estimate_probe.empty:
        with ThreadPoolExecutor(max_workers=min(3, len(estimate_probe))) as executor:
            futures = {executor.submit(fetch_deep_statements, str(row["Ticker"])): idx for idx, row in estimate_probe.iterrows()}
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    raw = future.result()
                    metrics = build_inflection_metrics(
                        raw.get("quarterly_income"), raw.get("quarterly_cashflow"),
                        raw.get("eps_trend"), raw.get("eps_revisions"), raw.get("earnings_history"),
                        raw.get("quarterly_balance"), raw.get("earnings_estimate")
                    )
                    _base_row = estimate_probe.loc[idx]
                    sector_kpis = extract_sector_kpis(
                        str(_base_row.get("Sektor") or ""), str(_base_row.get("Bransch") or ""),
                        raw.get("quarterly_income"), raw.get("quarterly_cashflow"), raw.get("quarterly_balance")
                    )
                    acceleration = build_expectation_acceleration(
                        raw.get("eps_trend"), raw.get("eps_revisions"), metrics, estimate_probe.loc[idx]
                    )
                    post_report = build_post_report_drift(
                        raw.get("earnings_history"), raw.get("price_history"), metrics
                    )
                    report_delta = build_report_delta_with_provenance(metrics, post_report, raw, estimate_probe.loc[idx])
                    _symbol = str(estimate_probe.loc[idx].get("Ticker", ""))
                    _report_snap = snapshot_from_report_delta(_symbol, metrics, post_report, report_delta, _borsify_today())
                    try:
                        with _db_connect() as _conn:
                            _report_prev = previous_report_snapshot(_conn, _symbol, _report_snap["report_date"]) if _report_snap else None
                            report_memory = compare_report_delta_memory(_report_snap, _report_prev)
                            save_report_snapshot(_conn, _report_snap)
                            _promises = parse_explicit_guidance(report_delta.get("Report Delta guidance"), _report_snap.get("report_date"), _symbol)
                            save_management_promises(_conn, _promises, _borsify_today())
                    except Exception:
                        report_memory = compare_report_delta_memory(_report_snap, None)
                    owner_snapshot = {**estimate_probe.loc[idx].to_dict(), **(raw.get("fast_info") or {})}
                    owner_signal = build_capital_allocation_insider_radar(
                        raw.get("cashflow"), raw.get("balance"), raw.get("insider_transactions"), owner_snapshot
                    )
                    management_signal = build_management_signal(raw.get("catalyst_events"))
                    _mgmt_snap = snapshot_from_management_signal(_symbol, management_signal, raw.get("catalyst_events"), _borsify_today())
                    try:
                        with _db_connect() as _conn:
                            _mgmt_prev = previous_management_snapshot(_conn, _symbol, _mgmt_snap["signal_key"]) if _mgmt_snap else None
                            management_memory = compare_management_signal_memory(_mgmt_snap, _mgmt_prev)
                            save_management_snapshot(_conn, _mgmt_snap)
                    except Exception:
                        management_memory = compare_management_signal_memory(_mgmt_snap, None)
                    consensus_change = build_consensus_change(
                        raw.get("recommendation_summary"), raw.get("upgrades_downgrades"),
                        raw.get("analyst_price_targets"), estimate_probe.loc[idx], as_of=_borsify_today()
                    )
                    _snap = snapshot_from_result(_symbol, consensus_change, _borsify_today())
                    try:
                        with _db_connect() as _conn:
                            _prev = previous_snapshot(_conn, _symbol, _snap["captured_date"])
                            consensus_memory = compare_consensus_memory(_snap, _prev)
                            save_snapshot(_conn, _snap)
                    except Exception:
                        consensus_memory = compare_consensus_memory(_snap, None)
                    _sequence_context = {**estimate_probe.loc[idx].to_dict(), **metrics, **sector_kpis, **report_delta, **report_memory, **consensus_change}
                    _sequence_context.update(assess_business_management_intelligence(_sequence_context))
                    _sequence_context.update(assess_kpi_inflection(_sequence_context))
                    try:
                        with _db_connect() as _conn:
                            save_events(_conn, events_from_snapshot(_symbol, _sequence_context, _borsify_today()))
                            _seq_hist = inflection_sequence_history(_conn, _symbol)
                            _sequence_summary = summarize_sequence(_seq_hist)
                            _fs_class = classify_early_signals(_seq_hist, _borsify_today())
                            _fs_summary = summarize_false_starts(_fs_class)
                            _latest_fs = _fs_class.sort_values("early_date").iloc[-1]["status"] if not _fs_class.empty else ""
                    except Exception:
                        _sequence_summary = summarize_sequence(None)
                        _fs_summary = summarize_false_starts(None)
                        _latest_fs = ""
                    _combined_change = {**report_memory, **management_memory, **consensus_memory}
                    change_confirmation = build_change_confirmation(_combined_change)
                    confirmed_why_now = build_confirmed_why_now(change_confirmation)
                    crowded_narrative = build_crowded_narrative({**estimate_probe.loc[idx].to_dict(), **consensus_change, **consensus_memory})
                    expectation_gap = build_expectation_gap({**estimate_probe.loc[idx].to_dict(), **consensus_change, **consensus_memory, **change_confirmation, **crowded_narrative})
                    estimate_records[idx] = {**metrics, **sector_kpis, **acceleration, **post_report, **report_delta, **report_memory, **owner_signal, **management_signal, **management_memory, **consensus_change, **consensus_memory, **change_confirmation, **confirmed_why_now, **crowded_narrative, **expectation_gap, **_sequence_summary, **_fs_summary, **{'False Start frozen state': _latest_fs}}
                except Exception:
                    estimate_records[idx] = {}
    if estimate_records:
        estimate_frame = pd.DataFrame.from_dict(estimate_records, orient="index")
        keep = [c for c in [
            "EPS-estimat förändring", "EPS-estimat jämförelseperiod", "EPS-revisionsbalans",
            "Analytiker antal", "Reviderande analytiker senaste period", "Analytikertäckning",
            "Estimat tillförlitlighetsvikt", "Senaste EPS-överraskning",
            "Förväntningsacceleration status", "Förväntningsacceleration kandidat",
            "Förväntningsacceleration stark", "EPS förändring 7d", "EPS förändring 30d",
            "Revisionsbalans 7d", "Andel revideringar senaste 7d",
            "Förväntningsacceleration förklaring",
            "Post-report dagar sedan", "Post-report reaktion", "Post-report fortsatt rörelse",
            "Report Delta status", "Report Delta kandidat", "Report Delta underreaktion",
            "Report Delta evidens", "Report Delta positiva", "Report Delta negativa",
            "Report Delta guidance", "Report Delta kursreaktion", "Report Delta fortsatt rörelse",
            "Report Delta förklaring", "Report Delta datagrund", "Rapport läst",
            "Rapport text verifierad", "Rapport titel", "Rapport typ", "Rapport publicerad",
            "Rapport URL", "Rapport kontroll", "Rapport användartext",
            "Rapportminne status", "Rapportminne historik", "Rapportminne förbättring",
            "Rapportminne försämring", "Rapportminne rapportdatum",
            "Rapportminne jämförelserapport", "Rapportminne förklaring",
            "Kapitalallokering nettoåterköp", "Kapitalallokering återköpsyield",
            "Kapitalallokering emissionsyield", "Kapitalallokering kontantutdelningsyield",
            "Kapitalallokering skuldtrend", "Kapitalallokering nettoskuld", "Insider köp antal", "Insider köpare antal",
            "Insider sälj antal", "Insider köp värde", "Insider kluster", "Insider starkt kluster",
            "Insider period dagar", "Insider förklaring", "Ägarsignal status", "Ägarsignal kandidat",
            "Ägarsignal stark", "Ägarsignal positiva", "Ägarsignal varningar", "Ägarsignal förklaring",
            "Ledningssignal status", "Ledningssignal kandidat", "Ledningssignal stark", "Ledningssignal varning",
            "Ledningssignal positiva", "Ledningssignal negativa", "Ledningssignal jämförbara",
            "Ledningssignal positiva ämnen", "Ledningssignal negativa ämnen", "Ledningssignal rubriker",
            "Ledningssignal förklaring",
            "Ledningsminne status", "Ledningsminne historik", "Ledningsminne positiv", "Ledningsminne negativ",
            "Ledningsminne förbättrade ämnen", "Ledningsminne försämrade ämnen", "Ledningsminne signaldatum",
            "Ledningsminne jämförelsedatum", "Ledningsminne förklaring",
            "Konsensusförändring status", "Konsensusförändring kandidat", "Konsensusförändring stark",
            "Konsensusförändring varning", "Konsensus bullish andel", "Konsensus bearish andel",
            "Konsensus net breadth", "Konsensus breadth förändring", "Konsensus analytiker antal",
            "Konsensus uppgraderingar 45d", "Konsensus nedgraderingar 45d",
            "Konsensus initierad bevakning 45d", "Konsensus aktiva analyshus 45d",
            "Konsensus åtgärdsbalans 45d", "Riktkurs medel", "Riktkurs median",
            "Riktkurs hög", "Riktkurs låg", "Riktkurs dispersion", "Riktkurs potential",
            "Konsensusförändring förklaring",
            "Konsensusminne status", "Konsensusminne historik", "Konsensusminne positiv",
            "Konsensusminne negativ", "Konsensusminne köpandel förändring",
            "Konsensusminne riktkursmedian förändring", "Konsensusminne dispersion förändring",
            "Crowded status", "Crowded varning", "Crowded stark varning", "Crowded förklaring",
            "Expectation Gap status", "Expectation Gap kandidat", "Expectation Gap stark", "Expectation Gap varning",
            "Expectation Gap förändringsfamiljer", "Expectation Gap bullish andel", "Expectation Gap analytiker antal",
            "Expectation Gap riktkurs potential", "Expectation Gap förklaring",
            "Konsensusminne analytiker förändring", "Konsensusminne jämförelsedatum",
            "Konsensusminne förklaring",
            "Förändringsbekräftelse status", "Förändringsbekräftelse kandidat",
            "Förändringsbekräftelse stark", "Förändringsbekräftelse varning",
            "Förändringsbekräftelse historikfamiljer", "Förändringsbekräftelse positiva familjer",
            "Förändringsbekräftelse negativa familjer", "Förändringsbekräftelse förklaring",
            "Bekräftat varför nu status", "Bekräftat varför nu", "Bekräftat varför nu utfall",
            "Bekräftat varför nu stöd antal", "Bekräftat varför nu motbevis antal",
            "Bekräftat varför nu konflikt", "Bekräftat varför nu stark",
            "Bekräftat varför nu familjer", "Bekräftat varför nu motbevis"
        ] if c in estimate_frame.columns]
        if keep:
            discovery_pool = discovery_pool.drop(columns=[c for c in keep if c in discovery_pool.columns], errors="ignore")
            discovery_pool = discovery_pool.join(estimate_frame[keep], how="left")
        if "Bekräftat varför nu status" in estimate_frame.columns:
            st.session_state["bq_confirmed_why_now_radar"] = estimate_frame.copy()
    discovery_pool = add_estimate_revision_radar(discovery_pool)
    # v3.58 Sector Read-through: use verified changes in one company only as a
    # conservative clue for fundamentally supported peers in the same sector.
    # This never claims causality or that a peer shares the source company's change.
    discovery_pool = add_value_chain_readthrough(discovery_pool)
    discovery_pool = add_verified_relationships(discovery_pool)
    discovery_pool = add_relationship_change_radar(discovery_pool, load_verified_relationships(), as_of=_borsify_today())
    discovery_pool = add_sector_readthrough(discovery_pool)
    try:
        st.session_state["bq_relationship_registry_health"] = relationship_registry_health(
            load_verified_relationships(), as_of=_borsify_today()
        )
    except Exception:
        st.session_state["bq_relationship_registry_health"] = {}
    try:
        if "Underfollowed kandidat" in discovery_pool.columns:
            st.session_state["bq_underfollowed_discovery"] = discovery_pool.copy()
        st.session_state["bq_estimate_revision_radar"] = discovery_pool[
            discovery_pool["Estimat Radar kandidat"].fillna(False).astype(bool)
        ].copy()
        if "Report Delta status" in discovery_pool.columns:
            st.session_state["bq_report_delta_radar"] = discovery_pool.copy()
        if "Ägarsignal status" in discovery_pool.columns:
            st.session_state["bq_owner_signal_radar"] = discovery_pool.copy()
        if "Ledningssignal status" in discovery_pool.columns:
            st.session_state["bq_management_signal_radar"] = discovery_pool.copy()
        if "Konsensusförändring status" in discovery_pool.columns:
            st.session_state["bq_consensus_change_radar"] = discovery_pool.copy()
        if "Värdekedja status" in discovery_pool.columns:
            st.session_state["bq_value_chain_radar"] = discovery_pool.copy()
        if "Verifierad relation status" in discovery_pool.columns:
            st.session_state["bq_verified_relationship_radar"] = discovery_pool.copy()
        if "Relationsförändring status" in discovery_pool.columns:
            st.session_state["bq_relationship_change_radar"] = discovery_pool.copy()
        if "Sektorläsning status" in discovery_pool.columns:
            st.session_state["bq_sector_readthrough_radar"] = discovery_pool.copy()
    except Exception:
        pass

    pool = select_deep_finalist_pool(discovery_pool, pool_size=pool_size)
    records: dict[str, dict[str, Any]] = {}
    max_workers = min(3, max(1, len(pool)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_deep_statements, str(row["Ticker"])): idx for idx, row in pool.iterrows()}
        for future in as_completed(futures):
            idx = futures[future]
            row = pool.loc[idx]
            try:
                raw = future.result()
                metrics = build_deep_metrics(raw.get("income"), raw.get("cashflow"), raw.get("balance"))
                assessment = assess_deep_case(metrics, row)

                earnings_quality_metrics = build_earnings_quality_metrics(
                    raw.get("income"), raw.get("cashflow"), raw.get("balance")
                )
                earnings_quality = assess_earnings_quality(earnings_quality_metrics)
                assessment.update(earnings_quality)
                assessment = apply_earnings_quality_gate(assessment)

                investment_discipline = assess_investment_discipline(
                    build_investment_discipline_metrics(raw.get("income"), raw.get("cashflow"), raw.get("balance")),
                    row.get("Sektor", ""),
                )
                assessment.update(investment_discipline)
                assessment = apply_investment_discipline_gate(assessment)

                inflection_metrics = build_inflection_metrics(
                    raw.get("quarterly_income"), raw.get("quarterly_cashflow"),
                    raw.get("eps_trend"), raw.get("eps_revisions"), raw.get("earnings_history"),
                    raw.get("quarterly_balance"), raw.get("earnings_estimate")
                )
                sector_kpis = extract_sector_kpis(
                    str(row.get("Sektor") or ""), str(row.get("Bransch") or ""),
                    raw.get("quarterly_income"), raw.get("quarterly_cashflow"), raw.get("quarterly_balance")
                )
                assessment.update(sector_kpis)
                _kpi_context = {**row.to_dict(), **assessment}
                _kpi_context.update(assess_business_management_intelligence(_kpi_context))
                assessment.update(assess_kpi_inflection(_kpi_context))
                inflection = assess_inflection(inflection_metrics)
                assessment.update(inflection)
                post_report = build_post_report_drift(
                    raw.get("earnings_history"), raw.get("price_history"), inflection_metrics
                )
                assessment.update(post_report)
                assessment.update(build_report_delta_with_provenance(inflection_metrics, post_report, raw, row))
                owner_snapshot = {**row.to_dict(), **(raw.get("fast_info") or {})}
                assessment.update(build_capital_allocation_insider_radar(
                    raw.get("cashflow"), raw.get("balance"), raw.get("insider_transactions"), owner_snapshot
                ))
                _management_signal = build_management_signal(raw.get("catalyst_events"))
                assessment.update(_management_signal)
                _deep_symbol = str(row.get("Ticker", ""))
                _mgmt_snap = snapshot_from_management_signal(_deep_symbol, _management_signal, raw.get("catalyst_events"), _borsify_today())
                try:
                    with _db_connect() as _conn:
                        _mgmt_prev = previous_management_snapshot(_conn, _deep_symbol, _mgmt_snap["signal_key"]) if _mgmt_snap else None
                        _management_memory = compare_management_signal_memory(_mgmt_snap, _mgmt_prev)
                        save_management_snapshot(_conn, _mgmt_snap)
                except Exception:
                    _management_memory = compare_management_signal_memory(_mgmt_snap, None)
                assessment.update(_management_memory)
                assessment.update(build_expectation_change({**row.to_dict(), **assessment}))
                assessment.update(build_fresh_change({**row.to_dict(), **assessment}))
                assessment = apply_inflection_gate(assessment)
                mispricing = build_mispricing_assessment(row, assessment)
                assessment.update(mispricing)
                assessment = apply_mispricing_gate(assessment)
                scenario = build_scenarios(row.to_dict(), assessment, assessment, assessment)
                assessment["Scenario Status"] = scenario.get("status", "Otillräcklig data")
                assessment["Scenario Confidence"] = scenario.get("confidence", 0)
                if scenario.get("status") == "OK":
                    assessment["Scenario Verdict"] = scenario.get("verdict", "—")
                    assessment["Scenario Asymmetry"] = scenario.get("asymmetry", np.nan)
                    assessment["Scenario Risk Label"] = scenario.get("risk_label", "—")
                    assessment["Scenario Note"] = scenario.get("note", "—")
                    for label, key in (("Bear", "bear"), ("Base", "base"), ("Bull", "bull")):
                        s = scenario.get(key, {})
                        assessment[f"{label} EPS growth"] = s.get("eps_growth", np.nan)
                        assessment[f"{label} exit P/E"] = s.get("exit_pe", np.nan)
                        assessment[f"{label} future price"] = s.get("future_price", np.nan)
                        assessment[f"{label} upside"] = s.get("upside", np.nan)
                        assessment[f"{label} annualized return"] = s.get("annualized_return", np.nan)
                else:
                    assessment["Scenario Verdict"] = "Kan inte bedömas"
                    assessment["Scenario Asymmetry"] = np.nan
                    assessment["Scenario Note"] = scenario.get("reason", "Otillräcklig data")
                assessment.update(build_fundamental_value_range({**row.to_dict(), **assessment}, scenario))
                catalyst = build_catalyst_assessment({**row.to_dict(), **assessment}, raw.get("catalyst_events"))
                assessment.update(catalyst)
                assessment.update(build_news_impact_assessment(raw.get("catalyst_events"), raw.get("price_history")))
                assessment.update(build_news_flow_monitor(raw.get("catalyst_events"), raw.get("price_history")))
                assessment.update(build_news_surprise_response(raw.get("catalyst_events"), raw.get("price_history")))
                assessment.update(build_why_now_assessment({**row.to_dict(), **assessment}))
                assessment.update(assess_fundamental_data_confidence(raw, assessment))
                assessment.update(assess_fundamental_redundancy({**row.to_dict(), **assessment}, raw))
                assessment.update(build_evidence_families({**row.to_dict(), **assessment}))
                assessment.update(build_case_quality_gate({**row.to_dict(), **assessment}))
                if raw.get("error"):
                    assessment["Deep fetch error"] = raw.get("error")
                _src_health = raw.get("source_health") if isinstance(raw.get("source_health"), dict) else {}
                assessment["Deep source status"] = str(_src_health.get("status") or "")
                assessment["Deep source errors"] = "; ".join(f"{k}:{v}" for k,v in (_src_health.get("errors") or {}).items())
                assessment["Deep source missing"] = "; ".join(map(str, _src_health.get("missing") or []))
                assessment["Deep source error types"] = "; ".join(f"{k}:{v}" for k,v in (_src_health.get("error_types") or {}).items())
                assessment["Deep source attempts"] = "; ".join(f"{k}:{v}" for k,v in (_src_health.get("attempts") or {}).items())
                assessment["Deep source circuits open"] = "; ".join(map(str, _src_health.get("circuits_open") or []))
                assessment["Deep source circuit open"] = bool(_src_health.get("circuit_open"))
                st.session_state["bq_source_health_deep"] = {
                    "status": assessment["Deep source status"] or "UNKNOWN",
                    "error": assessment["Deep source errors"],
                    "attempts": _src_health.get("attempts") or {},
                    "circuit_open": assessment["Deep source circuit open"],
                    "circuits_open": _src_health.get("circuits_open") or [],
                }
                try:
                    with _db_connect() as _conn:
                        save_events(_conn, events_from_snapshot(_deep_symbol, {**row.to_dict(), **assessment}, _borsify_today()))
                        _seq_hist = inflection_sequence_history(_conn, _deep_symbol)
                        assessment.update(summarize_sequence(_seq_hist))
                        _fs_class = classify_early_signals(_seq_hist, _borsify_today())
                        assessment.update(summarize_false_starts(_fs_class))
                        assessment["False Start frozen state"] = _fs_class.sort_values("early_date").iloc[-1]["status"] if not _fs_class.empty else ""
                except Exception:
                    assessment.update(summarize_sequence(None))
                    assessment.update(summarize_false_starts(None))
                    assessment["False Start frozen state"] = ""
                records[idx] = assessment
            except Exception as exc:
                records[idx] = {
                    "Djupkontroll": "Otillräcklig data", "Value Trap Risk": np.nan, "Deep Confidence": 0.0,
                    "Fleråriga styrkor": "kunde inte verifieras", "Fleråriga varningar": f"djupdata kunde inte läsas ({type(exc).__name__})",
                    "Varför marknaden kan ha fel": "kan inte bedömas med tillräcklig flerårsdata",
                    "Devil's Advocate": "otillräcklig data – gå inte vidare på modellen ensam", "Rapportdatum": "—",
                }
    # Pandas .at still falls back to .loc when a target column does not yet exist.
    # Some assessment fields are lists/dicts (e.g. catalyst candidates/supports), so
    # create all new columns as object dtype before assigning cell-by-cell.
    # Build an object-typed result frame first, then join it into pool.
    # This avoids Pandas scalar assignment entirely for list/dict values.
    if records:
        assessment_frame = pd.DataFrame.from_dict(records, orient="index")
        for key in assessment_frame.columns:
            assessment_frame[key] = assessment_frame[key].astype("object")
        existing = [c for c in assessment_frame.columns if c in pool.columns]
        if existing:
            pool = pool.drop(columns=existing)
        pool = pool.join(assessment_frame, how="left")
    # Final ordering is evidence-gate first. INVEST only breaks ties after the
    # independent quality, inflection, mispricing and scenario checks.
    order = sorted(pool.index, key=lambda idx: case_gate_rank_key(pool.loc[idx]), reverse=True)
    return pool.loc[order].head(limit).copy()


def build_short_term_longlist(df: pd.DataFrame, benchmark: dict[str, Any] | None, pool_size: int = 8, limit: int = 5) -> pd.DataFrame:
    """Build a 1–6 month finalist list.

    Stage 1 uses only causal current technical/relative-strength data to choose a small
    candidate pool. Stage 2 adds fresh quarterly/estimate inflection and catalyst evidence.
    A prior fall is never a positive input and hard anti-falling-knife vetoes survive stage 2.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    prelim = df.copy()
    prelim_records: dict[Any, dict[str, Any]] = {}
    for idx, row in prelim.iterrows():
        prelim_records[idx] = assess_short_term_case(row, benchmark)
    for idx, assessment in prelim_records.items():
        for key, value in assessment.items():
            prelim.at[idx, key] = value

    prelim_order = sorted(prelim.index, key=lambda idx: short_term_rank_key(prelim.loc[idx]), reverse=True)
    pool = prelim.loc[prelim_order].head(pool_size).copy()
    if pool.empty:
        return pool

    records: dict[Any, dict[str, Any]] = {}
    max_workers = min(3, max(1, len(pool)))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(fetch_deep_statements, str(row["Ticker"])): idx for idx, row in pool.iterrows()}
        for future in as_completed(futures):
            idx = futures[future]
            row = pool.loc[idx]
            try:
                raw = future.result()
                inflection_metrics = build_inflection_metrics(
                    raw.get("quarterly_income"), raw.get("quarterly_cashflow"),
                    raw.get("eps_trend"), raw.get("eps_revisions"), raw.get("earnings_history"),
                    raw.get("quarterly_balance"), raw.get("earnings_estimate")
                )
                sector_kpis = extract_sector_kpis(
                    str(row.get("Sektor") or ""), str(row.get("Bransch") or ""),
                    raw.get("quarterly_income"), raw.get("quarterly_cashflow"), raw.get("quarterly_balance")
                )
                inflection = assess_inflection(inflection_metrics)
                inflection.update(sector_kpis)
                _kpi_context = {**row.to_dict(), **inflection}
                _kpi_context.update(assess_business_management_intelligence(_kpi_context))
                inflection.update(assess_kpi_inflection(_kpi_context))
                post_report = build_post_report_drift(
                    raw.get("earnings_history"), raw.get("price_history"), inflection_metrics
                )
                inflection.update(post_report)
                inflection.update(build_report_delta_with_provenance(inflection_metrics, post_report, raw, row))
                inflection.update(build_expectation_change({**row.to_dict(), **inflection}))
                inflection.update(build_fresh_change({**row.to_dict(), **inflection}))
                catalyst = build_catalyst_assessment({**row.to_dict(), **inflection}, raw.get("catalyst_events"))
                result = assess_short_term_case(row, benchmark, inflection, catalyst)
                # Preserve the full current estimate/catalyst evidence on the finalist row.
                # The decision model still uses assess_short_term_case; these extra fields
                # exist so Point-in-Time Ledger 2.0 can audit exactly what was available.
                result.update(inflection)
                result.update(catalyst)
                result.update(build_news_impact_assessment(raw.get("catalyst_events"), raw.get("price_history")))
                result.update(build_news_flow_monitor(raw.get("catalyst_events"), raw.get("price_history")))
                result.update(build_news_surprise_response(raw.get("catalyst_events"), raw.get("price_history")))
                result.update(build_why_now_assessment({**row.to_dict(), **result}))
                if raw.get("error"):
                    result["Short Data Warning"] = raw.get("error")
                records[idx] = result
            except Exception as exc:
                fallback = assess_short_term_case(row, benchmark)
                fallback["Short Data Warning"] = f"Färsk fundamental-/estimatsdata kunde inte läsas ({type(exc).__name__})."
                records[idx] = fallback

    # Same protection as the deep longlist: pre-create new fields as object dtype
    # so iterable assessment values never trigger Pandas' multi-column assignment path.
    if records:
        assessment_frame = pd.DataFrame.from_dict(records, orient="index")
        for key in assessment_frame.columns:
            assessment_frame[key] = assessment_frame[key].astype("object")
        existing = [c for c in assessment_frame.columns if c in pool.columns]
        if existing:
            pool = pool.drop(columns=existing)
        pool = pool.join(assessment_frame, how="left")

    order = sorted(pool.index, key=lambda idx: short_term_rank_key(pool.loc[idx]), reverse=True)
    return pool.loc[order].head(limit).copy()


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_company_events(symbol: str) -> dict[str, Any]:
    """Fetch lightweight event/news data only for the stock the user opens."""
    t = yf.Ticker(symbol)
    result: dict[str, Any] = {"earnings": None, "ex_dividend": None, "news": []}
    try:
        cal = t.calendar
        if isinstance(cal, dict):
            earnings = cal.get("Earnings Date") or cal.get("EarningsDate")
            if isinstance(earnings, (list, tuple)) and earnings:
                earnings = earnings[0]
            result["earnings"] = earnings
            result["ex_dividend"] = cal.get("Ex-Dividend Date") or cal.get("ExDividendDate")
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            # yfinance has used both dict and DataFrame formats over time.
            for key in ["Earnings Date", "EarningsDate"]:
                if key in cal.index:
                    val = cal.loc[key].iloc[0]
                    result["earnings"] = val
                    break
            for key in ["Ex-Dividend Date", "ExDividendDate"]:
                if key in cal.index:
                    result["ex_dividend"] = cal.loc[key].iloc[0]
                    break
    except Exception:
        pass
    try:
        raw_news = t.news or []
        cleaned = []
        for item in raw_news[:8]:
            content = item.get("content", item) if isinstance(item, dict) else {}
            title = content.get("title") or item.get("title") if isinstance(item, dict) else None
            link = None
            if isinstance(content, dict):
                canonical = content.get("canonicalUrl") or content.get("clickThroughUrl")
                if isinstance(canonical, dict):
                    link = canonical.get("url")
                elif isinstance(canonical, str):
                    link = canonical
            if not link and isinstance(item, dict):
                link = item.get("link")
            provider = ""
            provider_obj = content.get("provider") if isinstance(content, dict) else None
            if isinstance(provider_obj, dict):
                provider = provider_obj.get("displayName") or ""
            if title:
                cleaned.append({"title": str(title), "link": link, "provider": provider})
        result["news"] = cleaned[:5]
    except Exception:
        pass
    return result


def _fmt_date(value: Any) -> str:
    if value is None:
        return "—"
    try:
        ts = pd.to_datetime(value)
        if pd.isna(ts):
            return "—"
        return ts.strftime("%Y-%m-%d")
    except Exception:
        return str(value)[:10] if value else "—"


def _supabase_config() -> tuple[str, str]:
    """Read Supabase public connection values from Streamlit secrets when available."""
    try:
        url = str(st.secrets.get("SUPABASE_URL", "")).strip()
        key = str(st.secrets.get("SUPABASE_ANON_KEY", "")).strip()
        return url, key
    except Exception:
        return "", ""


@st.cache_resource(show_spinner=False)
def _supabase_client() -> Any:
    url, key = _supabase_config()
    if not url or not key or create_client is None:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None


def cloud_enabled() -> bool:
    return _supabase_client() is not None


def current_user() -> Any:
    return st.session_state.get("bq_user")


def current_user_id() -> str | None:
    user = current_user()
    return str(getattr(user, "id", "")) or None if user is not None else None


def current_user_email() -> str:
    user = current_user()
    if user is None:
        return ""
    value = getattr(user, "email", "")
    return str(value or "").strip()


def auth_sign_in(email: str, password: str) -> tuple[bool, str]:
    client = _supabase_client()
    if client is None:
        return False, "Supabase är inte konfigurerat."
    try:
        res = client.auth.sign_in_with_password({"email": email.strip(), "password": password})
        user = getattr(res, "user", None)
        if user is None:
            return False, "Inloggningen misslyckades."
        st.session_state["bq_user"] = user
        return True, "Inloggad"
    except Exception as exc:
        return False, f"Inloggningen misslyckades: {exc}"


def auth_sign_up(email: str, password: str) -> tuple[bool, str]:
    client = _supabase_client()
    if client is None:
        return False, "Supabase är inte konfigurerat."
    try:
        res = client.auth.sign_up({"email": email.strip(), "password": password})
        user = getattr(res, "user", None)
        session = getattr(res, "session", None)
        if session is not None and user is not None:
            st.session_state["bq_user"] = user
            return True, "Konto skapat och inloggat."
        return True, "Konto skapat. Kontrollera e-post om Supabase kräver e-postbekräftelse."
    except Exception as exc:
        return False, f"Kontot kunde inte skapas: {exc}"


def auth_sign_out() -> None:
    client = _supabase_client()
    if client is not None:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    st.session_state.pop("bq_user", None)


def _db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def _ensure_sqlite_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    cols = {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def init_db() -> None:
    with _db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS watchlist (
                symbol TEXT PRIMARY KEY,
                note TEXT NOT NULL DEFAULT '',
                target_price REAL,
                added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _ensure_sqlite_column(conn, "watchlist", "signal_score_threshold", "REAL NOT NULL DEFAULT 75")
        _ensure_sqlite_column(conn, "watchlist", "signal_score_move", "REAL NOT NULL DEFAULT 8")
        _ensure_sqlite_column(conn, "watchlist", "signal_daily_drop", "REAL NOT NULL DEFAULT 5")
        _ensure_sqlite_column(conn, "watchlist", "breaker_min_score", "REAL NOT NULL DEFAULT 0")
        _ensure_sqlite_column(conn, "watchlist", "breaker_min_quality", "REAL NOT NULL DEFAULT 0")
        _ensure_sqlite_column(conn, "watchlist", "breaker_min_risk", "REAL NOT NULL DEFAULT 0")
        _ensure_sqlite_column(conn, "watchlist", "breaker_max_score_drop", "REAL NOT NULL DEFAULT 0")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS score_history (
                symbol TEXT NOT NULL,
                score REAL NOT NULL,
                profile TEXT NOT NULL,
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _ensure_sqlite_column(conn, "score_history", "valuation", "REAL")
        _ensure_sqlite_column(conn, "score_history", "quality", "REAL")
        _ensure_sqlite_column(conn, "score_history", "setup", "REAL")
        _ensure_sqlite_column(conn, "score_history", "income", "REAL")
        _ensure_sqlite_column(conn, "score_history", "risk", "REAL")
        _ensure_sqlite_column(conn, "score_history", "coverage", "REAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS radar_history (
                symbol TEXT NOT NULL,
                profile TEXT NOT NULL,
                rank INTEGER NOT NULL,
                score REAL NOT NULL,
                captured_date TEXT NOT NULL,
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(symbol, profile, captured_date)
            )
            """
        )
        _ensure_sqlite_column(conn, "radar_history", "details", "TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS signal_history (
                event_key TEXT PRIMARY KEY,
            …84700 tokens truncated…t.session_state["bq_manual_refresh_in_progress"] = False
        st.session_state["bq_manual_refresh_fetched_count"] = int(len(raw_df))
        st.session_state["bq_manual_refresh_error_count"] = int(len(errors))

    raw_df, fx_rates, missing_fx = add_sek_conversions(raw_df)
    if missing_fx:
        errors.append("Valutaomräkning saknas för: " + ", ".join(missing_fx))

    raw_df = apply_universe_quality(raw_df)
    qc_all_fetched = raw_df.copy()
    raw_df, qc_rejected = filter_rankable_universe(raw_df)
    st.session_state["bq_qc_hard_rejected"] = int(len(qc_rejected))
    if refresh:
        fetched_count = int(st.session_state.get("bq_manual_refresh_fetched_count", len(raw_df)) or 0)
        error_count = int(st.session_state.get("bq_manual_refresh_error_count", len(errors)) or 0)
        cleared_count = int(st.session_state.get("bq_manual_refresh_cleared_fundamentals", 0) or 0)
        if error_count:
            st.warning(f"Uppdateringen hämtade {fetched_count} aktier med {error_count} datavarning(ar). {cleared_count} gamla fundamentalposter rensades före hämtningen.")
        else:
            st.success(f"Data uppdaterad: {fetched_count} aktier hämtades på nytt. {cleared_count} gamla fundamentalposter rensades före hämtningen.")
        persistent_error = st.session_state.get("bq_manual_refresh_error")
        if persistent_error:
            st.warning(str(persistent_error))

    # Persist at most one equivalent QC observation per ticker/day, so Streamlit
    # reruns do not manufacture failure streaks. Provider-wide outages are guarded
    # against: missing fetches only count as strikes when enough of the batch worked.
    prior_lookup = {
        str(r.get("symbol") or "").upper(): r
        for _, r in qc_states_before.iterrows()
    } if not qc_states_before.empty else {}
    fetched_symbols = set(qc_all_fetched.get("Ticker", pd.Series(dtype=str)).astype(str).str.upper().tolist())
    health = scan_health(len(fetched_symbols), len(scan_symbols))
    st.session_state["bq_qc_scan_health"] = float(health["success_ratio"])
    st.session_state["bq_qc_provider_healthy"] = bool(health["provider_healthy_enough"])
    st.session_state["bq_qc_provider_rule"] = str(health.get("provider_health_rule") or "")

    for _, qc_row in qc_all_fetched.iterrows():
        sym = str(qc_row.get("Ticker") or "").upper()
        status = str(qc_row.get("Universe QC") or "")
        outcome = "verified" if status == "VERIFIERAD" else ("partial" if status == "DELVIS VERIFIERAD" else "hard_failure")
        prev = prior_lookup.get(sym)
        if should_record_qc_outcome(prev, outcome):
            state = evolve_qc_state(
                prev, symbol=sym, outcome=outcome,
                reason=str(qc_row.get("Universe QC Problem") or ""),
                count_failure=True,
            )
            save_universe_qc_state(state, outcome, counted_failure=(outcome == "hard_failure"))
            prior_lookup[sym] = state

    missing_fetch_symbols = [str(sym).upper() for sym in scan_symbols if str(sym).upper() not in fetched_symbols]
    for sym in missing_fetch_symbols:
        prev = prior_lookup.get(sym)
        if not should_record_qc_outcome(prev, "hard_failure" if health["provider_healthy_enough"] else "transient_failure"):
            continue
        counted = bool(health["provider_healthy_enough"])
        outcome = "hard_failure" if counted else "transient_failure"
        state = evolve_qc_state(
            prev, symbol=sym, outcome=outcome,
            reason=("ingen kurshistorik kunde verifieras" if counted else "brett datakällefel misstänks – ingen QC-strike"),
            count_failure=counted,
        )
        save_universe_qc_state(state, outcome, counted_failure=counted)
        prior_lookup[sym] = state

    if not qc_rejected.empty:
        for _, rejected_row in qc_rejected.iterrows():
            errors.append(
                f"{rejected_row.get('Ticker','?')}: Universe QC exkluderad · "
                f"{rejected_row.get('Universe QC Problem','otillräcklig datakvalitet')}"
            )
    if raw_df.empty:
        st.error("Ingen aktie hade tillräcklig marknadsdatakvalitet för ranking.")
        st.stop()

    # v3.03: estimate company-specific volatility relative to the selected market.
    # It is a risk/counterevidence clue only and never adds positive score.
    benchmark_hist_for_risk = fetch_single_price_history(benchmark_symbol) if benchmark_symbol else pd.DataFrame()
    raw_df = apply_idiosyncratic_volatility(raw_df, benchmark_hist_for_risk)

    analysis_started = time.perf_counter()
    scored = add_scores(raw_df, profile)
    scored = add_investment_company_context(scored)
    scored = add_data_trust(scored)
    scored["Land"] = [
        _market_label_for_ticker(t)
        for t in scored.get("Ticker", pd.Series(index=scored.index,dtype=str)).astype(str)
    ]
    save_score_history(scored, profile)
    analysis_seconds = time.perf_counter() - analysis_started

    # v2.64: validate a possible future price-only prefilter against the full
    # analysis. This does NOT reduce today's Yahoo calls or change rankings.
    try:
        validation_targets: set[str] = set(
            scored.sort_values(["Borsify Score","Datatäckning"],ascending=[False,False])
            .head(5)["Ticker"].astype(str).tolist()
        )
        for validation_horizon in ("day","medium","long","lifetime"):
            validation_top = top_three(scored, validation_horizon)
            if not validation_top.empty:
                validation_targets.update(validation_top["Ticker"].astype(str).tolist())
        prefilter_validation = validate_candidate_pool(
            scored, validation_targets, fraction=.60, minimum=80
        )
        save_prefilter_validation(
            DB_PATH, market, prefilter_validation, APP_VERSION
        )
        st.session_state["bq_prefilter_validation"] = prefilter_validation
    except Exception:
        st.session_state["bq_prefilter_validation"] = {}

    # Keep compatibility during Streamlit rolling deploys where app.py can reload
    # before the updated search_filters module. Apply dividend filtering below too.
    filter_counts: dict[str, int] = {"Analyserade": int(len(scored))}
    filtered = apply_country_price_filters(
        scored,
        countries=selected_countries,
        min_price_sek=min_price_sek,
        max_price_sek=max_price_sek,
    )
    filter_counts["Efter land/pris"] = int(len(filtered))
    if min_market_cap > 0:
        cap_ok = filtered["Börsvärde BSEK"] >= min_market_cap
        if allow_missing_filter_data: cap_ok = cap_ok | filtered["Börsvärde BSEK"].isna()
        filtered = filtered[cap_ok]
    filter_counts["Efter börsvärde"] = int(len(filtered))
    if min_turnover > 0:
        turnover_ok = filtered["Omsättning MSEK/dag"] >= min_turnover
        if allow_missing_filter_data: turnover_ok = turnover_ok | filtered["Omsättning MSEK/dag"].isna()
        filtered = filtered[turnover_ok]
    filter_counts["Efter handel"] = int(len(filtered))
    if require_positive:
        filtered = filtered[filtered["P/E"].notna() & (filtered["P/E"] > 0)]
    filter_counts["Efter positiv P/E"] = int(len(filtered))
    if dividend_only:
        dy = pd.to_numeric(filtered.get("Direktavkastning"), errors="coerce")
        min_yield = float(min_dividend_yield) / 100.0
        filtered = filtered[dy.notna() & (dy > 0) & (dy >= min_yield)]
    filter_counts["Efter utdelning"] = int(len(filtered))
    filtered = apply_discovery_intent(filtered, discovery_intent)
    filter_counts["Efter sökmål"] = int(len(filtered))
    filtered = apply_search_horizon(filtered, search_horizon, add_horizon_scores)
    filter_counts["Slutligt urval"] = int(len(filtered))
    avanza_symbol_set = set(avanza_universe_df.get("Ticker", pd.Series(dtype=str)).astype(str).str.upper()) if not avanza_universe_df.empty else set()
    filtered["Avanza-universum"] = filtered.get("Ticker", pd.Series("", index=filtered.index)).astype(str).str.upper().isin(avanza_symbol_set)
    # v3.52 Nya förbättringar i bolagen: compare today's broad scan with the latest
    # older point-in-time universe snapshot. Same-day data cannot be its own baseline
    # and missing historical fields are never backfilled.
    try:
        _change_history = get_missed_winner_snapshots(limit=20000)
        filtered = add_fundamental_change_radar(filtered, _change_history, datetime.now().date().isoformat())
    except Exception:
        filtered = add_fundamental_change_radar(filtered, pd.DataFrame(), datetime.now().date().isoformat())
    # Discovery 2.0 is a candidate doorway, not a new score. Keep an auditable
    # multi-lens pool so advanced diagnostics can show whether the search is broad.
    discovery_pool_global = build_discovery_pool(filtered, max_candidates=min(24, len(filtered)))
    st.session_state["bq_discovery_coverage"] = discovery_coverage_summary(filtered, discovery_pool_global)
    top = filtered.head(top_n).copy()
    daily_shortlist, evidence_finalists = build_evidence_gated_shortlist(filtered, profile, limit=min(5, len(filtered)))
    st.session_state["bq_evidence_finalists"] = evidence_finalists
    ungated_first = rank_close_daily_candidates(evidence_finalists.copy()).head(1) if not evidence_finalists.empty else pd.DataFrame()
    gated_first = daily_shortlist.head(1)
    st.session_state["bq_first_choice_gate_changed"] = bool(
        not ungated_first.empty and not gated_first.empty
        and str(ungated_first.iloc[0].get("Ticker")) != str(gated_first.iloc[0].get("Ticker"))
    )
    try:
        first_choice_records = []
        if not ungated_first.empty:
            first_choice_records.append(build_first_choice_record(ungated_first.iloc[0], "incumbent", profile, market))
        if not gated_first.empty:
            first_choice_records.append(build_first_choice_record(gated_first.iloc[0], "evidence_gated", profile, market))
        save_first_choice_records(DB_PATH, first_choice_records)
        resolve_runtime_issue(st.session_state, "first_choice_audit")
    except Exception as exc:
        record_runtime_issue(st.session_state, "first_choice_audit", exc, "jämförelsen mellan gammalt och evidensgranskat förstaval kunde inte frysas")
    elapsed = time.perf_counter() - start
    if isinstance(st.session_state.get("bq_scan_metrics"), dict):
        st.session_state["bq_scan_metrics"]["analysis_seconds"] = round(analysis_seconds, 3)
        st.session_state["bq_scan_metrics"]["total_seconds"] = round(elapsed, 3)
        _fund_total = int(st.session_state["bq_scan_metrics"].get("fundamental_candidates", 0) or 0)
        _fund_cached = int(st.session_state["bq_scan_metrics"].get("fundamental_persistent_cache", 0) or 0)
        st.session_state["bq_scan_metrics"]["fundamental_cache_hit_rate"] = (_fund_cached / _fund_total) if _fund_total else 0.0
    # Tekniska detaljer ska inte konkurrera med själva köpbeslutet på startsidan.
    benchmark_explainer = (
        "Borsify jämför ungefärligt med världsmarknaden via fonden VT."
        if market == "Alla marknader" else ""
    )

    price_dates = sorted({str(x) for x in raw_df.get("Prisdatum", pd.Series(dtype=str)).dropna().tolist() if str(x) != "—"})
    latest_price_date = price_dates[-1] if price_dates else "—"
    idx = fetch_index_snapshot(benchmark_symbol) if benchmark_symbol else {}
    market_note = f" · {benchmark_name} {idx['index']:.0f} ({fmt_pct(idx.get('daily'))})" if idx else ""
    fx_note = ""
    if market != "Sverige":
        converted = int(pd.to_numeric(raw_df.get("Pris SEK", pd.Series(dtype=float)), errors="coerce").notna().sum())
        fx_note = f" · SEK-omräkning {converted}/{len(raw_df)} aktier"
    active_price_text = ""
    if min_price_sek > 0 or max_price_sek > 0:
        low_txt = f"{min_price_sek:.0f}" if min_price_sek > 0 else "0"
        high_txt = f"{max_price_sek:.0f}" if max_price_sek > 0 else "ingen maxgräns"
        active_price_text = f" · prisfilter {low_txt}–{high_txt} SEK"
    country_text = ""
    if selected_countries and len(selected_countries) < len(country_filter_options):
        country_text = " · land " + ", ".join(f"{_country_flag(c)} {c}" for c in selected_countries)
    horizon_text = "" if search_horizon == "Alla tidshorisonter" else f" · tid {search_horizon}"
    scan_metrics = st.session_state.get("bq_scan_metrics", {})
    with st.expander("Om dagens analys", expanded=filtered.empty):
        if benchmark_explainer:
            st.caption(benchmark_explainer)
        requested_count = int(scan_metrics.get("requested", len(raw_df))) if isinstance(scan_metrics, dict) else len(raw_df)
        rejected_count = int(scan_metrics.get("price_rejected_before_fundamentals", 0) or 0) if isinstance(scan_metrics, dict) else 0
        st.caption(scan_result_user_text(requested_count, len(raw_df), rejected_count, int(st.session_state.get("bq_qc_skipped_quarantine", 0) or 0)))
        st.caption(f"{len(filtered)} aktier är kvar efter dina val · prisinformation från {latest_price_date}{market_note}{country_text}{active_price_text}{horizon_text}")
        st.caption("Filterkedja: " + " → ".join(f"{label} {count}" for label, count in filter_counts.items()))
        if "Fundamental förändring antal" in filtered.columns:
            _change_count = int((pd.to_numeric(filtered["Fundamental förändring antal"], errors="coerce").fillna(0) > 0).sum())
            st.caption(f"Nya förbättringar i bolagen: {_change_count} aktier med verifierad ny förbättring mot en äldre fryst bredscan. Radarn skapar inget nytt score.")
        discovery_diag = st.session_state.get("bq_discovery_coverage", {})
        if isinstance(discovery_diag, dict) and discovery_diag.get("pool"):
            lens_counts = discovery_diag.get("lens_counts", {}) or {}
            represented = ", ".join(f"{k} {v}" for k, v in lens_counts.items() if v)
            st.caption(
                f"Fler sätt att hitta intressanta aktier: {int(discovery_diag.get('pool', 0))} aktier väljs ut för en extra noggrann kontroll"
                + (f" · {represented}" if represented else "")
                + ". Det ändrar inte aktiens betyg i sig."
            )
        if isinstance(scan_metrics, dict) and scan_metrics:
            cache_hits = int(scan_metrics.get("fundamental_persistent_cache", 0) or 0)
            yahoo_fund = int(scan_metrics.get("fundamental_yahoo", 0) or 0)
            rejected_early = int(scan_metrics.get("price_rejected_before_fundamentals", 0) or 0)
            st.caption(
                f"Borsify hade redan sparad bolagsinformation för {cache_hits} aktier och hämtade ny information för {yahoo_fund}."
                + (f" {rejected_early} aktier kunde inte kontrolleras eftersom prisinformationen inte räckte." if rejected_early else "")
            )
        if st.session_state.get("bq_first_choice_gate_changed"):
            st.caption("Borsifys sista kontroll ändrade vilken aktie som hamnade först. Båda sparas så att Borsify senare kan kontrollera vilket val som blev bäst.")
        else:
            st.caption("Borsifys sista kontroll höll med om aktien som låg först. Resultatet sparas så att Borsify senare kan kontrollera hur valet gick.")
    if errors:
        with st.expander(f"Datakällan saknade {len(errors)} ticker(s) — övriga analyserades"):
            st.caption("Detta beror oftast på tillfälliga Yahoo-problem, ändrad ticker eller otillräcklig kurshistorik. Det påverkar inte aktier som redan har lästs in.")
            for error in errors:
                st.write(f"• {error}")
    if filtered.empty: st.warning("Inga aktier klarade filtren."); st.stop()

    # Förbered bevakningsdata och signaler en gång per körning.
    watch_meta_global = get_watchlist()
    watched_global = watch_meta_global["symbol"].astype(str).tolist() if not watch_meta_global.empty else []
    watch_df_global = scored[scored["Ticker"].isin(watched_global)].copy() if watched_global else pd.DataFrame()
    missing_global = [sym for sym in watched_global if sym not in set(scored["Ticker"])]
    if missing_global:
        with st.spinner(f"Hämtar {len(missing_global)} bevakade aktier utanför den valda aktielistan…"):
            extra_raw_global, _ = scan_universe(missing_global)
        if not extra_raw_global.empty:
            extra_scored_global = add_scores(extra_raw_global, profile)
            watch_df_global = pd.concat([watch_df_global, extra_scored_global], ignore_index=True)
    watch_signals = build_watch_signals(watch_df_global, top, watch_meta_global, profile) if watched_global else []
    persist_signals(watch_signals, profile)
    signal_history_global = get_signal_history()
    unread_signals = int((~signal_history_global["is_read"].astype(bool)).sum()) if not signal_history_global.empty else 0
    save_radar_history(filtered.head(max(20, top_n)), profile)

    page = st.radio(
        "Välj vy",
        ["Idag", "Fler aktier", f"Bevakning ({len(watch_df_global)})", "Mer"],
        horizontal=True,
        label_visibility="collapsed",
        key="main_page",
    )
    if page == "Idag":
        render_overview(daily_shortlist, filtered, scored, watch_df_global, signal_history_global, unread_signals, profile, idx, elapsed, latest_price_date, market, benchmark_name)
    elif page == "Fler aktier":
        st.caption(
            "Fördjupad kandidatgranskning körs först när du öppnar Fler aktier. "
            "Det gör startsidan snabbare utan att ta bort analysen."
        )
        with st.spinner("Fördjupar de starkaste kandidaterna…"):
            deep_longlist = build_deep_longlist(
                filtered, pool_size=min(10, len(filtered)), limit=min(5, len(filtered))
            )
            deep_longlist = add_data_trust(deep_longlist)
            short_longlist = build_short_term_longlist(
                filtered, idx, pool_size=min(10, len(filtered)), limit=min(5, len(filtered))
            )
            short_longlist = add_data_trust(short_longlist)

        confirmed_view = st.session_state.get("bq_confirmed_why_now_radar", pd.DataFrame())
        if isinstance(confirmed_view, pd.DataFrame) and not confirmed_view.empty and "Bekräftat varför nu status" in confirmed_view.columns:
            _cw = confirmed_view.copy()
            _cw["__support"] = pd.to_numeric(_cw.get("Bekräftat varför nu stöd antal"), errors="coerce").fillna(0)
            _cw["__against"] = pd.to_numeric(_cw.get("Bekräftat varför nu motbevis antal"), errors="coerce").fillna(0)
            _cw["__strong"] = _cw.get("Bekräftat varför nu stark", False).fillna(False).astype(int)
            _cw = _cw.sort_values(["__strong", "__support", "__against"], ascending=[False, False, True]).head(6)
            st.markdown("### Varför just nu – verifierat från flera håll")
            st.caption("Det här är inte ett nytt betyg. Borsify visar bara om verkliga förändringar i rapport, analytikerkonsensus och ledningssignaler bekräftar eller motsäger varandra.")
            for _, _case in _cw.iterrows():
                _ticker = str(_case.get("Ticker", "—"))
                _name = str(_case.get("Namn", _ticker) or _ticker)
                _status = str(_case.get("Bekräftat varför nu status", "—"))
                _text = str(_case.get("Bekräftat varför nu", "—"))
                _conflict = bool(_case.get("Bekräftat varför nu konflikt", False))
                with st.container(border=True):
                    st.markdown(f"**{_name} · {_ticker}** — {_status}")
                    if _conflict:
                        st.warning(_text)
                    else:
                        st.write(_text)
            st.caption("Borsify behöver minst två oberoende historiska kontroller innan den säger att flera saker bekräftar samma förändring. Saknad historik räknas aldrig som stöd.")

        underfollowed_view = st.session_state.get("bq_underfollowed_discovery", pd.DataFrame())
        if isinstance(underfollowed_view, pd.DataFrame) and not underfollowed_view.empty and "Underfollowed kandidat" in underfollowed_view.columns:
            _uf = underfollowed_view[underfollowed_view["Underfollowed kandidat"].fillna(False).astype(bool)].copy()
            if not _uf.empty:
                with st.expander("Underfollowed – förbättras innan analytikerna hunnit bli många", expanded=False):
                    _uf = _uf.assign(
                        __change=pd.to_numeric(_uf.get("Fundamental förändring antal"), errors="coerce").fillna(-1),
                        __quality=pd.to_numeric(_uf.get("Kvalitet"), errors="coerce").fillna(-1e9),
                    ).sort_values(["__change", "__quality"], ascending=[False, False]).head(10)
                    _cols = [c for c in [
                        "Ticker", "Namn", "Land", "Underfollowed status", "Analytiker antal",
                        "Fundamental förändring", "Fundamental förändring detalj", "Underfollowed förklaring"
                    ] if c in _uf.columns]
                    st.dataframe(_uf[_cols], use_container_width=True, hide_index=True)
                    st.caption("Låg analytikerbevakning är aldrig en positiv signal i sig. För att synas här krävs observerad analystäckning på högst tre analytiker och en verifierad fundamental förbättring mot en äldre fryst bredscan. Saknad analystäckning kvalificerar inte.")

        estimate_radar_view = st.session_state.get("bq_estimate_revision_radar", pd.DataFrame())
        if isinstance(estimate_radar_view, pd.DataFrame) and not estimate_radar_view.empty:
            with st.expander("Estimatförändringar i kandidatpoolen", expanded=False):
                _er = estimate_radar_view.copy()
                _er = _er.sort_values(
                    ["Estimat Radar underreaktion", "Estimat tillförlitlighetsvikt", "EPS-revisionsbalans", "EPS-estimat förändring"],
                    ascending=[False, False, False, False],
                    na_position="last",
                ).head(10)
                _cols = [c for c in ["Ticker", "Namn", "Estimat Radar status", "EPS-estimat förändring", "EPS-revisionsbalans", "Analytiker antal", "1 mån", "Estimat Radar förklaring"] if c in _er.columns]
                st.dataframe(_er[_cols], use_container_width=True, hide_index=True)
                st.caption("Radarn skapar inget nytt investeringsscore. Den reserverar bara en liten väg till djupanalys för verifierade estimathöjningar; skarpa kursfall behandlas som konflikt, inte som en automatisk köpfördel.")

        consensus_view = st.session_state.get("bq_consensus_change_radar", pd.DataFrame())
        if isinstance(consensus_view, pd.DataFrame) and not consensus_view.empty and "Konsensusförändring status" in consensus_view.columns:
            _cc = consensus_view.copy()
            _interesting = _cc[
                (_cc.get("Konsensusförändring kandidat", False).fillna(False).astype(bool))
                | (_cc.get("Konsensusförändring varning", False).fillna(False).astype(bool))
                | (_cc["Konsensusförändring status"].astype(str).str.contains("Bevakningen breddas", case=False, regex=False))
            ].copy()
            if not _interesting.empty:
                with st.expander("Analytikerkollektivet ändrar sig – Consensus Change", expanded=False):
                    _interesting = _interesting.assign(
                        __candidate=_interesting.get("Konsensusförändring kandidat", False).fillna(False).astype(int),
                        __strong=_interesting.get("Konsensusförändring stark", False).fillna(False).astype(int),
                        __breadth=pd.to_numeric(_interesting.get("Konsensus breadth förändring"), errors="coerce").fillna(-99),
                    ).sort_values(["__candidate", "__strong", "__breadth"], ascending=[False, False, False]).head(10)
                    _cols = [c for c in [
                        "Ticker", "Namn", "Konsensusförändring status", "Konsensus breadth förändring",
                        "Konsensus uppgraderingar 45d", "Konsensus nedgraderingar 45d",
                        "Konsensus initierad bevakning 45d", "Konsensus aktiva analyshus 45d",
                        "Riktkurs dispersion", "Riktkurs potential", "Konsensusminne status",
                        "Konsensusminne jämförelsedatum", "Konsensusförändring förklaring"
                    ] if c in _interesting.columns]
                    st.dataframe(_interesting[_cols], use_container_width=True, hide_index=True)
                    st.caption("Consensus Change skapar inget nytt score. En enskild rekommendation eller riktkurs räcker aldrig: Borsify kräver bredare förändring mellan flera analytiker. Riktkursdispersion visas som nuläge. Förändring i dispersion påstås bara när Borsify faktiskt har ett äldre fryst PIT-snapshot; ingen historik backfillas.")

        if isinstance(consensus_view, pd.DataFrame) and not consensus_view.empty and "Expectation Gap status" in consensus_view.columns:
            _eg = consensus_view[
                consensus_view.get("Expectation Gap kandidat", False).fillna(False).astype(bool)
                | consensus_view.get("Expectation Gap varning", False).fillna(False).astype(bool)
            ].copy()
            if not _eg.empty:
                with st.expander("Expectation Gap – förbättring kontra förväntningar", expanded=False):
                    _eg = _eg.assign(
                        __candidate=_eg.get("Expectation Gap kandidat", False).fillna(False).astype(int),
                        __strong=_eg.get("Expectation Gap stark", False).fillna(False).astype(int),
                        __upside=pd.to_numeric(_eg.get("Expectation Gap riktkurs potential"), errors="coerce").fillna(-99),
                    ).sort_values(["__candidate", "__strong", "__upside"], ascending=[False, False, False]).head(10)
                    _cols = [c for c in ["Ticker", "Namn", "Expectation Gap status", "Expectation Gap förändringsfamiljer", "Konsensus bullish andel", "Konsensus analytiker antal", "Riktkurs potential", "Expectation Gap förklaring"] if c in _eg.columns]
                    st.dataframe(_eg[_cols], use_container_width=True, hide_index=True)
                    st.caption("Expectation Gap är ett kontextlager, inte ett score. Borsify kräver först oberoende verifierad förändring och påstår aldrig att marknaden ligger efter när förväntningsdata är för tunn.")

        if isinstance(consensus_view, pd.DataFrame) and not consensus_view.empty and "Crowded varning" in consensus_view.columns:
            _crowded = consensus_view[consensus_view["Crowded varning"].fillna(False).astype(bool)].copy()
            if not _crowded.empty:
                with st.expander("Förväntningsrisk – när nästan alla redan är positiva", expanded=False):
                    _cols = [c for c in ["Ticker", "Namn", "Crowded status", "Konsensus bullish andel", "Konsensus analytiker antal", "Riktkurs potential", "Värdering", "Crowded förklaring"] if c in _crowded.columns]
                    st.dataframe(_crowded[_cols], use_container_width=True, hide_index=True)
                    st.caption("Crowding är en riskflagga, inte en säljsignal och inte ett nytt score. Låg analystäckning eller popularitet i sig räcker aldrig.")

        report_delta_view = st.session_state.get("bq_report_delta_radar", pd.DataFrame())
        if isinstance(report_delta_view, pd.DataFrame) and not report_delta_view.empty:
            _sale_view = add_negative_overreaction(report_delta_view)
            _sale_view = _sale_view[pd.to_numeric(_sale_view.get("Negativ överreaktion nivå"), errors="coerce").fillna(0).ne(0)].copy()
            if not _sale_view.empty:
                with st.expander("Quality on sale – negativ överreaktion", expanded=False):
                    _sale_view = _sale_view.sort_values(["Negativ överreaktion rangvärde"], ascending=False)
                    _cols = [c for c in ["Ticker", "Namn", "Negativ överreaktion", "Dagsförändring", "1 mån", "Report Delta status", "Konsensusminne status", "Riktkurs potential", "Negativ överreaktion förklaring"] if c in _sale_view.columns]
                    st.dataframe(_sale_view[_cols].head(20), use_container_width=True, hide_index=True)
                    st.caption("Ett kursfall räcker aldrig. Borsify kräver att bolagskvalitet och oberoende rapport-/konsensusevidens inte bekräftar fallet; annars markeras caset som möjlig fallande kniv.")

        if isinstance(report_delta_view, pd.DataFrame) and not report_delta_view.empty and "Report Delta status" in report_delta_view.columns:
            _rd = report_delta_view.copy()
            _interesting = _rd[
                (_rd.get("Report Delta kandidat", False).fillna(False).astype(bool))
                | (_rd["Report Delta status"].astype(str).str.contains("negativ|marknaden säger emot", case=False, regex=True))
            ].copy()
            if not _interesting.empty:
                with st.expander("Vad förändrades i senaste rapporten?", expanded=False):
                    _interesting = _interesting.assign(
                        __candidate=_interesting.get("Report Delta kandidat", False).fillna(False).astype(int),
                        __under=_interesting.get("Report Delta underreaktion", False).fillna(False).astype(int),
                        __pos=pd.to_numeric(_interesting.get("Report Delta positiva"), errors="coerce").fillna(-1),
                        __neg=pd.to_numeric(_interesting.get("Report Delta negativa"), errors="coerce").fillna(99),
                    ).sort_values(["__candidate", "__under", "__pos", "__neg"], ascending=[False, False, False, True]).head(10)
                    _cols = [c for c in [
                        "Ticker", "Namn", "Report Delta status", "Report Delta positiva", "Report Delta negativa",
                        "Report Delta kursreaktion", "Report Delta fortsatt rörelse", "Report Delta guidance",
                        "Report Delta datagrund", "Rapport text verifierad", "Rapport titel",
                        "Rapport publicerad", "Rapport URL", "Rapport kontroll",
                        "Report Delta förklaring"
                    ] if c in _interesting.columns]
                    st.dataframe(_interesting[_cols], use_container_width=True, hide_index=True)
                    st.caption("Report Delta skapar inget nytt score. Den skiljer på vad bolagets siffror faktiskt ändrade, vad analytikerna gjorde efter rapporten och hur kursen reagerade. Originalrapporten markeras bara som verifierad när Borsify faktiskt har primär rapporttext; saknad konsensus för omsättning/marginal fylls aldrig i med gissningar.")

        owner_signal_view = st.session_state.get("bq_owner_signal_radar", pd.DataFrame())
        if isinstance(owner_signal_view, pd.DataFrame) and not owner_signal_view.empty and "Ägarsignal status" in owner_signal_view.columns:
            _os = owner_signal_view.copy()
            _interesting = _os[
                (_os.get("Ägarsignal kandidat", False).fillna(False).astype(bool))
                | (_os["Ägarsignal status"].astype(str).str.contains("utspädning|skuldsättning|försiktighet", case=False, regex=True))
            ].copy()
            if not _interesting.empty:
                with st.expander("Ägarsignaler: återköp, skuld och insiderköp", expanded=False):
                    _interesting = _interesting.assign(
                        __candidate=_interesting.get("Ägarsignal kandidat", False).fillna(False).astype(int),
                        __strong=_interesting.get("Ägarsignal stark", False).fillna(False).astype(int),
                        __buyers=pd.to_numeric(_interesting.get("Insider köpare antal"), errors="coerce").fillna(-1),
                        __buyback=pd.to_numeric(_interesting.get("Kapitalallokering återköpsyield"), errors="coerce").fillna(-999),
                    ).sort_values(["__candidate", "__strong", "__buyers", "__buyback"], ascending=[False, False, False, False]).head(10)
                    _cols = [c for c in [
                        "Ticker", "Namn", "Ägarsignal status", "Kapitalallokering återköpsyield",
                        "Kapitalallokering skuldtrend", "Insider köpare antal", "Insider köp antal",
                        "Insider sälj antal", "Ägarsignal förklaring"
                    ] if c in _interesting.columns]
                    st.dataframe(_interesting[_cols], use_container_width=True, hide_index=True)
                    st.caption("Ägarsignalen skapar inget nytt score. Nettoåterköp bedöms efter observerad aktieutgivning, skuld vägs in och insiderstöd kräver flera oberoende verifierbara köp. Optioner, grants och saknad data räknas inte som köpbevis.")

        management_view = st.session_state.get("bq_management_signal_radar", pd.DataFrame())
        if isinstance(management_view, pd.DataFrame) and not management_view.empty and "Ledningssignal status" in management_view.columns:
            _ms = management_view.copy()
            _interesting = _ms[
                (_ms.get("Ledningssignal kandidat", False).fillna(False).astype(bool))
                | (_ms.get("Ledningssignal varning", False).fillna(False).astype(bool))
            ].copy()
            if not _interesting.empty:
                with st.expander("Vad säger ledningen konkret?", expanded=False):
                    _interesting = _interesting.assign(
                        __candidate=_interesting.get("Ledningssignal kandidat", False).fillna(False).astype(int),
                        __strong=_interesting.get("Ledningssignal stark", False).fillna(False).astype(int),
                        __pos=pd.to_numeric(_interesting.get("Ledningssignal positiva"), errors="coerce").fillna(0),
                        __neg=pd.to_numeric(_interesting.get("Ledningssignal negativa"), errors="coerce").fillna(99),
                    ).sort_values(["__candidate", "__strong", "__pos", "__neg"], ascending=[False, False, False, True]).head(10)
                    _cols = [c for c in [
                        "Ticker", "Namn", "Ledningssignal status", "Ledningsminne status", "Ledningssignal positiva ämnen",
                        "Ledningssignal negativa ämnen", "Ledningsminne förbättrade ämnen", "Ledningsminne försämrade ämnen",
                        "Ledningssignal förklaring", "Ledningsminne förklaring"
                    ] if c in _interesting.columns]
                    st.dataframe(_interesting[_cols], use_container_width=True, hide_index=True)
                    st.caption("Ledningslagret är medvetet konservativt: bara explicita CEO/CFO/VD-uttalanden om konkreta operativa ämnen räknas. Det är inte sentimentanalys och inte en fullständig rapporttranskriptanalys. Ett enstaka positivt uttalande räcker aldrig för en discovery-plats.")

        value_chain_view = st.session_state.get("bq_value_chain_radar", pd.DataFrame())
        verified_view = st.session_state.get("bq_verified_relationship_radar")
        if isinstance(verified_view, pd.DataFrame) and not verified_view.empty and "Verifierad relation status" in verified_view.columns:
            _vr = verified_view.copy()
            _vr_i = _vr[_vr.get("Verifierad relation kandidat", False).fillna(False).astype(bool)].copy()
            if not _vr_i.empty:
                with st.expander("Verifierade bolagsrelationer – riktig ekonomisk koppling", expanded=False):
                    _vr_i = _vr_i.assign(__strong=_vr_i.get("Verifierad relation stark", False).fillna(False).astype(int), __sources=pd.to_numeric(_vr_i.get("Verifierad relation källor antal"), errors="coerce").fillna(0)).sort_values(["__strong","__sources"], ascending=[False,False]).head(10)
                    _cols=[c for c in ["Ticker","Namn","Verifierad relation status","Verifierad relation källbolag","Verifierad relation typ","Verifierad relation operativ","Verifierad relation evidens","Fundamentala upptäcktslinser","1 mån","Verifierad relation förklaring"] if c in _vr_i.columns]
                    st.dataframe(_vr_i[_cols], use_container_width=True, hide_index=True)
                    st.caption("Här visas bara explicit källbelagda relationer. Från v3.62 får bara riktade operativa relationer, främst kund → leverantör, skapa cross-company discovery. Ägarrelationer finns kvar som verifierad kontext men får inte längre låtsas vara operativ read-through.")

        relationship_change_view = st.session_state.get("bq_relationship_change_radar", pd.DataFrame())
        if isinstance(relationship_change_view, pd.DataFrame) and not relationship_change_view.empty and "Relationsförändring status" in relationship_change_view.columns:
            _rc = relationship_change_view.copy()
            _rc_i = _rc[
                (_rc.get("Relationsförändring kandidat", False).fillna(False).astype(bool))
                | (_rc["Relationsförändring status"].astype(str).str.contains("motbevis|redan rört|betydelsen", case=False, regex=True))
            ].copy()
            if not _rc_i.empty:
                with st.expander("Relationen förändras – har kopplingen blivit viktigare?", expanded=False):
                    _rc_i = _rc_i.assign(
                        __strong=_rc_i.get("Relationsförändring stark", False).fillna(False).astype(int),
                        __age=pd.to_numeric(_rc_i.get("Relationsförändring ålder dagar"), errors="coerce").fillna(99999),
                    ).sort_values(["__strong", "__age"], ascending=[False, True]).head(10)
                    _cols = [c for c in [
                        "Ticker", "Namn", "Relationsförändring status", "Relationsförändring källbolag",
                        "Relationsförändring typ", "Relationsförändring datum", "Relationsförändring materialitet",
                        "Relationsförändring materialitet evidens", "1 mån", "Relationsförändring förklaring"
                    ] if c in _rc_i.columns]
                    st.dataframe(_rc_i[_cols], use_container_width=True, hide_index=True)
                    st.caption("Detta lager skiljer en statisk kund-/leverantörsrelation från en explicit förändring som nytt avtal, förlängning eller högre volym. 'Materialitet' betyder här hur tydligt omfattningen är källbelagd – Borsify hittar aldrig på intäktsandelar eller resultateffekt.")

        _rh = st.session_state.get("bq_relationship_registry_health", {})
        if isinstance(_rh, dict) and _rh.get("relations", 0):
            with st.expander("Relationsdatabas – täckning och källkvalitet", expanded=False):
                st.write(
                    f"{int(_rh.get('relations', 0))} verifierade relationer · "
                    f"{int(_rh.get('source_companies', 0))} källbolag · "
                    f"{int(_rh.get('target_companies', 0))} målbolag · "
                    f"{int(_rh.get('customer_supplier_relations', 0))} kund→leverantör"
                )
                _share = _rh.get("primary_source_share")
                if isinstance(_share, (int, float)) and pd.notna(_share):
                    st.caption(f"Primärkällor: {_share:.0%} · Föråldrade verifieringar: {int(_rh.get('stale_relations', 0))}. Registret växer bara genom explicit källbelagda poster; ingen branschheuristik auto-promoveras.")

        if isinstance(value_chain_view, pd.DataFrame) and not value_chain_view.empty and "Värdekedja status" in value_chain_view.columns:
            _vc = value_chain_view.copy()
            _interesting = _vc[(_vc.get("Värdekedja kandidat", False).fillna(False).astype(bool)) | (_vc["Värdekedja status"].astype(str).str.contains("motbevis|redan rört", case=False, regex=True))].copy()
            if not _interesting.empty:
                with st.expander("Värdekedjan rör sig – vilka bolag kan påverkas härnäst?", expanded=False):
                    _interesting = _interesting.assign(__candidate=_interesting.get("Värdekedja kandidat", False).fillna(False).astype(int), __strong=_interesting.get("Värdekedja stark", False).fillna(False).astype(int), __sources=pd.to_numeric(_interesting.get("Värdekedja källor antal"), errors="coerce").fillna(0)).sort_values(["__candidate","__strong","__sources"], ascending=[False,False,False]).head(10)
                    _cols=[c for c in ["Ticker","Namn","Sektor","Bransch","Värdekedja status","Värdekedja roll","Värdekedja källbolag","Värdekedja relation","Fundamentala upptäcktslinser","1 mån","Värdekedja förklaring"] if c in _interesting.columns]
                    st.dataframe(_interesting[_cols], use_container_width=True, hide_index=True)
                    st.caption("Värdekedjeläsningen använder transparenta branschroller och riktade ekonomiska samband. Den påstår inte att de namngivna bolagen har ett verifierat kund-/leverantörsavtal. Eget fundamentalt stöd krävs och färska negativa motbevis väger tyngre.")

        sector_view = st.session_state.get("bq_sector_readthrough_radar", pd.DataFrame())
        if isinstance(sector_view, pd.DataFrame) and not sector_view.empty and "Sektorläsning status" in sector_view.columns:
            _sr = sector_view.copy()
            _interesting = _sr[
                (_sr.get("Sektorläsning kandidat", False).fillna(False).astype(bool))
                | (_sr["Sektorläsning status"].astype(str).str.contains("motbevis|redan rört", case=False, regex=True))
            ].copy()
            if not _interesting.empty:
                with st.expander("Sektorn rör sig – vilka peers kan stå på tur?", expanded=False):
                    _interesting = _interesting.assign(
                        __candidate=_interesting.get("Sektorläsning kandidat", False).fillna(False).astype(int),
                        __strong=_interesting.get("Sektorläsning stark", False).fillna(False).astype(int),
                        __sources=pd.to_numeric(_interesting.get("Sektorläsning källor antal"), errors="coerce").fillna(0),
                    ).sort_values(["__candidate", "__strong", "__sources"], ascending=[False, False, False]).head(10)
                    _cols = [c for c in [
                        "Ticker", "Namn", "Sektor", "Bransch", "Sektorläsning status",
                        "Sektorläsning nivå", "Sektorläsning källbolag", "Fundamentala upptäcktslinser",
                        "1 mån", "Sektorläsning förklaring"
                    ] if c in _interesting.columns]
                    st.dataframe(_interesting[_cols], use_container_width=True, hide_index=True)
                    st.caption("Sektorläsning är en discovery-ledtråd, inte bolagsspecifikt bevis. En peer måste ha eget fundamentalt stöd, får inte ha färska negativa motbevis och får inte redan ha rusat >12 % på en månad. Samma sektor betyder inte automatiskt samma värdekedja.")

        acceleration_view = st.session_state.get("bq_estimate_revision_radar", pd.DataFrame())
        if isinstance(acceleration_view, pd.DataFrame) and not acceleration_view.empty and "Förväntningsacceleration kandidat" in acceleration_view.columns:
            _ea = acceleration_view[acceleration_view["Förväntningsacceleration kandidat"].fillna(False).astype(bool)].copy()
            if not _ea.empty:
                with st.expander("Förväntningar som accelererar", expanded=False):
                    _ea = _ea.sort_values(
                        ["Förväntningsacceleration stark", "Revisionsbalans 7d", "EPS förändring 7d"],
                        ascending=[False, False, False], na_position="last"
                    ).head(10)
                    _cols = [c for c in ["Ticker", "Namn", "Förväntningsacceleration status", "EPS förändring 7d", "EPS förändring 30d", "Revisionsbalans 7d", "Fundamental förändring detalj", "Förväntningsacceleration förklaring"] if c in _ea.columns]
                    st.dataframe(_ea[_cols], use_container_width=True, hide_index=True)
                    st.caption("Acceleration är en discovery-signal, inte ett nytt score: Borsify letar efter estimat som förbättras snabbare nyligen och kräver revisionsbredd eller fundamental bekräftelse.")

        # Compare fresh events only with already-frozen point-in-time history.
        # The current run is deliberately not part of its own reference sample.
        try:
            event_memory_ledger = get_recommendation_records(limit=2000)
            deep_longlist = apply_news_event_memory(deep_longlist, event_memory_ledger)
            short_longlist = apply_news_event_memory(short_longlist, event_memory_ledger)
            resolve_runtime_issue(st.session_state, "news_event_memory")
        except Exception as exc:
            record_runtime_issue(st.session_state, "news_event_memory", exc, "historisk nyhetsrespons kunde inte användas")

        # Freeze only analyses that were actually run. This preserves point-in-time
        # history without forcing every homepage visit to perform deep Yahoo requests.
        ledger_records = build_recommendation_records(
            short_longlist, "short", APP_VERSION, profile, market, max_records=5
        ) + build_recommendation_records(
            deep_longlist, "long", APP_VERSION, profile, market, max_records=5
        )
        save_recommendation_records(ledger_records)

        try:
            relevance_ledger = get_recommendation_records(limit=500)
            relevance_date = pd.Timestamp.now(tz="UTC").date().isoformat()
            short_longlist = apply_recommendation_relevance(
                short_longlist, relevance_ledger, "short", profile, market, relevance_date
            )
            deep_longlist = apply_recommendation_relevance(
                deep_longlist, relevance_ledger, "long", profile, market, relevance_date
            )
            resolve_runtime_issue(st.session_state, "recommendation_relevance")
        except Exception as exc:
            record_runtime_issue(st.session_state, "recommendation_relevance", exc, "rekommendationernas aktualitet kunde inte bedömas")

        try:
            short_longlist = apply_case_plans(short_longlist, "short")
            deep_longlist = apply_case_plans(deep_longlist, "long")
            resolve_runtime_issue(st.session_state, "case_plans")
        except Exception as exc:
            record_runtime_issue(st.session_state, "case_plans", exc, "omprövningsplaner kunde inte skapas")

        try:
            refresh_due_recommendation_outcomes(max_records=6)
            resolve_runtime_issue(st.session_state, "recommendation_outcomes")
        except Exception as exc:
            record_runtime_issue(st.session_state, "recommendation_outcomes", exc, "mogna rekommendationsutfall kunde inte uppdateras")

        discover_daily, discover_ideas, discover_radar = st.tabs(["Aktier", "Nya uppslag", f"Signaler ({unread_signals})"])
        with discover_daily:
            st.markdown("## Vad rekommenderar Borsify idag?")
            st.caption(
                "Tre olika frågor kräver tre olika svar. Borsify rankar därför aktier separat för kort sikt, upp till ett år och mycket lång ägarhorisont."
            )

            def _horizon_section(title: str, subtitle: str, horizon: str, score_col: str):
                ranked = top_ranked(filtered, horizon, limit=10)
                st.markdown(f"### {title}")
                st.caption(subtitle)
                if ranked.empty:
                    st.info("Ingen aktie uppfyller Borsifys krav i den här kategorin just nu. Hellre tomt än ett svagt förslag.")
                    return ranked

                ranked = add_full_deal_evidence(ranked, horizon)
                # Entry timing may downgrade the action wording, but never upgrades a weak case.
                _red = ranked["Ingångsläge nivå"].eq("red")
                _orange = ranked["Ingångsläge nivå"].eq("orange")
                if horizon == "medium":
                    ranked.loc[_red, ["Signal", "Signal kort"]] = ["AVVAKTA", "Jaga inte kursen"]
                    ranked.loc[_red, "Signal förklaring"] = "Caset kan vara bra, men kursen har sprungit för långt för ett färskt köp just nu."
                    ranked.loc[_orange & ranked["Signal"].isin(["KÖP NU", "KÖP"]), ["Signal", "Signal kort"]] = ["BEVAKA", "Vänta på bättre ingång"]
                elif horizon == "year":
                    ranked.loc[_red, ["Signal", "Signal kort"]] = ["AVVAKTA INGÅNG", "Bra case – fel pris just nu"]
                    ranked.loc[_orange & ranked["Signal"].eq("KÖP / ÄG"), ["Signal", "Signal kort"]] = ["BYGG POSITION", "Köp stegvis"]
                elif horizon == "lifetime":
                    ranked.loc[_red, ["Signal", "Signal kort"]] = ["BEVAKA PRISET", "Bra bolag – jaga inte"]
                history_profile = f"{profile}::horizon::{horizon}"
                previous_horizon = previous_radar_snapshot(history_profile, limit=10)
                ranked = add_change_signals(ranked, previous_horizon, score_col, horizon)
                ranked = add_change_reasons(ranked, previous_horizon, horizon)
                history_frame = ranked.copy()
                history_frame["Borsify Score"] = pd.to_numeric(history_frame.get(score_col), errors="coerce")
                save_radar_history(history_frame, history_profile)
                first = ranked.iloc[0]
                with st.container(border=True):
                    a, b = st.columns([4.2, 1.0])
                    a.markdown(f"#### Förstaval · {_stock_identity(first)}")
                    a.markdown(f"**Signal: {first.get('Signal', '—')}** · {first.get('Signal kort', '')}")
                    a.caption(f"Förändring: {first.get('Förändring', '—')} · {first.get('Förändring förklaring', '')}")
                    if str(first.get("Vad har förändrats", "")).strip():
                        a.markdown(f"**Vad har förändrats?** {plain_finance_text(first.get('Vad har förändrats'))}")
                    a.write(plain_finance_text(first.get("Varför köpa") or first.get("Horisontförklaring") or "—"))
                    score = _num(first.get("Borsify slutbetyg"))
                    if not np.isfinite(score):
                        score = _num(first.get("Borsify Score"))
                    if not np.isfinite(score):
                        score = _num(first.get(score_col))
                    b.metric("Borsify", f"{score:.0f}/100" if np.isfinite(score) else "—")
                    st.caption(plain_finance_text(first.get("Signal förklaring") or ""))
                    _axis1, _axis2 = st.columns(2)
                    _axis1.markdown(f"**Bolaget:** {first.get('Bolagsbedömning', '—')}")
                    _axis1.caption(str(first.get('Bolagsbedömning skäl', '')))
                    _axis2.markdown(f"**Köpläget:** {first.get('Ingångsläge', '—')}")
                    _axis2.caption(f"{first.get('Ingångsläge skäl', '')}" + (f" · Vänta på: {first.get('Vänta på')}" if str(first.get('Vänta på', '')) not in {'', 'ingen tydlig väntesignal'} else ""))
                    if str(first.get("Bättre ingång", "—")) != "—":
                        _curr = str(first.get("Valuta", "") or "")
                        _axis2.info(f"**Bättre ingång:** {first.get('Bättre ingång')} {_curr}".strip())
                    st.markdown("#### Affären sammanfattad")
                    st.markdown(f"**Varför Borsify gillar aktien:** {plain_finance_text(first.get('Decision Brief tes', '—'))}")
                    st.markdown(f"**Vad priset verkar kräva:** {first.get('Market-Implied Expectations', '❔ Kan inte bedömas')}")
                    st.caption(str(first.get("Market-Implied Expectations förklaring", "")))
                    _brief1, _brief2 = st.columns(2)
                    _brief1.markdown("**Varför aktien kan vara billigare än den borde**")
                    _brief1.write(plain_finance_text(first.get("Decision Brief market wrong", "—")))
                    _brief2.markdown("**Vad kan få fler att bli intresserade av aktien**")
                    _brief2.write(plain_finance_text(first.get("Decision Brief recognition", "—")))
                    st.markdown(f"**När kan det hända?:** {first.get('Decision Brief timing', 'Borsify vet inte när det kan hända.')}")
                    st.caption(str(first.get("Decision Brief payoff", "Borsify kan inte säga säkert hur stor uppgången kan bli eller hur lång tid den kan ta.")))
                    _risk1, _risk2 = st.columns(2)
                    _risk1.markdown("**Största risken**")
                    _risk1.write(plain_finance_text(first.get("Decision Brief risk", "—")))
                    _risk2.markdown("**När ändrar Borsify sig?**")
                    _risk2.write(plain_finance_text(first.get("Decision Brief invalidation", "—")))
                    st.caption(f"Hur bra är informationen?  {first.get('Decision Brief confidence', '—')}")
                    st.markdown(f"**Position:** {first.get('Positionsråd', '—')} · första storlek {first.get('Första positionsstorlek', '—')}")
                    if horizon == "medium":
                        st.markdown("#### När bör jag sälja?")
                        st.write(first.get("Tänkt tid att äga", "Några dagar till några veckor."))
                        st.write(first.get("När ska jag kontrollera igen?", "Kontrollera aktien regelbundet."))
                        st.warning(first.get("När bör jag sälja?", "Sälj när det som gjorde aktien intressant inte längre gäller."))
                    elif horizon == "year":
                        st.markdown("#### Plan för ungefär ett år")
                        st.write("Tanken är att äga så länge skälen till köpet fortfarande gäller – högst ungefär ett år i den här listan.")
                        st.write(f"**Kontrollera särskilt:** {plain_finance_text(first.get('Decision Brief invalidation', 'om bolaget börjar gå sämre eller priset blir för högt'))}")
                        st.info("Borsify ska inte behålla aktien bara för att ett år inte har gått. Om köpskälet försvinner ska den omprövas tidigare.")
                    elif horizon == "lifetime":
                        st.markdown("#### Vad krävs för att äga länge?")
                        st.write("Det här betyder inte att aktien ska behållas oavsett vad som händer. Bolaget måste fortsätta vara starkt.")
                        st.write(f"**Borsify ändrar sig om:** {plain_finance_text(first.get('Decision Brief invalidation', 'bolagets kvalitet eller ekonomi försämras tydligt'))}")
                        st.info("Kontrollera efter varje större rapport och när något viktigt förändras i bolaget.")

                    with st.expander("Visa hur Borsify räknade (tekniska detaljer)", expanded=False):
                        _evidence_rows = [
                            ("Deal Conviction", first.get("Deal Conviction", "—"), first.get("Deal Conviction förklaring", "")),
                            ("Deal Nose", first.get("Deal Nose", "—"), first.get("Deal Nose förklaring", "")),
                            ("Value Trap-test", first.get("Value Trap Test", "—"), first.get("Value Trap förklaring", "")),
                            ("Tidig felprissättning", first.get("Early Mispricing", "—"), first.get("Early Mispricing förklaring", "")),
                            ("Market Blind Spot", first.get("Market Blind Spot", "—"), first.get("Market Blind Spot förklaring", "")),
                            ("Catalyst-to-Recognition", first.get("Catalyst-to-Recognition", "—"), first.get("Catalyst-to-Recognition förklaring", "")),
                            ("Recognition Window", first.get("Recognition Window", "—"), first.get("Recognition Window förklaring", "")),
                            ("Market-Implied Expectations", first.get("Market-Implied Expectations", "—"), first.get("Market-Implied Expectations förklaring", "")),
                            ("Decision Support", first.get("Decision Support", "—"), first.get("Decision Support förklaring", "")),
                            ("God affär", first.get("Affärsläge", "—"), first.get("Affärsläge förklaring", "")),
                        ]
                        for _label, _value, _why in _evidence_rows:
                            st.markdown(f"**{_label}:** {_value}")
                            if str(_why).strip():
                                st.caption(str(_why))

                _why1 = explain_top_pick(ranked, score_col, horizon)
                with st.container(border=True):
                    st.markdown("#### Varför är den här #1?")
                    st.write(plain_finance_text(_why1["Varför #1"]))
                    if _why1.get("Utmanarnas fördelar"):
                        st.caption("**Vad #2–#3 gör bättre:** " + plain_finance_text(_why1["Utmanarnas fördelar"]))
                    _cmp = _why1.get("Jämförelseunderlag")
                    if isinstance(_cmp, pd.DataFrame) and not _cmp.empty:
                        st.dataframe(_cmp, use_container_width=True, hide_index=True)

                _paths = challenger_paths(ranked, score_col, horizon)
                if isinstance(_paths, pd.DataFrame) and not _paths.empty:
                    with st.container(border=True):
                        st.markdown("#### Vad krävs för att #2 eller #3 ska bli #1?")
                        st.caption("Trösklarna kommer från Borsifys aktuella rankordning. De är villkor, inte prognoser om att måtten faktiskt kommer nå dit.")
                        for _, _p in _paths.iterrows():
                            st.markdown(f"**#{int(_p['#'])} · {_p['Utmanare']}**")
                            st.write(plain_finance_text(_p["Formell väg till #1"]))
                            if str(_p.get("Bevaka också", "")):
                                st.caption("Bevaka också: " + plain_finance_text(_p["Bevaka också"]))

                table = ranked.head(10).copy()
                table.insert(0, "#", range(1, len(table) + 1))
                table["Aktie"] = table.apply(_stock_identity, axis=1)
                table["Score"] = pd.to_numeric(table.get(score_col), errors="coerce").round(0)
                previous = table["Score"].shift(1)
                table["Till platsen ovan"] = (table["Score"] - previous).where(previous.notna())
                table["Till platsen ovan"] = table["Till platsen ovan"].apply(
                    lambda x: "—" if pd.isna(x) else f"{x:+.0f} p"
                )
                price = pd.to_numeric(table.get("Pris"), errors="coerce")
                currencies = table.get("Valuta", pd.Series("", index=table.index)).fillna("").astype(str)
                table["Kurs"] = [
                    "—" if not np.isfinite(v) else f"{v:,.2f} {cur}".replace(",", " ").replace(".00 ", " ")
                    for v, cur in zip(price, currencies)
                ]
                table["Land"] = table.get("Land", pd.Series("—", index=table.index)).fillna("—")
                table["Risk"] = table.apply(lambda r: plain_finance_text(r.get("Största risk") or "—"), axis=1)
                table["Varför ändrad?"] = table.get("Vad har förändrats", pd.Series("—", index=table.index)).apply(lambda x: plain_finance_text(x or "—"))
                table["Bolag"] = table.get("Bolagsbedömning", "—")
                table["Köpläge"] = table.get("Ingångsläge", "—")
                table["Varför nu"] = table.get("Decision Brief recognition", pd.Series("—", index=table.index)).apply(plain_finance_text)
                table["Datatillit"] = table.get("Decision Brief confidence", "—")
                table["Förväntningar"] = table.get("Market-Implied Expectations", "—")
                _zones = table.get("Bättre ingång", pd.Series("—", index=table.index)).fillna("—").astype(str)
                table["Bättre ingång"] = [
                    z if z == "—" else f"{z} {cur}".strip()
                    for z, cur in zip(_zones, currencies)
                ]
                show_cols = ["#", "Aktie", "Signal", "Förväntningar", "Köpläge", "Varför nu", "Recognition Window", "Risk", "Datatillit", "Score"]
                st.markdown("**Topp 10 i kategorin**")
                st.dataframe(table[show_cols], use_container_width=True, hide_index=True)
                st.caption("Listan visar beslutet först. Klicka på en aktie nedan för full Borsify-analys och AI-frågor.")
                with st.expander("Visa teknisk jämförelsetabell", expanded=False):
                    diagnostic_cols = [c for c in [
                        "#", "Aktie", "Land", "Kurs", "Deal Nose", "Value Trap Test",
                        "Early Mispricing", "Market Blind Spot", "Catalyst-to-Recognition",
                        "Recognition Window payoff", "Market-Implied Expectations", "Deal Conviction", "Analysis Confidence",
                        "Decision Support", "KPI Inflection", "Management execution",
                        "Business KPI coverage", "Revision breadth", "Positionsråd",
                        "Första positionsstorlek", "Bättre ingång", "Förändring",
                        "Varför ändrad?", "Till platsen ovan"
                    ] if c in table.columns]
                    st.dataframe(table[diagnostic_cols], use_container_width=True, hide_index=True)
                    st.caption("Bättre ingång är en härledd referenszon från prisstrukturen, inte en prognos eller garanterad köpnivå.")
                for _rank, (_, _r) in enumerate(ranked.head(10).iterrows(), start=1):
                    _ticker = str(_r.get("Ticker", "—"))
                    _name = str(_r.get("Namn", _ticker) or _ticker)
                    if st.button(f"{_rank}. {_name} · {_ticker}  →", key=f"open_{horizon}_{_ticker}_{_rank}", use_container_width=True):
                        st.session_state["bq_open_stock_ticker"] = _ticker
                        st.session_state["bq_open_stock_horizon"] = horizon
                        st.session_state["bq_open_stock_rank"] = _rank
                _open_ticker = str(st.session_state.get("bq_open_stock_ticker") or "")
                _open_horizon = str(st.session_state.get("bq_open_stock_horizon") or "")
                if _open_ticker and _open_horizon == horizon:
                    _match = ranked[ranked["Ticker"].astype(str).eq(_open_ticker)]
                    if not _match.empty:
                        st.divider()
                        if st.button("Stäng analys", key=f"close_{horizon}_{_open_ticker}"):
                            st.session_state.pop("bq_open_stock_ticker", None)
                            st.session_state.pop("bq_open_stock_horizon", None)
                            st.session_state.pop("bq_open_stock_rank", None)
                            st.rerun()
                        render_detail(_match.iloc[0], profile, key_prefix=f"horizon_{horizon}_{_open_ticker}", horizon=horizon, rank=int(st.session_state.get("bq_open_stock_rank", 0) or 0))
                departed = dropped_from_top10(ranked, previous_horizon)
                if departed:
                    st.caption("Lämnat topp 10 sedan föregående sparade analys: " + ", ".join(departed) + ". Det är en omprövningssignal, inte automatiskt en säljsignal.")
                with st.expander("Vad betyder signalerna?", expanded=False):
                    for signal_name, signal_text in signal_legend(horizon):
                        st.markdown(f"**{signal_name}** — {signal_text}")
                    st.caption("Signalen sammanfattar redan godkända case. Den skapar inget nytt score och kan inte göra en underkänd aktie köpbar.")
                    st.markdown("**Förändring sedan sist:** NY KÖPSIGNAL = ny i topp 10 med köpbar signal · STÄRKT = tydligt bättre score/placering · OFÖRÄNDRAD = stabil · FÖRSVAGAD = tydligt sämre score/placering.")
                    st.caption("Från v3.44 fryser Borsify även värdering, kvalitet, marknadsläge, risk och datatäckning för topp 10. Därför kan STÄRKT/FÖRSVAGAD förklaras med vad som faktiskt ändrats, utan att dagens data skrivs bakåt på äldre analyser.")
                    st.caption("En aktie som lämnar topp 10 markeras för omprövning, inte automatiskt som SÄLJ. Ett riktigt säljbeslut kräver att caset eller riskbilden faktiskt har försämrats.")
                return ranked

            _focus = str(st.session_state.get("bq_horizon_focus") or "")
            if _focus:
                if st.button("Visa alla tre tidshorisonter", key="clear_horizon_focus"):
                    st.session_state.pop("bq_horizon_focus", None)
                    st.rerun()
            ranked_medium = pd.DataFrame()
            ranked_year = pd.DataFrame()
            ranked_lifetime = pd.DataFrame()
            if _focus == "upcoming":
                render_up_and_coming(filtered, profile)
            if not _focus or _focus == "medium":
                ranked_medium = _horizon_section(
                    "⚡ Köp nu – sälj i närtid",
                    "För lägen där Borsify ser ett aktie som ser intressant ut att köpa nu på ungefär några veckor till tre månader. Det är inte intradagshandel.",
                    "medium", "Mellan Score"
                )
            if not _focus or _focus == "year":
                if not _focus: st.divider()
                ranked_year = _horizon_section(
                    "📈 Köp nu – behåll upp till ett år",
                    "För bolag där värdering, kvalitet och utveckling kan ge ett stark möjlighet under ungefär 3–12 månader.",
                    "year", "Års Score"
                )
            if not _focus or _focus == "lifetime":
                if not _focus: st.divider()
                ranked_lifetime = _horizon_section(
                    "♾️ Köp för resten av livet",
                    "Den hårdaste kategorin. Borsify prioriterar uthållig kvalitet, robust ekonomi och rimlig värdering. Aktien måste fortsätta förtjäna sin plats.",
                    "lifetime", "Livstid Score"
                )

            # v3.47: freeze the broad discovery universe, not only today's winners.
            # Future "missed winner" analysis can therefore ask what Borsify failed to select
            # without reconstructing old rankings with today's model.
            try:
                snapshot_source = add_horizon_scores(filtered)
                recommended_sets = {
                    "medium": set(ranked_medium.get("Ticker", pd.Series(dtype=str)).astype(str)) if ranked_medium is not None and not ranked_medium.empty else set(),
                    "year": set(ranked_year.get("Ticker", pd.Series(dtype=str)).astype(str)) if ranked_year is not None and not ranked_year.empty else set(),
                    "lifetime": set(ranked_lifetime.get("Ticker", pd.Series(dtype=str)).astype(str)) if ranked_lifetime is not None and not ranked_lifetime.empty else set(),
                }
                discovery_flags = discovery_selection_flags(snapshot_source, max_candidates=min(24, len(snapshot_source)))
                missed_snapshot = build_universe_snapshot(
                    snapshot_source, profile, market, datetime.now().date().isoformat(), recommended_sets,
                    discovery_flags=discovery_flags, model_version=APP_VERSION
                )
                save_missed_winner_snapshot(missed_snapshot)
                refresh_missed_winner_outcomes(filtered, profile, market)
                resolve_runtime_issue(st.session_state, "missed_winner_history")
            except Exception as exc:
                record_runtime_issue(st.session_state, "missed_winner_history", exc, "missade vinnare kunde inte frysas eller utvärderas")

            with st.expander("Sök på ett särskilt sätt", expanded=False):
                st.caption(f"Ditt val just nu: {discovery_intent}. {intent_plain_text(discovery_intent)}")
                render_discovery_shortlist(filtered, discovery_intent, search_horizon)
                if discovery_intent in {"Bra långsiktig investering", "Billiga kvalitetsbolag", "Bästa möjligheter just nu"}:
                    render_quality_at_fair_price(filtered)
                if discovery_intent == "Utdelningsaktier" or dividend_only:
                    render_dividend_discovery(filtered)

            with st.expander("Fler analysverktyg", expanded=False):
                st.caption("Det här är för dig som vill granska motorn. Du behöver inte använda det för att följa Borsifys val.")
                render_engine_board(filtered)
                if "Fundamental förändring antal" in filtered.columns:
                    _radar = filtered[pd.to_numeric(filtered["Fundamental förändring antal"], errors="coerce").fillna(0) > 0].copy()
                    if not _radar.empty:
                        st.markdown("**Fundamental förändringsradar**")
                        _radar = _radar.sort_values(["Fundamental förändring antal", "Kvalitet"], ascending=[False, False]).head(10)
                        _cols = [c for c in ["Ticker", "Namn", "Fundamental förändring", "Fundamental förändring detalj", "Fundamental jämförelsedatum", "Borsify Score"] if c in _radar.columns]
                        st.dataframe(_radar[_cols], use_container_width=True, hide_index=True)
                        st.caption("Bygger på förändring mot äldre frysta bredscans. Saknad historik ger ingen fördel och radarn ändrar inte Borsify Score.")
                if not daily_shortlist.empty:
                    quick_cols = [c for c in ["Ticker", "Namn", "Borsify Score", "Dagens relevans", "Prioritet", "Värdering", "Kvalitet", "Risk"] if c in daily_shortlist.columns]
                    st.dataframe(daily_shortlist[quick_cols].copy(), use_container_width=True, hide_index=True)

        with discover_ideas:
            render_idea_flow(scored)

        with discover_radar:
            st.subheader("Borsify Radar · dagens förändringar")
            today_str = datetime.now().date().isoformat()
            today_hist = signal_history_global.copy()
            if not today_hist.empty:
                today_hist = today_hist[today_hist["occurred_date"].astype(str) == today_str]
            if today_hist.empty:
                st.info("Inga sparade Radar-händelser för idag ännu. De skapas vid analys eller av den schemalagda scanningen.")
            else:
                r1, r2, r3 = st.columns(3)
                r1.metric("Händelser idag", len(today_hist))
                r2.metric("Hög prioritet", int((pd.to_numeric(today_hist["priority"], errors="coerce") >= 3).sum()))
                r3.metric("Berörda aktier", int(today_hist["symbol"].astype(str).nunique()))
                for _, sig in today_hist.sort_values(["priority", "created_at"], ascending=[False, False]).head(8).iterrows():
                    icon = "🔔" if int(sig["priority"]) >= 3 else "⚠️"
                    st.markdown(f"**{icon} {sig['kind']} · {sig['symbol']}** — {sig['text']}")

            st.divider()
            st.subheader("Signalhistorik")
            st.caption("Signaler sparas i historiken och kan markeras som lästa. Trösklar för Score och dagsfall kan ställas per bevakad aktie.")
            if not watched_global:
                st.info("Lägg till aktier i bevakningslistan för att få signaler.")
            else:
                if unread_signals:
                    if st.button(f"Markera alla {unread_signals} som lästa", use_container_width=False):
                        mark_all_signals_read(); st.rerun()
                history_mode = st.radio("Visa", ["Olästa", "Alla"], horizontal=True, label_visibility="collapsed")
                hist = signal_history_global.copy()
                if history_mode == "Olästa" and not hist.empty:
                    hist = hist[~hist["is_read"].astype(bool)]
                if hist.empty:
                    st.info("Inga signaler i den valda vyn.")
                else:
                    for _, sig in hist.head(100).iterrows():
                        icon = "🔔" if int(sig["priority"]) >= 3 else "⚠️"
                        read_label = "Läst" if bool(sig["is_read"]) else "Oläst"
                        email_label = " · E-post skickad" if pd.notna(sig.get("email_sent_at")) and str(sig.get("email_sent_at") or "").strip() else ""
                        with st.container(border=True):
                            st.markdown(f"**{icon} {sig['kind']} · {sig['symbol']}** · {sig['occurred_date']} · {read_label}{email_label}")
                            st.write(str(sig["text"]))
                            if not bool(sig["is_read"]) and st.button("Markera läst", key=f"read_{sig['event_key']}"):
                                mark_signal_read(str(sig["event_key"]), True); st.rerun()
                st.caption("Regler: ny i topp 10, egen Score-förändringsgräns, egen Score-nivå, målkurs och egen dagsfallsgräns.")

            st.divider()
            st.subheader("E-postnotiser")
            if not (cloud_enabled() and current_user_id()):
                st.info("E-postnotiser kräver inloggat Supabase-konto. Lokalt gästläge sparar bara signalerna i appen.")
            else:
                prefs = get_notification_preferences()
                with st.form("notification_preferences_form"):
                    enabled = st.checkbox("Skicka e-post efter den automatiska vardagsscanningen", value=bool(prefs.get("email_enabled", False)))
                    email = st.text_input("Mottagare", value=str(prefs.get("email") or current_user_email()))
                    min_priority = st.select_slider(
                        "Minsta prioritet", options=[1, 2, 3], value=int(prefs.get("min_priority", 2)),
                        format_func=lambda x: {1: "Alla", 2: "Viktiga", 3: "Hög"}[x],
                    )
                    selected_kinds = st.multiselect("Signaltyper", SIGNAL_KINDS, default=[x for x in prefs.get("notify_kinds", SIGNAL_KINDS) if x in SIGNAL_KINDS])
                    save_notif = st.form_submit_button("Spara e-postinställningar")
                if save_notif:
                    if enabled and ("@" not in email or "." not in email.split("@")[-1]):
                        st.error("Ange en giltig e-postadress.")
                    elif enabled and not selected_kinds:
                        st.error("Välj minst en signaltyp eller stäng av e-postnotiser.")
                    else:
                        update_notification_preferences(enabled, email, min_priority, selected_kinds)
                        st.success("E-postinställningarna är sparade.")
                st.caption("Leverans sker från den schemalagda serverkörningen. Resend/API-nyckeln ligger bara i GitHub Secrets/servermiljö, aldrig i klientappen.")

    elif page.startswith("Bevakning"):
        st.subheader("Min bevakning")
        watch_meta = watch_meta_global
        watched = watched_global
        if st.session_state.get("bq_case_breaker_migration_needed"):
            st.info("Regler för när du ska tänka om fungerar i appen, men databasen behöver uppdateras innan de kan sparas permanent i molnet. Övrig bevakning fungerar som tidigare.")
        if not watched:
            st.info("Bevakningslistan är tom. Lägg till en aktie från detaljanalysen.")
        else:
            st.markdown("#### Case Alert · intern utveckling + nya bolagshändelser")
            st.caption("Bevakningen kopplar ihop dina egna anteckningar, dina regler för när du ska tänka om och nyhetsrubriker. Nyheter ändrar aldrig Borsifys betyg automatiskt. Rubriker används bara som tips om vad du kan behöva läsa vidare om.")
            refresh_watch_media = st.button("Kontrollera senaste media för bevakade case", key="watch_case_alert_refresh", use_container_width=False)
            if refresh_watch_media:
                watch_feed, watch_feed_errors = fetch_idea_flow_cached()
                st.session_state["idea_flow_feed"] = watch_feed
                st.session_state["idea_flow_errors"] = watch_feed_errors
            watch_media_feed = st.session_state.get("idea_flow_feed")
            watch_ideas = pd.DataFrame()
            if isinstance(watch_media_feed, pd.DataFrame) and not watch_media_feed.empty and not watch_df_global.empty:
                watch_mentions = map_mentions(watch_media_feed, watch_df_global)
                watch_ideas = build_verified_ideas(watch_mentions, watch_df_global) if not watch_mentions.empty else pd.DataFrame()
                if not watch_ideas.empty:
                    important = int((pd.to_numeric(watch_ideas.get("Case Impact Nivå", 0), errors="coerce").fillna(0) >= 2).sum())
                    st.caption(f"Mediabevakning matchade {len(watch_ideas)} bevakade aktier · {important} med potentiellt casepåverkande händelse. Händelsernas riktning verifieras inte från rubriken ensam.")
                else:
                    st.caption("Mediabevakningen är hämtad, men inga aktuella rubriker matchade dina bevakade aktier.")
            else:
                st.caption("Ingen mediabevakning är hämtad i den här sessionen ännu. Knappen ovan hämtar den när du vill göra en Case Alert-kontroll.")

            watch_df = watch_df_global.copy()
            if not watch_df.empty:
                order = {sym: i for i, sym in enumerate(watched)}
                watch_df["_watch_order"] = watch_df["Ticker"].map(order).fillna(9999)
                watch_df = watch_df.sort_values("_watch_order").drop(columns=["_watch_order"])
                watch_display = dataframe_for_display(watch_df)
                watch_display.insert(4, "Betyg ändring", [score_change(str(r["Ticker"]), profile, float(r["Borsify Score"])) for _, r in watch_df.iterrows()])
                st.dataframe(watch_display, use_container_width=True, hide_index=True, column_config={"Betyg ändring": st.column_config.NumberColumn("Betyg ändring", format="%+.1f")})
                st.download_button("Exportera bevakningslista", data="Ticker\n" + "\n".join(watched), file_name="borsify_bevakning.csv", mime="text/csv")

            st.markdown("#### Varför bevakar jag den? · intressepris och signaler")
            st.caption("Skriv med egna ord varför du följer aktien. Borsify visar samtidigt sitt eget skäl så att du senare kan se om caset har förändrats.")
            for _, meta in watch_meta.iterrows():
                sym = str(meta["symbol"])
                current_note = str(meta.get("note") or "")
                current_target = _num(meta.get("target_price"))
                with st.expander(sym, expanded=False):
                    current_row = watch_df_global[watch_df_global["Ticker"].astype(str) == sym].head(1) if not watch_df_global.empty else pd.DataFrame()
                    journal = None
                    breaker = None
                    if not current_row.empty:
                        wr = current_row.iloc[0]
                        st.markdown(f"**Borsifys skäl just nu:** {wr.get('Varför','—')}")
                        cp = _num(wr.get("Pris"))
                        if np.isfinite(cp): st.caption(f"Aktuell hämtad kurs: {fmt_price_with_sek(wr)} · kursdag {wr.get('Prisdatum','—')}")
                    if not current_row.empty:
                        hist = get_score_history(sym, profile)
                        wr = current_row.iloc[0]
                        current_case = {
                            "score": _num(wr.get("Borsify Score")),
                            "valuation": _num(wr.get("Värdering")),
                            "quality": _num(wr.get("Kvalitet")),
                            "setup": _num(wr.get("Marknadsläge")),
                            "income": _num(wr.get("Utdelning")),
                            "risk": _num(wr.get("Risk")),
                            "coverage": _num(wr.get("Datatäckning")),
                        }
                        journal = assess_case_change(hist, current_case, meta.get("added_at"))
                        st.markdown("**Case Journal · vad har förändrats?**")
                        delta = journal.get("score_delta")
                        delta_text = f"{float(delta):+.1f} poäng sedan start" if np.isfinite(_num(delta)) else "historiken byggs upp"
                        st.write(f"**{journal.get('status', 'Historiken byggs upp')}** · {delta_text}")
                        days = journal.get("days_followed")
                        if days is not None:
                            st.caption(f"Följd i cirka {int(days)} dagar. Det här visar vad som har förändrats i Borsifys analys – det är inte automatiskt ett köp- eller säljbeslut.")
                        for change in journal.get("changes", []):
                            st.write(f"• {change}")
                        jt = journal_table(hist)
                        if len(jt) >= 2:
                            with st.expander("Visa sparad utveckling", expanded=False):
                                st.dataframe(jt, use_container_width=True, hide_index=True)
                        else:
                            st.caption("Efter fler dagliga analyser visas en tidslinje här så att du kan se om caset faktiskt utvecklas åt rätt håll.")
                    else:
                        st.caption("Case Journal börjar byggas när aktien har analyserats och sparats i bevakningen.")

                    st.markdown("**Vad skulle få dig att tänka om kring aktien?**")
                    st.caption("Sätt bara gränser som faktiskt skulle få dig att ompröva caset. 0 betyder att regeln är avstängd. Det här är en kontrollista, inte en automatisk säljorder.")
                    b1, b2 = st.columns(2)
                    breaker_min_score = b1.number_input("Minsta Borsify Score", 0.0, 100.0, float(_num(meta.get("breaker_min_score"))) if np.isfinite(_num(meta.get("breaker_min_score"))) else 0.0, 1.0, key=f"breaker_score_{sym}")
                    breaker_min_quality = b2.number_input("Minsta kvalitet", 0.0, 100.0, float(_num(meta.get("breaker_min_quality"))) if np.isfinite(_num(meta.get("breaker_min_quality"))) else 0.0, 1.0, key=f"breaker_quality_{sym}")
                    b3, b4 = st.columns(2)
                    breaker_min_risk = b3.number_input("Minsta riskpoäng", 0.0, 100.0, float(_num(meta.get("breaker_min_risk"))) if np.isfinite(_num(meta.get("breaker_min_risk"))) else 0.0, 1.0, key=f"breaker_risk_{sym}", help="I Borsify betyder högre riskpoäng bättre/tryggare riskbild.")
                    breaker_max_score_drop = b4.number_input("Max scorefall från start", 0.0, 100.0, float(_num(meta.get("breaker_max_score_drop"))) if np.isfinite(_num(meta.get("breaker_max_score_drop"))) else 0.0, 1.0, key=f"breaker_drop_{sym}")
                    if not current_row.empty:
                        breaker_rules = {"min_score": breaker_min_score, "min_quality": breaker_min_quality, "min_risk": breaker_min_risk, "max_score_drop": breaker_max_score_drop}
                        breaker = evaluate_case_breakers(current_case, hist, breaker_rules)
                        status = str(breaker.get("status", ""))
                        if breaker.get("tone") == "negative":
                            st.error(f"**{status}** · {breaker.get('explanation','')}")
                        elif breaker.get("tone") == "warning":
                            st.warning(f"**{status}** · {breaker.get('explanation','')}")
                        elif breaker.get("tone") == "positive":
                            st.success(f"**{status}** · {breaker.get('explanation','')}")
                        else:
                            st.info(f"**{status}** · {breaker.get('explanation','')}")
                        for item in breaker.get("triggered", []): st.write(f"🚨 {item}")
                        for item in breaker.get("near", []): st.write(f"⚠️ {item}")

                    if journal is not None and breaker is not None:
                        idea_row = None
                        if not watch_ideas.empty and "Ticker" in watch_ideas.columns:
                            idea_match = watch_ideas[watch_ideas["Ticker"].astype(str) == sym].head(1)
                            if not idea_match.empty:
                                idea_row = idea_match.iloc[0]
                        case_alert = evaluate_case_alert(journal, breaker, idea_row)
                        st.markdown("**Case Alert · behöver något prioriteras?**")
                        alert_text = f"**{case_alert.get('status','')}** · {case_alert.get('summary','')}"
                        if case_alert.get("tone") == "critical":
                            st.error(alert_text)
                        elif case_alert.get("tone") == "warning":
                            st.warning(alert_text)
                        elif case_alert.get("tone") == "positive":
                            st.success(alert_text)
                        else:
                            st.info(alert_text)
                        for reason in case_alert.get("reasons", []):
                            st.write(f"• {reason}")
                        if idea_row is not None:
                            event_name = str(idea_row.get("Huvudhändelse", "Övrigt / oklart"))
                            pulse_name = str(idea_row.get("Mediepuls", "Ingen tydlig ny puls"))
                            st.caption(f"Senaste externa kontext: {event_name} · {pulse_name}. Case Alert tolkar inte en vanlig rapport som positiv eller negativ utan verifierade fakta.")
                            headlines = idea_row.get("Rubriker") or []
                            if isinstance(headlines, list) and headlines:
                                latest_headline = headlines[0]
                                title = str(latest_headline.get("title", ""))
                                source = str(latest_headline.get("source", ""))
                                link = str(latest_headline.get("link", ""))
                                if title:
                                    st.write(f"Senaste rubrik: **{title}** · {source}")
                                if link:
                                    st.link_button("Öppna originalkällan", link)

                    note = st.text_area("Min anledning att bevaka", value=current_note, key=f"note_{sym}", placeholder="Exempel: Bra bolag men jag vill vänta på lägre pris.")
                    target = st.number_input(
                        "Mitt intressepris (0 = inget)", min_value=0.0, value=float(current_target) if np.isfinite(current_target) and current_target > 0 else 0.0, step=1.0, key=f"target_{sym}"
                    )
                    current_threshold = _num(meta.get("signal_score_threshold")); current_move = _num(meta.get("signal_score_move")); current_drop = _num(meta.get("signal_daily_drop"))
                    st.markdown("**Signalgränser**")
                    t1, t2, t3 = st.columns(3)
                    score_threshold = t1.number_input("Score-nivå", 0.0, 100.0, float(current_threshold) if np.isfinite(current_threshold) else 75.0, 1.0, key=f"threshold_{sym}")
                    score_move = t2.number_input("Score-förändring", 1.0, 50.0, float(current_move) if np.isfinite(current_move) else 8.0, 1.0, key=f"move_{sym}")
                    daily_drop = t3.number_input("Dagsfall %", 1.0, 50.0, float(current_drop) if np.isfinite(current_drop) else 5.0, 0.5, key=f"drop_{sym}")
                    csave, crem = st.columns(2)
                    if csave.button("Spara", key=f"save_watch_{sym}", use_container_width=True):
                        update_watchlist_item(sym, note, target if target > 0 else None, score_threshold, score_move, daily_drop, breaker_min_score, breaker_min_quality, breaker_min_risk, breaker_max_score_drop)
                        st.success("Sparat")
                    if crem.button("Ta bort", key=f"remove_watch_{sym}", use_container_width=True):
                        toggle_watchlist(sym)
                        st.rerun()
            if st.button("Töm bevakningslistan"):
                clear_watchlist()
                st.rerun()
        st.caption("Inloggad användare: bevakning, scorehistorik, radarhistorik och signalhistorik lagras i Supabase. Gäst/lokalt läge: SQLite används på aktuell dator.")
    else:  # Mer
        more_market, more_method, more_lab = st.tabs(["Alla aktier", "Så fungerar Borsify", "Analyslabbet"])
        with more_market:
            st.subheader("Alla analyserade aktier")
            st.caption("Rålistan är till för den som vill gräva själv. Börja annars på Idag.")
            st.dataframe(dataframe_for_display(scored), use_container_width=True, hide_index=True)
        with more_method:
            w = PROFILE_WEIGHTS[profile]
            st.subheader("Så räknas Borsify Score")
            with st.expander("Risk på vanlig svenska · det viktigaste före ett köp", expanded=False):
                st.markdown(f"""
- **Volatilitet:** {beginner_term('volatilitet')}.
- **Likviditet:** {beginner_term('likviditet')}.
- **Stop-loss:** {beginner_term('stop-loss')}.
- **Diversifiering:** {beginner_term('diversifiering')}.
- **Hävstång:** {beginner_term('hävstång')}. Borsify fokuserar i första hand på vanliga aktier och uppmuntrar inte användaren att ta hävstång för att förstora en signal.

Borsify försöker därför visa både **varför något ser intressant ut** och **vad som kan gå fel**. Ett högt score är ett analysurval, inte en garanti.
""")
            st.markdown(f"""
**Vald strategi: {profile}.** Vikter: värdering {w['valuation']:.0%}, kvalitet {w['quality']:.0%}, marknadsläge {w['setup']:.0%}, utdelning {w['income']:.0%}, risk {w['risk']:.0%}.

**Värdering** använder inte längre samma måttmix för alla bolag. Bank/finans får större vikt på P/B och vinstmått, tillgångslätta teknik-/kommunikationsbolag får större vikt på forward P/E och kassaflöde, medan energi/material får större vikt på EV/EBITDA och kassaflöde. Fastigheter får en försiktigare bedömning eftersom P/FFO och substansvärde saknas i grunddatan. Jämförelsen görs fortfarande främst mot samma sektor när underlaget räcker.

**Kvalitet** försöker svara på: ”Är det här ett välskött och lönsamt bolag?” Den väger bland annat ROE (hur effektivt bolaget använder ägarnas pengar), marginaler, tillväxt och skuld. **Marknadsläge** försöker svara på: ”Är kursläget intressant just nu?” och använder bland annat RSI och 200-dagarssnittet. **Utdelning** tittar både på direktavkastningen och hur stor del av vinsten som går till utdelning. **Risk** drar ned bolag med exempelvis förluster, hög skuld eller en tydligt fallande kursutveckling.

Aktier med låg datatäckning får en försiktig rabatt. En hög score är en prioriteringssignal för vidare analys, inte en prognos om framtida avkastning.

**Bevakningssignaler** jämför aktuell körning med tidigare dagssnapshots, din målkurs och dina egna tröskelvärden per aktie. Signalhistorik sparas med läst/oläst-status. Inloggade användare kan välja vilka signaltyper som ska skickas som e-post efter den schemalagda scanningen. De är regelbaserade informationshändelser, inte automatiska affärsförslag.
""")
            st.caption("Konton/molnsynk: Supabase när konfigurerat. Datakälla: Yahoo Finance via yfinance. Sverige bred läses från universe.csv. Utländska marknader använder kuraterade startuniversum. Listorna är inte garanterat kompletta officiella indexlistor. Kontrollera alltid rapporter, nyheter, kassaflöde, skuldsättning och bolagsspecifika händelser före investeringsbeslut.")

        with more_lab:
            st.subheader("Analyslabbet")
            st.caption("Här granskas Borsifys egna modeller och historik. Du behöver inte använda detta för att hitta aktier.")
            st.info("Resultaten här är modellkontroller – inte köpsignaler. Borsify ändrar inte vikter automatiskt utifrån små historiska sample.")
            default_edge_symbol = str(filtered.iloc[0]["Ticker"]) if not filtered.empty else "INVE-B.ST"
            render_edge_lab(default_edge_symbol, list(symbols), benchmark_symbol, benchmark_name)

            st.divider()
            st.markdown("### Missade vinnare")
            st.caption("Borsify fryser nu hela det analyserade universumet och kontrollerar senare vilka tydliga vinnare som aldrig nådde rekommendationslistorna. Det här är en prospektiv kvalitetskontroll, inte ett nytt score.")
            missed_outcomes = get_missed_winner_outcomes(limit=10000)
            c1, c2 = st.columns(2)
            for col, horizon in [(c1, "1m"), (c2, "3m")]:
                summary = missed_winner_summary(missed_outcomes, horizon)
                col.metric(MISSED_WINNER_HORIZONS[horizon]["label"], f"{summary['misses']} missar" if summary["evaluated"] else "Bygger historik")
                col.caption(summary["text"])
            if missed_outcomes is not None and not missed_outcomes.empty:
                misses = missed_outcomes[pd.to_numeric(missed_outcomes["missed_winner"], errors="coerce").fillna(0).eq(1)].copy()
                if not misses.empty:
                    misses["Utfall"] = (pd.to_numeric(misses["return_pct"], errors="coerce") * 100).round(1).map(lambda x: f"{x:+.1f}%")
                    misses["Fryst score"] = pd.to_numeric(misses["frozen_score"], errors="coerce").round(0)
                    misses["Period"] = misses["horizon"].map({"1m":"1 månad","3m":"3 månader"}).fillna(misses["horizon"])
                    show = misses.sort_values("return_pct", ascending=False).head(20).rename(columns={"name":"Bolag","symbol":"Ticker","why_missed":"Varför missades den?","captured_date":"Fryst datum"})
                    st.dataframe(show[["Fryst datum","Ticker","Bolag","Period","Utfall","Fryst score","Varför missades den?"]], use_container_width=True, hide_index=True)
                else:
                    st.info("Mogna kohorter finns, men inga tydliga missade vinnare har identifierats ännu.")
            else:
                st.info("Historiken börjar byggas från v3.47. Äldre dagar fylls inte i bakåt, eftersom det skulle använda information som inte var fryst då.")
            if st.session_state.get("bq_missed_winner_migration_needed"):
                st.warning("Missed Winners-historiken kräver v3.47-raderna i supabase_schema.sql för molnlagring. Analysen fylls inte bakåt innan tabellerna finns.")

            st.markdown("#### Missmönster")
            st.caption("Borsify jämför nu de missade vinnarnas frysta egenskaper med hela den utvärderade kohorten. Ett mönster måste återkomma och vara överrepresenterat; det ändrar aldrig modellen automatiskt.")
            missed_snapshots = get_missed_winner_snapshots(limit=20000)
            pattern_table = build_miss_pattern_table(missed_outcomes, missed_snapshots)
            pattern_summary = miss_pattern_summary(pattern_table)
            st.info(pattern_summary["text"])
            if pattern_table is not None and not pattern_table.empty:
                pattern_show = pattern_table.copy()
                pattern_show["Andel av missar"] = (pattern_show["miss_share"] * 100).round(0).map(lambda x: f"{x:.0f}%")
                pattern_show["Andel av hela kohorten"] = (pattern_show["cohort_share"] * 100).round(0).map(lambda x: f"{x:.0f}%")
                pattern_show["Överrepresentation"] = pattern_show["overrepresentation"].round(2).map(lambda x: f"{x:.2f}×" if pd.notna(x) else "–")
                pattern_show["Typiskt resultat"] = (pattern_show["median_return"] * 100).round(1).map(lambda x: f"{x:+.1f}%" if pd.notna(x) else "–")
                pattern_show = pattern_show.rename(columns={"pattern":"Mönster","misses":"Missar","status":"Bedömning"})
                st.dataframe(pattern_show[["Mönster","Missar","Andel av missar","Andel av hela kohorten","Överrepresentation","Typiskt resultat","Bedömning"]], use_container_width=True, hide_index=True)

            st.markdown("#### Discovery Learning Loop")
            st.caption("När samma typ av vinnare missas tillräckligt ofta föreslår Borsify en liten, förregistrerad challenger i själva discovery-steget. Förslaget ändrar aldrig produktionen direkt och får bara bedömas på nya framtida case.")
            learning_proposals = build_discovery_learning_proposals(pattern_table)
            learning_summary = discovery_learning_summary(learning_proposals)
            st.info(learning_summary["text"])
            if learning_proposals is not None and not learning_proposals.empty:
                proposal_show = learning_proposals.copy()
                proposal_show["Överrepresentation"] = proposal_show["overrepresentation"].round(2).map(lambda x: f"{x:.2f}×" if pd.notna(x) else "–")
                proposal_show["Typiskt resultat"] = (proposal_show["median_return"] * 100).round(1).map(lambda x: f"{x:+.1f}%" if pd.notna(x) else "–")
                proposal_show = proposal_show.rename(columns={"pattern":"Missmönster","challenger":"Challenger","proposal":"Föreslagen teständring","misses":"Missar","status":"Status","next_step":"Nästa steg"})
                st.dataframe(proposal_show[["Missmönster","Challenger","Föreslagen teständring","Missar","Överrepresentation","Typiskt resultat","Status","Nästa steg"]], use_container_width=True, hide_index=True)

            st.markdown("#### Discovery Champion vs Challenger")
            st.caption("Från v3.50 är alternativa discovery-regler låsta innan framtida utfall uppstår. Champion och challengers får samma frysta universum och samma poolstorlek. Äldre observationer räknas inte.")
            discovery_registry = discovery_registry_table()
            with st.expander("Visa förregistrerade discovery-regler", expanded=False):
                st.dataframe(discovery_registry[["Challenger","Missmönster","Låst regel","Förregistrerad version","Definition"]], use_container_width=True, hide_index=True)
            discovery_cc = prospective_discovery_results(missed_snapshots, missed_outcomes)
            discovery_cc_summary = discovery_challenger_summary(discovery_cc)
            st.info(discovery_cc_summary["text"])
            if discovery_cc is not None and not discovery_cc.empty:
                cc_show = discovery_cc.copy()
                for c in ["Champion träffgrad","Challenger träffgrad","Skillnad träffgrad","Champion median","Challenger median"]:
                    cc_show[c] = pd.to_numeric(cc_show[c], errors="coerce").map(lambda x: "–" if pd.isna(x) else f"{x*100:+.1f}%" if "Skillnad" in c or "median" in c.lower() else f"{x*100:.1f}%")
                st.dataframe(cc_show[["Challenger","Horisont","Oberoende kohorter","Vinnare","Champion fångade","Challenger fångade","Champion träffgrad","Challenger träffgrad","Skillnad träffgrad","Champion median","Challenger median","Status"]], use_container_width=True, hide_index=True)
            st.caption("Minst tre oberoende kohorter och sex vinnare krävs innan jämförelsen får en riktning. En vinnande challenger promoveras aldrig automatiskt.")


if __name__ == "__main__":
    main()
