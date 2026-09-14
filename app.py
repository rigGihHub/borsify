from __future__ import annotations

import math
import re
import json
import hmac
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
    outcome_summary, calibration_by_gate, calibration_by_deal_conviction,
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
from universe_quality import apply_universe_quality, filter_rankable_universe, quality_summary
from qc_history import evolve_qc_state, is_quarantined, scan_health, quarantine_summary, should_record_qc_outcome
from case_ai import build_case_ai_input, build_case_ai_instructions, local_case_explanation
from ai_cost import token_usage, estimate_usage_cost, format_cost_usd

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

APP_VERSION = "4.34.0"

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
    if np.isfinite(cov) and cov < .50: flags.append("begränsad fundamentaldata")
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


def scan_universe(symbols: list[str]) -> tuple[pd.DataFrame, list[str]]:
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
        "price_seconds": 0.0,
        "fundamental_seconds": 0.0,
    }

    price_started = time.perf_counter()
    price_map = fetch_bulk_price_history(tuple(symbols))
    usable_histories: dict[str, pd.DataFrame] = {}

    for sym in symbols:
        hist = price_map.get(sym)
        if hist is None or hist.empty:
            metrics["single_price_fallbacks"] += 1
            hist = fetch_single_price_history(sym)

        if hist is None or hist.empty:
            errors.append(f"{sym}: ingen kurshistorik efter bulk + fallback")
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
    with ThreadPoolExecutor(max_workers=min(6, max(1, len(usable_histories)))) as executor:
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
                errors.append(f"{sym}: fundamentaldata {type(exc).__name__}")
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
                    report_delta = build_report_delta(metrics, post_report, raw.get("catalyst_events"))
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
            "Report Delta förklaring",
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
                assessment.update(build_report_delta(inflection_metrics, post_report, raw.get("catalyst_events")))
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
                assessment.update(sector_kpis)
                _kpi_context = {**row.to_dict(), **assessment}
                _kpi_context.update(assess_business_management_intelligence(_kpi_context))
                assessment.update(assess_kpi_inflection(_kpi_context))
                inflection = assess_inflection(inflection_metrics)
                post_report = build_post_report_drift(
                    raw.get("earnings_history"), raw.get("price_history"), inflection_metrics
                )
                inflection.update(post_report)
                inflection.update(build_report_delta(inflection_metrics, post_report, raw.get("catalyst_events")))
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


def _site_access_password() -> str:
    """Optional shared site password stored only in Streamlit Secrets."""
    try:
        return str(st.secrets.get("APP_ACCESS_PASSWORD", "")).strip()
    except Exception:
        return ""


def require_site_access() -> None:
    """Gate a public Streamlit deployment behind an app-level password when configured.

    Local development remains open if APP_ACCESS_PASSWORD is not configured.
    The password itself never belongs in source control.
    """
    expected = _site_access_password()
    if not expected:
        return
    if st.session_state.get("bq_site_access") is True:
        return

    st.subheader("Borsify är låst")
    st.caption("Ange åtkomstlösenordet för att öppna appen.")
    with st.form("site_access_form", clear_on_submit=True):
        supplied = st.text_input("Åtkomstlösenord", type="password")
        submitted = st.form_submit_button("Öppna Borsify", type="primary", use_container_width=True)
    if submitted:
        if hmac.compare_digest(supplied, expected):
            st.session_state["bq_site_access"] = True
            st.rerun()
        else:
            st.error("Fel lösenord.")
    st.stop()


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
                symbol TEXT NOT NULL,
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 1,
                profile TEXT NOT NULL,
                occurred_date TEXT NOT NULL,
                is_read INTEGER NOT NULL DEFAULT 0,
                email_sent_at TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _ensure_sqlite_column(conn, "signal_history", "email_sent_at", "TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_preferences (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                email_enabled INTEGER NOT NULL DEFAULT 0,
                email TEXT NOT NULL DEFAULT '',
                min_priority INTEGER NOT NULL DEFAULT 2,
                notify_kinds TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO notification_preferences(singleton,notify_kinds) VALUES (1,?)",
            ("|".join(SIGNAL_KINDS),),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS visit_state (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                last_seen_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reviewed_changes (
                change_key TEXT PRIMARY KEY,
                reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendation_ledger (
                record_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                horizon_type TEXT NOT NULL,
                model_version TEXT NOT NULL,
                profile TEXT NOT NULL,
                market TEXT NOT NULL,
                rank INTEGER NOT NULL,
                entry_price REAL NOT NULL,
                gate TEXT NOT NULL DEFAULT '',
                score REAL,
                confidence REAL,
                evidence_count INTEGER,
                why_now TEXT NOT NULL DEFAULT '',
                primary_catalyst TEXT NOT NULL DEFAULT '',
                captured_date TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                snapshot_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS recommendation_outcomes (
                record_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                horizon TEXT NOT NULL,
                trading_days INTEGER NOT NULL,
                evaluated_date TEXT NOT NULL,
                evaluated_price REAL NOT NULL,
                return_pct REAL NOT NULL,
                positive INTEGER NOT NULL DEFAULT 0,
                gain_10 INTEGER NOT NULL DEFAULT 0,
                loss_10 INTEGER NOT NULL DEFAULT 0,
                evaluated_at TEXT NOT NULL,
                PRIMARY KEY (record_id, horizon)
            )
            """
        )
        _ensure_sqlite_column(conn, "recommendation_outcomes", "benchmark_symbol", "TEXT NOT NULL DEFAULT ''")
        _ensure_sqlite_column(conn, "recommendation_outcomes", "benchmark_name", "TEXT NOT NULL DEFAULT ''")
        _ensure_sqlite_column(conn, "recommendation_outcomes", "benchmark_return_pct", "REAL")
        _ensure_sqlite_column(conn, "recommendation_outcomes", "excess_return_pct", "REAL")
        _ensure_sqlite_column(conn, "recommendation_outcomes", "beat_benchmark", "INTEGER")
        _ensure_sqlite_column(conn, "recommendation_outcomes", "best_return_pct", "REAL")
        _ensure_sqlite_column(conn, "recommendation_outcomes", "worst_return_pct", "REAL")
        _ensure_sqlite_column(conn, "recommendation_outcomes", "sessions_to_best", "INTEGER")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_usage (
                request_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL,
                input_tokens INTEGER NOT NULL DEFAULT 0,
                output_tokens INTEGER NOT NULL DEFAULT 0,
                cost_usd REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS holdings (
                holding_id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                purchase_price REAL NOT NULL,
                quantity REAL NOT NULL DEFAULT 1,
                purchase_date TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS missed_winner_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                profile TEXT NOT NULL,
                market TEXT NOT NULL,
                captured_date TEXT NOT NULL,
                entry_price REAL NOT NULL,
                borsify_score REAL,
                medium_score REAL,
                year_score REAL,
                lifetime_score REAL,
                valuation REAL,
                quality REAL,
                setup REAL,
                risk REAL,
                coverage REAL,
                recommended_medium INTEGER NOT NULL DEFAULT 0,
                recommended_year INTEGER NOT NULL DEFAULT 0,
                recommended_lifetime INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        _ensure_sqlite_column(conn, "missed_winner_snapshots", "discovery_champion_selected", "INTEGER")
        _ensure_sqlite_column(conn, "missed_winner_snapshots", "discovery_challenger_flags", "TEXT")
        _ensure_sqlite_column(conn, "missed_winner_snapshots", "discovery_registry_version", "TEXT")
        _ensure_sqlite_column(conn, "missed_winner_snapshots", "model_version", "TEXT")
        _ensure_sqlite_column(conn, "missed_winner_snapshots", "revenue_growth", "REAL")
        _ensure_sqlite_column(conn, "missed_winner_snapshots", "earnings_growth", "REAL")
        _ensure_sqlite_column(conn, "missed_winner_snapshots", "profit_margin", "REAL")
        _ensure_sqlite_column(conn, "missed_winner_snapshots", "roe", "REAL")
        _ensure_sqlite_column(conn, "missed_winner_snapshots", "fcf_yield", "REAL")
        _ensure_sqlite_column(conn, "missed_winner_snapshots", "forward_pe", "REAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS missed_winner_outcomes (
                snapshot_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                captured_date TEXT NOT NULL,
                evaluated_date TEXT NOT NULL,
                horizon TEXT NOT NULL,
                entry_price REAL NOT NULL,
                evaluated_price REAL NOT NULL,
                return_pct REAL NOT NULL,
                return_percentile REAL NOT NULL,
                was_recommended INTEGER NOT NULL DEFAULT 0,
                missed_winner INTEGER NOT NULL DEFAULT 0,
                frozen_score REAL,
                why_missed TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(snapshot_id,horizon)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS universe_qc_state (
                symbol TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'OKÄND',
                failure_streak INTEGER NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                failure_count INTEGER NOT NULL DEFAULT 0,
                last_checked_at TEXT,
                last_verified_at TEXT,
                last_reason TEXT NOT NULL DEFAULT '',
                quarantine_until TEXT
            )
            """
        )
        ensure_consensus_memory_table(conn)
        ensure_report_delta_memory_table(conn)
        ensure_management_signal_memory_table(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS universe_qc_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL,
                outcome TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                counted_failure INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )




def save_missed_winner_snapshot(frame: pd.DataFrame) -> None:
    if frame is None or frame.empty:
        return
    client = _supabase_client(); uid = current_user_id()
    rows = []
    for _, r in frame.iterrows():
        payload = r.to_dict()
        payload["snapshot_id"] = f"{payload.get('captured_date')}::{payload.get('profile')}::{payload.get('market')}::{payload.get('symbol')}"
        rows.append(payload)
    if client is not None and uid:
        try:
            for row in rows:
                client.table("missed_winner_snapshots").upsert({"user_id": uid, **row}, on_conflict="user_id,snapshot_id").execute()
            return
        except Exception:
            st.session_state["bq_missed_winner_migration_needed"] = True
            return
    init_db()
    cols = ["snapshot_id","symbol","name","profile","market","captured_date","entry_price","borsify_score","medium_score","year_score","lifetime_score","valuation","quality","setup","risk","coverage","revenue_growth","earnings_growth","profit_margin","roe","fcf_yield","forward_pe","recommended_medium","recommended_year","recommended_lifetime","discovery_champion_selected","discovery_challenger_flags","discovery_registry_version","model_version"]
    with _db_connect() as conn:
        sql = f"INSERT OR IGNORE INTO missed_winner_snapshots({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})"
        for row in rows:
            conn.execute(sql, tuple(row.get(c) for c in cols))


def get_missed_winner_snapshots(limit: int = 10000) -> pd.DataFrame:
    cols = ["snapshot_id","symbol","name","profile","market","captured_date","entry_price","borsify_score","medium_score","year_score","lifetime_score","valuation","quality","setup","risk","coverage","revenue_growth","earnings_growth","profit_margin","roe","fcf_yield","forward_pe","recommended_medium","recommended_year","recommended_lifetime","discovery_champion_selected","discovery_challenger_flags","discovery_registry_version","model_version"]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = client.table("missed_winner_snapshots").select(",".join(cols)).eq("user_id", uid).order("captured_date", desc=True).limit(int(limit)).execute().data or []
            return pd.DataFrame(data, columns=cols)
        except Exception:
            st.session_state["bq_missed_winner_migration_needed"] = True
            return pd.DataFrame(columns=cols)
    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query(f"SELECT {','.join(cols)} FROM missed_winner_snapshots ORDER BY captured_date DESC LIMIT ?", conn, params=(int(limit),))


def save_missed_winner_outcomes(frame: pd.DataFrame) -> None:
    if frame is None or frame.empty:
        return
    cols = ["snapshot_id","symbol","name","captured_date","evaluated_date","horizon","entry_price","evaluated_price","return_pct","return_percentile","was_recommended","missed_winner","frozen_score","why_missed"]
    rows = [{c: r.get(c) for c in cols} for _, r in frame.iterrows()]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            for row in rows:
                client.table("missed_winner_outcomes").upsert({"user_id": uid, **row}, on_conflict="user_id,snapshot_id,horizon").execute()
            return
        except Exception:
            st.session_state["bq_missed_winner_migration_needed"] = True
            return
    init_db()
    with _db_connect() as conn:
        sql = f"INSERT OR IGNORE INTO missed_winner_outcomes({','.join(cols)}) VALUES ({','.join(['?']*len(cols))})"
        for row in rows:
            conn.execute(sql, tuple(row.get(c) for c in cols))


def get_missed_winner_outcomes(limit: int = 10000) -> pd.DataFrame:
    cols = ["snapshot_id","symbol","name","captured_date","evaluated_date","horizon","entry_price","evaluated_price","return_pct","return_percentile","was_recommended","missed_winner","frozen_score","why_missed"]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = client.table("missed_winner_outcomes").select(",".join(cols)).eq("user_id", uid).order("evaluated_date", desc=True).limit(int(limit)).execute().data or []
            return pd.DataFrame(data, columns=cols)
        except Exception:
            st.session_state["bq_missed_winner_migration_needed"] = True
            return pd.DataFrame(columns=cols)
    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query(f"SELECT {','.join(cols)} FROM missed_winner_outcomes ORDER BY evaluated_date DESC LIMIT ?", conn, params=(int(limit),))


def refresh_missed_winner_outcomes(current_frame: pd.DataFrame, profile: str, market: str) -> None:
    history = get_missed_winner_snapshots(limit=20000)
    if history.empty or current_frame is None or current_frame.empty:
        return
    today = pd.Timestamp.now().date()
    existing = get_missed_winner_outcomes(limit=50000)
    existing_keys = set(zip(existing.get("snapshot_id", pd.Series(dtype=str)).astype(str), existing.get("horizon", pd.Series(dtype=str)).astype(str))) if not existing.empty else set()
    for horizon, spec in MISSED_WINNER_HORIZONS.items():
        candidates = history[(history["profile"].astype(str) == str(profile)) & (history["market"].astype(str) == str(market))].copy()
        if candidates.empty:
            continue
        candidates["_date"] = pd.to_datetime(candidates["captured_date"], errors="coerce").dt.date
        due_dates = sorted({d for d in candidates["_date"].dropna() if (today - d).days >= int(spec["min_age_days"])})
        for d in due_dates:
            cohort = candidates[candidates["_date"].eq(d)].drop(columns=["_date"])
            if cohort.empty or all((str(x), horizon) in existing_keys for x in cohort["snapshot_id"]):
                continue
            result = evaluate_snapshot_cohort(cohort, current_frame[["Ticker","Pris"]], horizon, today.isoformat())
            if not result.empty:
                result = result[~result["snapshot_id"].astype(str).map(lambda x: (x, horizon) in existing_keys)]
                save_missed_winner_outcomes(result)


def get_universe_qc_states() -> pd.DataFrame:
    cols = [
        "symbol","status","failure_streak","success_count","failure_count",
        "last_checked_at","last_verified_at","last_reason","quarantine_until",
    ]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = client.table("universe_qc_state").select(",".join(cols)).eq("user_id", uid).execute().data or []
            return pd.DataFrame(data, columns=cols)
        except Exception:
            st.session_state["bq_qc_state_migration_needed"] = True
            return pd.DataFrame(columns=cols)
    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query(f"SELECT {','.join(cols)} FROM universe_qc_state", conn)


def save_universe_qc_state(state: dict[str, Any], outcome: str, counted_failure: bool) -> None:
    symbol = str(state.get("symbol") or "").upper().strip()
    if not symbol:
        return
    client = _supabase_client(); uid = current_user_id()
    payload = {
        "symbol": symbol,
        "status": str(state.get("status") or "OKÄND"),
        "failure_streak": int(state.get("failure_streak") or 0),
        "success_count": int(state.get("success_count") or 0),
        "failure_count": int(state.get("failure_count") or 0),
        "last_checked_at": state.get("last_checked_at"),
        "last_verified_at": state.get("last_verified_at"),
        "last_reason": str(state.get("last_reason") or ""),
        "quarantine_until": state.get("quarantine_until"),
    }
    if client is not None and uid:
        try:
            client.table("universe_qc_state").upsert({"user_id": uid, **payload}, on_conflict="user_id,symbol").execute()
            client.table("universe_qc_events").insert({
                "user_id": uid, "symbol": symbol, "outcome": str(outcome),
                "reason": payload["last_reason"], "counted_failure": bool(counted_failure),
            }).execute()
            return
        except Exception:
            st.session_state["bq_qc_state_migration_needed"] = True
            return
    init_db()
    with _db_connect() as conn:
        conn.execute(
            """
            INSERT INTO universe_qc_state(
                symbol,status,failure_streak,success_count,failure_count,last_checked_at,
                last_verified_at,last_reason,quarantine_until
            ) VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET
                status=excluded.status,
                failure_streak=excluded.failure_streak,
                success_count=excluded.success_count,
                failure_count=excluded.failure_count,
                last_checked_at=excluded.last_checked_at,
                last_verified_at=excluded.last_verified_at,
                last_reason=excluded.last_reason,
                quarantine_until=excluded.quarantine_until
            """,
            (
                payload["symbol"], payload["status"], payload["failure_streak"], payload["success_count"],
                payload["failure_count"], payload["last_checked_at"], payload["last_verified_at"],
                payload["last_reason"], payload["quarantine_until"],
            ),
        )
        conn.execute(
            "INSERT INTO universe_qc_events(symbol,outcome,reason,counted_failure) VALUES(?,?,?,?)",
            (symbol, str(outcome), payload["last_reason"], 1 if counted_failure else 0),
        )


def active_quarantine_symbols(states: pd.DataFrame) -> set[str]:
    if states is None or states.empty:
        return set()
    return {
        str(row.get("symbol") or "").upper()
        for _, row in states.iterrows()
        if str(row.get("symbol") or "") and is_quarantined(row)
    }



def get_holdings() -> pd.DataFrame:
    cols = ["holding_id","symbol","purchase_price","quantity","purchase_date","note","created_at"]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = (
                client.table("holdings").select(",".join(cols))
                .eq("user_id", uid).order("created_at", desc=False).execute().data or []
            )
            return pd.DataFrame(data, columns=cols)
        except Exception:
            st.session_state["bq_holdings_migration_needed"] = True
            return pd.DataFrame(columns=cols)
    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query(
            f"SELECT {','.join(cols)} FROM holdings ORDER BY created_at ASC", conn
        )


def add_holding(symbol: str, purchase_price: float, quantity: float, purchase_date: str, note: str = "") -> None:
    symbol = str(symbol or "").upper().strip()
    if not symbol or purchase_price <= 0 or quantity <= 0:
        return
    client = _supabase_client(); uid = current_user_id()
    payload = {
        "symbol": symbol, "purchase_price": float(purchase_price), "quantity": float(quantity),
        "purchase_date": str(purchase_date or ""), "note": str(note or ""),
    }
    if client is not None and uid:
        try:
            client.table("holdings").insert({"user_id": uid, **payload}).execute()
            return
        except Exception:
            st.session_state["bq_holdings_migration_needed"] = True
            return
    init_db()
    with _db_connect() as conn:
        conn.execute(
            "INSERT INTO holdings(symbol,purchase_price,quantity,purchase_date,note) VALUES(?,?,?,?,?)",
            (payload["symbol"], payload["purchase_price"], payload["quantity"], payload["purchase_date"], payload["note"]),
        )


def delete_holding(holding_id: int) -> None:
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            client.table("holdings").delete().eq("user_id", uid).eq("holding_id", int(holding_id)).execute()
            return
        except Exception:
            st.session_state["bq_holdings_migration_needed"] = True
            return
    init_db()
    with _db_connect() as conn:
        conn.execute("DELETE FROM holdings WHERE holding_id=?", (int(holding_id),))



def _load_last_visit() -> str | None:
    """Read the previous overview visit. Missing cloud migration degrades safely."""
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = client.table("visit_state").select("last_seen_at").eq("user_id", uid).limit(1).execute().data or []
            return str(data[0].get("last_seen_at")) if data else None
        except Exception:
            st.session_state["bq_visit_state_migration_needed"] = True
            return None
    init_db()
    with _db_connect() as conn:
        row = conn.execute("SELECT last_seen_at FROM visit_state WHERE singleton=1").fetchone()
    return str(row[0]) if row else None


def _save_last_visit(value: str) -> None:
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            client.table("visit_state").upsert({"user_id": uid, "last_seen_at": value}, on_conflict="user_id").execute()
        except Exception:
            st.session_state["bq_visit_state_migration_needed"] = True
        return
    init_db()
    with _db_connect() as conn:
        conn.execute(
            "INSERT INTO visit_state(singleton,last_seen_at) VALUES(1,?) "
            "ON CONFLICT(singleton) DO UPDATE SET last_seen_at=excluded.last_seen_at",
            (value,),
        )


def visit_context() -> tuple[str | None, str]:
    """Freeze the previous-visit marker for this Streamlit session/reruns."""
    if "bq_previous_visit_at" not in st.session_state:
        previous = _load_last_visit()
        current = datetime.now().isoformat(timespec="seconds")
        st.session_state["bq_previous_visit_at"] = previous
        st.session_state["bq_current_visit_started_at"] = current
        _save_last_visit(current)
    return st.session_state.get("bq_previous_visit_at"), str(st.session_state.get("bq_current_visit_started_at", ""))


def get_reviewed_change_keys() -> set[str]:
    """Return change ids the current user has explicitly reviewed."""
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = client.table("reviewed_changes").select("change_key").eq("user_id", uid).execute().data or []
            return {str(x.get("change_key")) for x in data if x.get("change_key")}
        except Exception:
            st.session_state["bq_review_state_migration_needed"] = True
            return set()
    init_db()
    with _db_connect() as conn:
        rows = conn.execute("SELECT change_key FROM reviewed_changes").fetchall()
    return {str(r[0]) for r in rows}


def mark_change_reviewed(change_key: str) -> None:
    key = str(change_key or "").strip()
    if not key:
        return
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            client.table("reviewed_changes").upsert({"user_id": uid, "change_key": key}, on_conflict="user_id,change_key").execute()
        except Exception:
            st.session_state["bq_review_state_migration_needed"] = True
        return
    init_db()
    with _db_connect() as conn:
        conn.execute("INSERT OR IGNORE INTO reviewed_changes(change_key) VALUES(?)", (key,))



def save_recommendation_records(records: list[dict[str, Any]]) -> None:
    """Idempotently freeze daily model finalists before future outcomes are known."""
    if not records:
        return
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        for rec in records:
            payload = {"user_id": uid, **rec}
            try:
                client.table("recommendation_ledger").upsert(
                    payload, on_conflict="user_id,record_id"
                ).execute()
            except Exception:
                st.session_state["bq_recommendation_ledger_migration_needed"] = True
                return
        return

    init_db()
    cols = [
        "record_id","symbol","name","horizon_type","model_version","profile","market",
        "rank","entry_price","gate","score","confidence","evidence_count","why_now",
        "primary_catalyst","captured_date","captured_at","snapshot_json",
    ]
    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT OR IGNORE INTO recommendation_ledger({','.join(cols)}) VALUES ({placeholders})"
    with _db_connect() as conn:
        for rec in records:
            conn.execute(sql, tuple(rec.get(c) for c in cols))


def get_recommendation_records(limit: int = 500) -> pd.DataFrame:
    cols = [
        "record_id","symbol","name","horizon_type","model_version","profile","market",
        "rank","entry_price","gate","score","confidence","evidence_count","why_now",
        "primary_catalyst","captured_date","captured_at","snapshot_json",
    ]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = (
                client.table("recommendation_ledger").select(",".join(cols))
                .eq("user_id", uid).order("captured_at", desc=True).limit(int(limit))
                .execute().data or []
            )
            return pd.DataFrame(data, columns=cols)
        except Exception:
            st.session_state["bq_recommendation_ledger_migration_needed"] = True
            return pd.DataFrame(columns=cols)

    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query(
            f"SELECT {','.join(cols)} FROM recommendation_ledger ORDER BY captured_at DESC LIMIT ?",
            conn, params=(int(limit),)
        )


def save_recommendation_outcomes(rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        for row in rows:
            payload = {"user_id": uid, **row}
            try:
                client.table("recommendation_outcomes").upsert(
                    payload, on_conflict="user_id,record_id,horizon"
                ).execute()
            except Exception:
                st.session_state["bq_recommendation_ledger_migration_needed"] = True
                return
        return

    init_db()
    cols = [
        "record_id","symbol","horizon","trading_days","evaluated_date","evaluated_price",
        "return_pct","benchmark_symbol","benchmark_name","benchmark_return_pct","excess_return_pct",
        "beat_benchmark","best_return_pct","worst_return_pct","sessions_to_best",
        "positive","gain_10","loss_10","evaluated_at",
    ]
    placeholders = ",".join(["?"] * len(cols))
    sql = (
        f"INSERT INTO recommendation_outcomes({','.join(cols)}) VALUES ({placeholders}) "
        "ON CONFLICT(record_id,horizon) DO UPDATE SET "
        "evaluated_date=excluded.evaluated_date,evaluated_price=excluded.evaluated_price,"
        "return_pct=excluded.return_pct,benchmark_symbol=excluded.benchmark_symbol,"
        "benchmark_name=excluded.benchmark_name,benchmark_return_pct=excluded.benchmark_return_pct,"
        "excess_return_pct=excluded.excess_return_pct,beat_benchmark=excluded.beat_benchmark,"
        "best_return_pct=excluded.best_return_pct,worst_return_pct=excluded.worst_return_pct,"
        "sessions_to_best=excluded.sessions_to_best,positive=excluded.positive,gain_10=excluded.gain_10,"
        "loss_10=excluded.loss_10,evaluated_at=excluded.evaluated_at"
    )
    with _db_connect() as conn:
        for row in rows:
            vals = []
            for c in cols:
                v = row.get(c)
                if c in {"positive","gain_10","loss_10","beat_benchmark"} and v is not None:
                    v = 1 if bool(v) else 0
                vals.append(v)
            conn.execute(sql, tuple(vals))


def get_recommendation_outcomes(limit: int = 2000) -> pd.DataFrame:
    cols = [
        "record_id","symbol","horizon","trading_days","evaluated_date","evaluated_price",
        "return_pct","benchmark_symbol","benchmark_name","benchmark_return_pct","excess_return_pct",
        "beat_benchmark","best_return_pct","worst_return_pct","sessions_to_best",
        "positive","gain_10","loss_10","evaluated_at",
    ]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = (
                client.table("recommendation_outcomes").select(",".join(cols))
                .eq("user_id", uid).order("evaluated_at", desc=True).limit(int(limit))
                .execute().data or []
            )
            return pd.DataFrame(data, columns=cols)
        except Exception:
            st.session_state["bq_recommendation_ledger_migration_needed"] = True
            return pd.DataFrame(columns=cols)

    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query(
            f"SELECT {','.join(cols)} FROM recommendation_outcomes ORDER BY evaluated_at DESC LIMIT ?",
            conn, params=(int(limit),)
        )


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ledger_history(symbol: str, start_date: str) -> pd.DataFrame:
    """Fetch raw price history needed to evaluate an already-frozen recommendation."""
    try:
        start = (pd.Timestamp(start_date) - pd.Timedelta(days=7)).date().isoformat()
        hist = yf.Ticker(symbol).history(
            start=start, interval="1d", auto_adjust=True, actions=False
        )
        if hist is None or hist.empty or "Close" not in hist:
            return pd.DataFrame()
        return hist[["Close"]].dropna()
    except Exception:
        return pd.DataFrame()


def _ledger_benchmark_for_market(market: str) -> tuple[str | None, str]:
    cfg = MARKETS.get(str(market), {})
    symbol = cfg.get("benchmark")
    name = cfg.get("benchmark_name") or "Jämförelseindex"
    if not symbol:
        return "VT", "Globalt aktieindex (VT)"
    return str(symbol), str(name)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_ledger_benchmark_history(symbol: str, start_date: str) -> pd.DataFrame:
    return fetch_ledger_history(symbol, start_date)


def refresh_due_recommendation_outcomes(max_records: int = 12) -> int:
    """Evaluate mature recommendations without changing their original snapshot."""
    recs = get_recommendation_records(limit=500)
    if recs.empty:
        return 0
    existing = get_recommendation_outcomes(limit=5000)
    existing_keys = set()
    if not existing.empty:
        existing_keys = set(zip(existing["record_id"].astype(str), existing["horizon"].astype(str)))

    now = pd.Timestamp.now(tz="UTC")
    # Oldest first: they are most likely to have due outcomes.
    work = recs.sort_values("captured_date").copy()
    evaluated_rows: list[dict[str, Any]] = []
    checked = 0
    for _, rec in work.iterrows():
        if checked >= int(max_records):
            break
        horizon_type = str(rec.get("horizon_type"))
        wanted = ["1m","3m","6m"] if horizon_type == "short" else ["6m","1y","2y"]
        if all((str(rec["record_id"]), h) in existing_keys for h in wanted):
            continue

        age_days = (now.tz_localize(None).normalize() - pd.Timestamp(str(rec["captured_date"])[:10])).days
        min_age = 28 if horizon_type == "short" else 180
        if age_days < min_age:
            continue

        checked += 1
        hist = fetch_ledger_history(str(rec["symbol"]), str(rec["captured_date"]))
        if hist.empty:
            continue
        benchmark_symbol, benchmark_name = _ledger_benchmark_for_market(str(rec.get("market", "")))
        benchmark_hist = fetch_ledger_benchmark_history(benchmark_symbol, str(rec["captured_date"])) if benchmark_symbol else pd.DataFrame()
        rows = evaluate_record_from_history(
            rec.to_dict(), hist, as_of=now,
            benchmark_history=benchmark_hist,
            benchmark_symbol=benchmark_symbol, benchmark_name=benchmark_name,
        )
        for row in rows:
            if (str(row["record_id"]), str(row["horizon"])) not in existing_keys:
                evaluated_rows.append(row)

    if evaluated_rows:
        save_recommendation_outcomes(evaluated_rows)
    return len(evaluated_rows)


def _cloud_watchlist() -> pd.DataFrame:
    client = _supabase_client(); uid = current_user_id()
    if client is None or not uid:
        return pd.DataFrame(columns=["symbol", "note", "target_price", "signal_score_threshold", "signal_score_move", "signal_daily_drop", "breaker_min_score", "breaker_min_quality", "breaker_min_risk", "breaker_max_score_drop", "added_at"])
    try:
        cols = "symbol,note,target_price,signal_score_threshold,signal_score_move,signal_daily_drop,breaker_min_score,breaker_min_quality,breaker_min_risk,breaker_max_score_drop,added_at"
        res = client.table("watchlist").select(cols).eq("user_id", uid).order("added_at", desc=True).execute()
        return pd.DataFrame(res.data or [], columns=cols.split(","))
    except Exception as exc:
        # Backward-compatible read if v2.21 Supabase migration has not been run yet.
        try:
            legacy_cols = "symbol,note,target_price,signal_score_threshold,signal_score_move,signal_daily_drop,added_at"
            res = client.table("watchlist").select(legacy_cols).eq("user_id", uid).order("added_at", desc=True).execute()
            df = pd.DataFrame(res.data or [], columns=legacy_cols.split(","))
            for col in ["breaker_min_score", "breaker_min_quality", "breaker_min_risk", "breaker_max_score_drop"]:
                df[col] = 0.0
            st.session_state["bq_case_breaker_migration_needed"] = True
            return df
        except Exception:
            st.session_state["bq_cloud_error"] = str(exc)
            return pd.DataFrame(columns=["symbol", "note", "target_price", "signal_score_threshold", "signal_score_move", "signal_daily_drop", "breaker_min_score", "breaker_min_quality", "breaker_min_risk", "breaker_max_score_drop", "added_at"])


def get_watchlist() -> pd.DataFrame:
    if cloud_enabled() and current_user_id():
        return _cloud_watchlist()
    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query("SELECT symbol, note, target_price, signal_score_threshold, signal_score_move, signal_daily_drop, breaker_min_score, breaker_min_quality, breaker_min_risk, breaker_max_score_drop, added_at FROM watchlist ORDER BY added_at DESC", conn)


def watched_symbols() -> list[str]:
    df = get_watchlist()
    return df["symbol"].astype(str).tolist() if not df.empty else []


def is_watched(symbol: str) -> bool:
    return symbol in set(watched_symbols())


def toggle_watchlist(symbol: str) -> None:
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        existing = client.table("watchlist").select("symbol").eq("user_id", uid).eq("symbol", symbol).execute().data or []
        if existing:
            client.table("watchlist").delete().eq("user_id", uid).eq("symbol", symbol).execute()
        else:
            client.table("watchlist").insert({"user_id": uid, "symbol": symbol}).execute()
        return
    init_db()
    with _db_connect() as conn:
        exists = conn.execute("SELECT 1 FROM watchlist WHERE symbol=?", (symbol,)).fetchone()
        if exists:
            conn.execute("DELETE FROM watchlist WHERE symbol=?", (symbol,))
        else:
            conn.execute("INSERT INTO watchlist(symbol) VALUES (?)", (symbol,))


def update_watchlist_item(
    symbol: str,
    note: str,
    target_price: float | None,
    signal_score_threshold: float = 75.0,
    signal_score_move: float = 8.0,
    signal_daily_drop: float = 5.0,
    breaker_min_score: float = 0.0,
    breaker_min_quality: float = 0.0,
    breaker_min_risk: float = 0.0,
    breaker_max_score_drop: float = 0.0,
) -> None:
    target = None if target_price is None or not np.isfinite(target_price) or target_price <= 0 else float(target_price)
    score_threshold = float(np.clip(signal_score_threshold, 0, 100))
    score_move = float(np.clip(signal_score_move, 1, 50))
    daily_drop = float(np.clip(signal_daily_drop, 1, 50))
    breaker_min_score = float(np.clip(breaker_min_score, 0, 100))
    breaker_min_quality = float(np.clip(breaker_min_quality, 0, 100))
    breaker_min_risk = float(np.clip(breaker_min_risk, 0, 100))
    breaker_max_score_drop = float(np.clip(breaker_max_score_drop, 0, 100))
    client = _supabase_client(); uid = current_user_id()
    payload = {
        "note": note.strip(), "target_price": target,
        "signal_score_threshold": score_threshold,
        "signal_score_move": score_move,
        "signal_daily_drop": daily_drop,
        "breaker_min_score": breaker_min_score,
        "breaker_min_quality": breaker_min_quality,
        "breaker_min_risk": breaker_min_risk,
        "breaker_max_score_drop": breaker_max_score_drop,
    }
    if client is not None and uid:
        try:
            client.table("watchlist").update(payload).eq("user_id", uid).eq("symbol", symbol).execute()
        except Exception as exc:
            # Preserve existing watchlist edits on an older Supabase schema, but case-breakers
            # require the v2.21 migration before they can be stored in the cloud.
            legacy_payload = {k: payload[k] for k in ["note", "target_price", "signal_score_threshold", "signal_score_move", "signal_daily_drop"]}
            client.table("watchlist").update(legacy_payload).eq("user_id", uid).eq("symbol", symbol).execute()
            st.session_state["bq_case_breaker_migration_needed"] = True
            st.session_state["bq_cloud_error"] = f"Case-breaker-regler kunde inte sparas i molnet ännu: {exc}"
        return
    init_db()
    with _db_connect() as conn:
        conn.execute(
            "UPDATE watchlist SET note=?, target_price=?, signal_score_threshold=?, signal_score_move=?, signal_daily_drop=?, breaker_min_score=?, breaker_min_quality=?, breaker_min_risk=?, breaker_max_score_drop=? WHERE symbol=?",
            (note.strip(), target, score_threshold, score_move, daily_drop, breaker_min_score, breaker_min_quality, breaker_min_risk, breaker_max_score_drop, symbol),
        )


def clear_watchlist() -> None:
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        client.table("watchlist").delete().eq("user_id", uid).execute()
        return
    init_db()
    with _db_connect() as conn:
        conn.execute("DELETE FROM watchlist")


def get_notification_preferences() -> dict[str, Any]:
    """Read e-mail notification settings. E-mail delivery itself is done server-side."""
    defaults: dict[str, Any] = {
        "email_enabled": False,
        "email": current_user_email(),
        "min_priority": 2,
        "notify_kinds": SIGNAL_KINDS.copy(),
    }
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = client.table("notification_preferences").select("email_enabled,email,min_priority,notify_kinds").eq("user_id", uid).limit(1).execute().data or []
            if not data:
                return defaults
            row = data[0]
            kinds = row.get("notify_kinds")
            if not isinstance(kinds, list):
                kinds = SIGNAL_KINDS.copy()
            return {
                "email_enabled": bool(row.get("email_enabled", False)),
                "email": str(row.get("email") or defaults["email"]),
                "min_priority": int(row.get("min_priority") or 2),
                "notify_kinds": [str(x) for x in kinds if str(x) in SIGNAL_KINDS],
            }
        except Exception as exc:
            st.session_state["bq_cloud_error"] = str(exc)
            return defaults
    init_db()
    with _db_connect() as conn:
        row = conn.execute("SELECT email_enabled,email,min_priority,notify_kinds FROM notification_preferences WHERE singleton=1").fetchone()
    if not row:
        return defaults
    kinds = [x for x in str(row[3] or "").split("|") if x in SIGNAL_KINDS] or SIGNAL_KINDS.copy()
    return {"email_enabled": bool(row[0]), "email": str(row[1] or defaults["email"]), "min_priority": int(row[2] or 2), "notify_kinds": kinds}


def update_notification_preferences(email_enabled: bool, email: str, min_priority: int, notify_kinds: list[str]) -> None:
    clean_email = email.strip()
    priority = int(np.clip(min_priority, 1, 3))
    kinds = [x for x in SIGNAL_KINDS if x in set(notify_kinds)]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        payload = {
            "user_id": uid, "email_enabled": bool(email_enabled), "email": clean_email,
            "min_priority": priority, "notify_kinds": kinds,
        }
        client.table("notification_preferences").upsert(payload, on_conflict="user_id").execute()
        return
    init_db()
    with _db_connect() as conn:
        conn.execute(
            "UPDATE notification_preferences SET email_enabled=?,email=?,min_priority=?,notify_kinds=?,updated_at=CURRENT_TIMESTAMP WHERE singleton=1",
            (1 if email_enabled else 0, clean_email, priority, "|".join(kinds)),
        )


def save_score_history(df: pd.DataFrame, profile: str) -> None:
    """Persist a daily score + component snapshot for watched shares."""
    watched = set(watched_symbols())
    if not watched or df.empty:
        return
    cols = ["Ticker", "Borsify Score", "Värdering", "Kvalitet", "Marknadsläge", "Utdelning", "Risk", "Datatäckning"]
    rows = df[df["Ticker"].isin(watched)][cols].dropna(subset=["Borsify Score"])
    if rows.empty:
        return
    today = datetime.now().date().isoformat()
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        for _, row in rows.iterrows():
            payload = {
                "user_id": uid, "symbol": str(row["Ticker"]), "score": float(row["Borsify Score"]), "profile": profile, "captured_date": today,
                "valuation": _num(row.get("Värdering")), "quality": _num(row.get("Kvalitet")), "setup": _num(row.get("Marknadsläge")),
                "income": _num(row.get("Utdelning")), "risk": _num(row.get("Risk")), "coverage": _num(row.get("Datatäckning")),
            }
            payload = {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in payload.items()}
            try:
                client.table("score_history").upsert(payload, on_conflict="user_id,symbol,profile,captured_date").execute()
            except Exception:
                # Compatibility with a v1.6 schema until the migration has been run.
                fallback = {k: payload[k] for k in ["user_id", "symbol", "score", "profile", "captured_date"]}
                try: client.table("score_history").upsert(fallback, on_conflict="user_id,symbol,profile,captured_date").execute()
                except Exception: pass
        return
    init_db()
    with _db_connect() as conn:
        for _, row in rows.iterrows():
            vals = (
                float(row["Borsify Score"]), _num(row.get("Värdering")), _num(row.get("Kvalitet")), _num(row.get("Marknadsläge")),
                _num(row.get("Utdelning")), _num(row.get("Risk")), _num(row.get("Datatäckning")),
            )
            existing = conn.execute("SELECT rowid FROM score_history WHERE symbol=? AND profile=? AND substr(captured_at,1,10)=?", (str(row["Ticker"]), profile, today)).fetchone()
            if existing:
                conn.execute("UPDATE score_history SET score=?,valuation=?,quality=?,setup=?,income=?,risk=?,coverage=?,captured_at=CURRENT_TIMESTAMP WHERE rowid=?", (*vals, existing[0]))
            else:
                conn.execute("INSERT INTO score_history(symbol,score,profile,valuation,quality,setup,income,risk,coverage) VALUES (?,?,?,?,?,?,?,?,?)", (str(row["Ticker"]), vals[0], profile, *vals[1:]))


def get_score_history(symbol: str, profile: str) -> pd.DataFrame:
    """Return chronological stored snapshots for Case Journal. Gracefully supports older schemas."""
    client = _supabase_client(); uid = current_user_id()
    fields = "score,valuation,quality,setup,income,risk,coverage,captured_date,created_at"
    columns = ["score", "valuation", "quality", "setup", "income", "risk", "coverage", "captured_date", "created_at"]
    try:
        if client is not None and uid:
            try:
                data = client.table("score_history").select(fields).eq("user_id", uid).eq("symbol", symbol).eq("profile", profile).order("captured_date").execute().data or []
            except Exception:
                data = client.table("score_history").select("score,captured_date,created_at").eq("user_id", uid).eq("symbol", symbol).eq("profile", profile).order("captured_date").execute().data or []
            return pd.DataFrame(data)
        init_db()
        with _db_connect() as conn:
            rows = conn.execute(
                "SELECT score,valuation,quality,setup,income,risk,coverage,substr(captured_at,1,10),captured_at FROM score_history WHERE symbol=? AND profile=? ORDER BY captured_at",
                (symbol, profile),
            ).fetchall()
        return pd.DataFrame(rows, columns=columns)
    except Exception:
        return pd.DataFrame(columns=columns)


def previous_score_snapshot(symbol: str, profile: str) -> dict[str, Any] | None:
    """Return the latest earlier daily component snapshot for explainability."""
    client = _supabase_client(); uid = current_user_id(); today = datetime.now().date().isoformat()
    fields = "score,valuation,quality,setup,income,risk,coverage,captured_date"
    try:
        if client is not None and uid:
            try:
                data = client.table("score_history").select(fields).eq("user_id", uid).eq("symbol", symbol).eq("profile", profile).lt("captured_date", today).order("captured_date", desc=True).limit(1).execute().data or []
            except Exception:
                data = client.table("score_history").select("score,captured_date").eq("user_id", uid).eq("symbol", symbol).eq("profile", profile).lt("captured_date", today).order("captured_date", desc=True).limit(1).execute().data or []
            return data[0] if data else None
        init_db()
        with _db_connect() as conn:
            row = conn.execute("SELECT score,valuation,quality,setup,income,risk,coverage,substr(captured_at,1,10) FROM score_history WHERE symbol=? AND profile=? AND substr(captured_at,1,10)<? ORDER BY captured_at DESC LIMIT 1", (symbol, profile, today)).fetchone()
            if not row: return None
            keys = ["score","valuation","quality","setup","income","risk","coverage","captured_date"]
            return dict(zip(keys, row))
    except Exception:
        return None


def _score_explanation(row: pd.Series, profile: str) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Break the score into weighted components and concrete strengths/weaknesses."""
    weights = PROFILE_WEIGHTS[profile]
    factors = [
        ("Värdering", "valuation"), ("Kvalitet", "quality"), ("Marknadsläge", "setup"),
        ("Utdelning", "income"), ("Risk", "risk"),
    ]
    table = []
    for label, key in factors:
        score = _num(row.get(label)); weight = weights[key]
        weighted = score * weight if np.isfinite(score) else np.nan
        impact = (score - 50) * weight if np.isfinite(score) else np.nan
        if not np.isfinite(score): assessment = "Data saknas"
        elif score >= 75: assessment = "Stark"
        elif score >= 60: assessment = "Positiv"
        elif score >= 40: assessment = "Neutral"
        elif score >= 25: assessment = "Svag"
        else: assessment = "Mycket svag"
        table.append({"Del": label, "Score": score, "Vikt %": weight * 100, "Viktade poäng": weighted, "Påverkan mot neutral": impact, "Bedömning": assessment})

    strengths: list[str] = []
    weaknesses: list[str] = []
    pe, fpe, fcfy = _num(row.get("P/E")), _num(row.get("Forward P/E")), _num(row.get("FCF-yield"))
    roe, margin, growth, debt = _num(row.get("ROE")), _num(row.get("Vinstmarginal")), _num(row.get("Omsättningstillväxt")), _num(row.get("Skuld/eget kapital"))
    rsi, m3, dist = _num(row.get("RSI14")), _num(row.get("3 mån")), _num(row.get("Avstånd SMA200"))
    dy, payout, coverage = _num(row.get("Direktavkastning")), _num(row.get("Utdelningsandel")), _num(row.get("Datatäckning"))
    if np.isfinite(pe) and 0 < pe <= 15: strengths.append(f"P/E {pe:.1f} är relativt låg. Förenklat betalar marknaden inte lika många årsvinster för aktien som vid ett högt P/E.")
    if np.isfinite(fpe) and 0 < fpe < pe: strengths.append(f"Forward P/E {fpe:.1f} är lägre än historisk P/E {pe:.1f}.")
    if np.isfinite(fcfy) and fcfy >= .05: strengths.append(f"FCF-yield {fcfy:.1%} ger stöd åt värderingen.")
    if np.isfinite(roe) and roe >= .15: strengths.append(f"ROE {roe:.1%} visar att bolaget hittills varit bra på att skapa vinst med ägarnas kapital.")
    if np.isfinite(margin) and margin >= .10: strengths.append(f"Vinstmarginal {margin:.1%} är stark.")
    if np.isfinite(growth) and growth >= .08: strengths.append(f"Omsättningen växer {growth:.1%} enligt tillgänglig data.")
    if np.isfinite(rsi) and 32 <= rsi <= 48: strengths.append(f"RSI {rsi:.0f} visar att kursen nyligen pressats ned till ett område där modellen ibland hittar återhämtningslägen.")
    if np.isfinite(dy) and .025 <= dy <= .08: strengths.append(f"Direktavkastning {dy:.1%} bidrar positivt.")

    if np.isfinite(pe) and pe >= 30: weaknesses.append(f"P/E {pe:.1f} är högt. Det betyder att marknaden betalar mycket för varje krona i nuvarande vinst, vilket ökar kraven på framtida tillväxt.")
    if np.isfinite(roe) and roe < 0: weaknesses.append(f"ROE {roe:.1%} är negativ.")
    if np.isfinite(margin) and margin < 0: weaknesses.append(f"Vinstmarginal {margin:.1%} är negativ.")
    if np.isfinite(debt) and debt > 200: weaknesses.append(f"Skuld/eget kapital {debt:.0f} är hög och ger riskavdrag.")
    if np.isfinite(m3) and m3 <= -.15: weaknesses.append(f"Tremånadersmomentum {m3:.1%} är tydligt negativt.")
    if np.isfinite(dist) and dist <= -.10: weaknesses.append(f"Kursen ligger {abs(dist):.1%} under sitt 200-dagarssnitt (SMA200), vilket tyder på en svagare långsiktig kurstrend.")
    if np.isfinite(payout) and payout > 1: weaknesses.append(f"Utdelningsandelen {payout:.0%} är över 100 %.")
    if np.isfinite(coverage) and coverage < .60: weaknesses.append(f"Datatäckningen är bara {coverage:.0%}; totalpoängen rabatteras.")

    # Always surface the strongest model component even when raw metrics are less obvious.
    sorted_factors = sorted(table, key=lambda x: (_num(x["Påverkan mot neutral"])), reverse=True)
    if sorted_factors and _num(sorted_factors[0]["Påverkan mot neutral"]) > 3:
        strengths.insert(0, f"{sorted_factors[0]['Del']} är modellens starkaste del ({sorted_factors[0]['Score']:.0f}/100).")
    if sorted_factors and _num(sorted_factors[-1]["Påverkan mot neutral"]) < -3:
        weaknesses.insert(0, f"{sorted_factors[-1]['Del']} är modellens svagaste del ({sorted_factors[-1]['Score']:.0f}/100).")
    return pd.DataFrame(table), strengths[:5], weaknesses[:5]

def score_change(symbol: str, profile: str, current_score: float) -> float | None:
    """Compare with the latest earlier daily snapshot."""
    client = _supabase_client(); uid = current_user_id()
    today = datetime.now().date().isoformat()
    try:
        if client is not None and uid:
            data = client.table("score_history").select("score,captured_date").eq("user_id", uid).eq("symbol", symbol).eq("profile", profile).lt("captured_date", today).order("captured_date", desc=True).limit(1).execute().data or []
            if data:
                return float(current_score) - float(data[0]["score"])
            return None
        init_db()
        with _db_connect() as conn:
            row = conn.execute("SELECT score FROM score_history WHERE symbol=? AND profile=? AND substr(captured_at,1,10)<? ORDER BY captured_at DESC LIMIT 1", (symbol, profile, today)).fetchone()
            return float(current_score) - float(row[0]) if row else None
    except Exception:
        return None


def previous_score(symbol: str, profile: str) -> float | None:
    """Latest score from an earlier day, used for threshold-crossing signals."""
    client = _supabase_client(); uid = current_user_id()
    today = datetime.now().date().isoformat()
    try:
        if client is not None and uid:
            data = client.table("score_history").select("score,captured_date").eq("user_id", uid).eq("symbol", symbol).eq("profile", profile).lt("captured_date", today).order("captured_date", desc=True).limit(1).execute().data or []
            return float(data[0]["score"]) if data else None
        init_db()
        with _db_connect() as conn:
            row = conn.execute("SELECT score FROM score_history WHERE symbol=? AND profile=? AND substr(captured_at,1,10)<? ORDER BY captured_at DESC LIMIT 1", (symbol, profile, today)).fetchone()
            return float(row[0]) if row else None
    except Exception:
        return None


def previous_top_symbols(profile: str, limit: int = 10) -> set[str]:
    """Top symbols from the latest earlier scan date for the signed-in user/local app."""
    client = _supabase_client(); uid = current_user_id()
    today = datetime.now().date().isoformat()
    try:
        if client is not None and uid:
            dates = client.table("radar_history").select("captured_date").eq("user_id", uid).eq("profile", profile).lt("captured_date", today).order("captured_date", desc=True).limit(1).execute().data or []
            if not dates:
                return set()
            d = dates[0]["captured_date"]
            data = client.table("radar_history").select("symbol,rank").eq("user_id", uid).eq("profile", profile).eq("captured_date", d).lte("rank", limit).execute().data or []
            return {str(x["symbol"]) for x in data}
        init_db()
        with _db_connect() as conn:
            row = conn.execute("SELECT captured_date FROM radar_history WHERE profile=? AND captured_date<? ORDER BY captured_date DESC LIMIT 1", (profile, today)).fetchone()
            if not row:
                return set()
            rows = conn.execute("SELECT symbol FROM radar_history WHERE profile=? AND captured_date=? AND rank<=?", (profile, row[0], limit)).fetchall()
            return {str(x[0]) for x in rows}
    except Exception:
        return set()



def previous_radar_snapshot(profile: str, limit: int = 10) -> pd.DataFrame:
    """Latest earlier radar snapshot with rank, score and frozen explanation inputs.

    The optional ``details`` payload was added in v3.44. Older cloud schemas are
    read through a legacy fallback, so missing historical details stay missing
    rather than being reconstructed from today's data.
    """
    client = _supabase_client(); uid = current_user_id()
    today = datetime.now().date().isoformat()
    base_columns = ["Ticker", "Rank", "Score", "captured_date"]
    try:
        if client is not None and uid:
            dates = client.table("radar_history").select("captured_date").eq("user_id", uid).eq("profile", profile).lt("captured_date", today).order("captured_date", desc=True).limit(1).execute().data or []
            if not dates:
                return pd.DataFrame(columns=base_columns)
            d = dates[0]["captured_date"]
            try:
                data = client.table("radar_history").select("symbol,rank,score,captured_date,details").eq("user_id", uid).eq("profile", profile).eq("captured_date", d).lte("rank", limit).order("rank").execute().data or []
            except Exception:
                data = client.table("radar_history").select("symbol,rank,score,captured_date").eq("user_id", uid).eq("profile", profile).eq("captured_date", d).lte("rank", limit).order("rank").execute().data or []
            rows = []
            for x in data:
                row = {"Ticker": x.get("symbol"), "Rank": x.get("rank"), "Score": x.get("score"), "captured_date": x.get("captured_date")}
                details = x.get("details")
                if isinstance(details, str):
                    try: details = json.loads(details)
                    except Exception: details = None
                if isinstance(details, dict):
                    row.update(details)
                rows.append(row)
            return pd.DataFrame(rows)
        init_db()
        with _db_connect() as conn:
            row = conn.execute("SELECT captured_date FROM radar_history WHERE profile=? AND captured_date<? ORDER BY captured_date DESC LIMIT 1", (profile, today)).fetchone()
            if not row:
                return pd.DataFrame(columns=base_columns)
            rows = conn.execute("SELECT symbol,rank,score,captured_date,details FROM radar_history WHERE profile=? AND captured_date=? AND rank<=? ORDER BY rank", (profile, row[0], limit)).fetchall()
        parsed = []
        for symbol, rank, score, captured_date, details_raw in rows:
            item = {"Ticker": symbol, "Rank": rank, "Score": score, "captured_date": captured_date}
            if details_raw:
                try:
                    details = json.loads(details_raw)
                    if isinstance(details, dict): item.update(details)
                except Exception:
                    pass
            parsed.append(item)
        return pd.DataFrame(parsed)
    except Exception:
        return pd.DataFrame(columns=base_columns)

def save_radar_history(top_df: pd.DataFrame, profile: str) -> None:
    """Store today's ranking and frozen explanation inputs for later comparisons.

    ``details`` is point-in-time only. If an older Supabase schema lacks that
    column, Borsify falls back to the legacy rank/score payload rather than
    breaking the scan.
    """
    if top_df.empty:
        return
    today = datetime.now().date().isoformat()
    client = _supabase_client(); uid = current_user_id()
    rows = top_df.head(20).reset_index(drop=True)
    if client is not None and uid:
        for i, row in rows.iterrows():
            score = _num(row.get("Borsify Score"))
            if not np.isfinite(score):
                continue
            payload = {
                "user_id": uid, "symbol": str(row.get("Ticker", "")), "profile": profile,
                "rank": int(i + 1), "score": float(score), "captured_date": today,
                "details": snapshot_details(row),
            }
            try:
                client.table("radar_history").upsert(payload, on_conflict="user_id,symbol,profile,captured_date").execute()
            except Exception:
                legacy = {k: payload[k] for k in ["user_id", "symbol", "profile", "rank", "score", "captured_date"]}
                try: client.table("radar_history").upsert(legacy, on_conflict="user_id,symbol,profile,captured_date").execute()
                except Exception: pass
        return
    init_db()
    with _db_connect() as conn:
        for i, row in rows.iterrows():
            score = _num(row.get("Borsify Score"))
            if not np.isfinite(score):
                continue
            details = json.dumps(snapshot_details(row), ensure_ascii=False)
            conn.execute(
                "INSERT INTO radar_history(symbol,profile,rank,score,captured_date,details) VALUES (?,?,?,?,?,?) ON CONFLICT(symbol,profile,captured_date) DO UPDATE SET rank=excluded.rank,score=excluded.score,details=excluded.details,captured_at=CURRENT_TIMESTAMP",
                (str(row.get("Ticker", "")), profile, int(i + 1), float(score), today, details),
            )


def _signal_event_key(sig: dict[str, Any], profile: str, occurred_date: str | None = None) -> str:
    d = occurred_date or datetime.now().date().isoformat()
    return f"{d}|{profile}|{sig['symbol']}|{sig['kind']}"


def persist_signals(signals: list[dict[str, Any]], profile: str) -> None:
    """Store signal events once per day/profile/symbol/kind while preserving read state."""
    if not signals:
        return
    occurred = datetime.now().date().isoformat()
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        for sig in signals:
            payload = {
                "user_id": uid,
                "event_key": _signal_event_key(sig, profile, occurred),
                "symbol": sig["symbol"], "kind": sig["kind"], "text": sig["text"],
                "priority": int(sig["priority"]), "profile": profile, "occurred_date": occurred,
            }
            try:
                client.table("signal_history").upsert(payload, on_conflict="user_id,event_key").execute()
            except Exception:
                pass
        return
    init_db()
    with _db_connect() as conn:
        for sig in signals:
            conn.execute(
                "INSERT INTO signal_history(event_key,symbol,kind,text,priority,profile,occurred_date) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(event_key) DO UPDATE SET text=excluded.text,priority=excluded.priority",
                (_signal_event_key(sig, profile, occurred), sig["symbol"], sig["kind"], sig["text"], int(sig["priority"]), profile, occurred),
            )


def get_signal_history(limit: int = 150) -> pd.DataFrame:
    cols = ["event_key", "symbol", "kind", "text", "priority", "profile", "occurred_date", "is_read", "email_sent_at", "created_at"]
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        try:
            data = client.table("signal_history").select(",".join(cols)).eq("user_id", uid).order("created_at", desc=True).limit(limit).execute().data or []
            return pd.DataFrame(data, columns=cols)
        except Exception:
            return pd.DataFrame(columns=cols)
    init_db()
    with _db_connect() as conn:
        return pd.read_sql_query(
            "SELECT event_key,symbol,kind,text,priority,profile,occurred_date,is_read,email_sent_at,created_at FROM signal_history ORDER BY created_at DESC LIMIT ?",
            conn, params=(limit,),
        )


def mark_signal_read(event_key: str, is_read: bool = True) -> None:
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        client.table("signal_history").update({"is_read": bool(is_read)}).eq("user_id", uid).eq("event_key", event_key).execute()
        return
    init_db()
    with _db_connect() as conn:
        conn.execute("UPDATE signal_history SET is_read=? WHERE event_key=?", (1 if is_read else 0, event_key))


def mark_all_signals_read() -> None:
    client = _supabase_client(); uid = current_user_id()
    if client is not None and uid:
        client.table("signal_history").update({"is_read": True}).eq("user_id", uid).eq("is_read", False).execute()
        return
    init_db()
    with _db_connect() as conn:
        conn.execute("UPDATE signal_history SET is_read=1 WHERE is_read=0")


def build_watch_signals(watch_df: pd.DataFrame, top_df: pd.DataFrame, watch_meta: pd.DataFrame, profile: str) -> list[dict[str, Any]]:
    """Create transparent alerts using per-share thresholds from the watchlist."""
    if watch_df.empty:
        return []
    meta_by_symbol = {str(r["symbol"]): r for _, r in watch_meta.iterrows()} if not watch_meta.empty else {}
    current_top = {str(x) for x in top_df.head(10)["Ticker"].tolist()}
    prior_top = previous_top_symbols(profile, 10)
    signals: list[dict[str, Any]] = []
    for _, row in watch_df.iterrows():
        sym = str(row["Ticker"]); name = str(row.get("Namn") or sym)
        score = _num(row.get("Borsify Score")); price = _num(row.get("Pris")); daily = _num(row.get("Dagsförändring"))
        prev = previous_score(sym, profile)
        delta = score - prev if np.isfinite(score) and prev is not None and np.isfinite(prev) else None
        meta = meta_by_symbol.get(sym)
        target = _num(meta.get("target_price")) if meta is not None else np.nan
        threshold = _num(meta.get("signal_score_threshold")) if meta is not None else 75.0
        move = _num(meta.get("signal_score_move")) if meta is not None else 8.0
        daily_drop = _num(meta.get("signal_daily_drop")) if meta is not None else 5.0
        threshold = threshold if np.isfinite(threshold) else 75.0
        move = move if np.isfinite(move) else 8.0
        daily_drop = daily_drop if np.isfinite(daily_drop) else 5.0

        if sym in current_top and prior_top and sym not in prior_top:
            rank = next((i + 1 for i, x in enumerate(top_df.head(10)["Ticker"].astype(str).tolist()) if x == sym), None)
            signals.append({"priority": 3, "symbol": sym, "name": name, "kind": "Ny i topp 10", "text": f"{name} har gått in på plats {rank} i Borsify Radar ({score:.0f}/100)."})
        if delta is not None and delta >= move:
            signals.append({"priority": 3, "symbol": sym, "name": name, "kind": "Score lyfter", "text": f"Borsify Score har stigit {delta:+.1f} sedan föregående registrerade dag till {score:.0f}/100. Din gräns är {move:.1f}."})
        if prev is not None and prev < threshold <= score:
            signals.append({"priority": 2, "symbol": sym, "name": name, "kind": "Scoregräns passerad", "text": f"Borsify Score har passerat din gräns {threshold:.0f}: {prev:.1f} → {score:.1f}."})
        if np.isfinite(target) and np.isfinite(price) and price >= target:
            signals.append({"priority": 3, "symbol": sym, "name": name, "kind": "Målkurs nådd", "text": f"Kursen {price:.2f} har nått/passerat din målkurs {target:.2f}."})
        if np.isfinite(daily) and daily <= -(daily_drop / 100.0):
            signals.append({"priority": 2, "symbol": sym, "name": name, "kind": "Kraftigt dagsfall", "text": f"Aktien är ned {daily:.1%} idag, vilket passerar din gräns på {daily_drop:.1f} %. Kontrollera nyheter/bolagshändelser."})
        if delta is not None and delta <= -move:
            signals.append({"priority": 2, "symbol": sym, "name": name, "kind": "Score faller", "text": f"Borsify Score har sjunkit {delta:.1f} sedan föregående registrerade dag till {score:.0f}/100. Din gräns är {move:.1f}."})
    return sorted(signals, key=lambda x: (-int(x["priority"]), x["symbol"], x["kind"]))


def render_signal_cards(signals: list[dict[str, Any]]) -> None:
    if not signals:
        st.info("Inga nya bevakningssignaler just nu.")
        return
    for sig in signals:
        icon = "🔔" if sig["priority"] >= 3 else "⚠️"
        st.markdown(f"**{icon} {sig['kind']} · {sig['symbol']}**  ")
        st.write(sig["text"])


def load_universe_file() -> pd.DataFrame:
    if not UNIVERSE_PATH.exists():
        return pd.DataFrame({"Ticker": SWEDEN_BROAD_TICKERS, "Segment": "Kuraterad"})
    try:
        uni = pd.read_csv(UNIVERSE_PATH)
        if "Ticker" not in uni.columns:
            raise ValueError("Ticker-kolumn saknas")
        uni["Ticker"] = uni["Ticker"].astype(str).str.strip().str.upper()
        uni = uni[uni["Ticker"].ne("")].drop_duplicates("Ticker")
        if "Segment" not in uni.columns:
            uni["Segment"] = "Sverige"
        return uni
    except Exception:
        return pd.DataFrame({"Ticker": SWEDEN_BROAD_TICKERS, "Segment": "Kuraterad"})


def fmt_pct(v: Any, digits: int = 1) -> str:
    x = _num(v); return "—" if not np.isfinite(x) else f"{x * 100:.{digits}f}%"


def fmt_num(v: Any, digits: int = 1) -> str:
    x = _num(v); return "—" if not np.isfinite(x) else f"{x:.{digits}f}"




def beginner_term(term: str) -> str:
    explanations = {
        "P/E": "hur många kronor marknaden betalar för varje krona i bolagets årsvinst. Lägre kan vara billigare, men bara om vinsten är hållbar",
        "ROE": "avkastning på eget kapital – ungefär hur effektivt bolaget använder ägarnas pengar för att skapa vinst",
        "RSI": "ett kortsiktigt temperaturmått för kursen. Lågt värde kan betyda att aktien nyligen pressats ned, högt värde att den gått starkt",
        "SMA200": "aktiekursens genomsnitt under ungefär 200 handelsdagar. Över snittet brukar tolkas som starkare lång trend, under som svagare",
        "ATR": "ett mått på hur mycket aktien normalt rör sig från dag till dag. Borsify använder det för att anpassa stop-avstånd efter aktiens normala svängningar",
        "direktavkastning": "årlig utdelning i förhållande till aktiekursen. 4 % betyder ungefär 4 kr i årlig utdelning per 100 kr investerat, om utdelningen ligger kvar",
        "drawdown": "hur mycket värdet som mest har fallit från en tidigare topp. −20 % betyder att 100 000 kr som mest tillfälligt hade varit nere kring 80 000 kr",
        "profit factor": "summan av vinster delad med summan av förluster. Över 1 betyder att vinsterna varit större än förlusterna i testet",
        "Sharpe": "ett förenklat mått på hur mycket avkastning strategin gett i förhållande till hur mycket den svängt. Högre är normalt bättre",
        "risk-on": "ett marknadsläge där börsen generellt är starkare och investerare oftare vågar ta mer risk",
        "risk-off": "ett försiktigare marknadsläge där börsen generellt är svagare och investerare söker mindre risk",
        "volatilitet": "hur mycket priset svänger. Hög volatilitet betyder större rörelser både upp och ned – inte automatiskt högre framtida avkastning",
        "likviditet": "hur lätt en aktie normalt går att köpa eller sälja utan att priset påverkas mycket. Låg likviditet kan ge sämre köp- och säljpris",
        "stop-loss": "en förutbestämd nivå där man planerar att sälja för att begränsa en förlust. Den garanterar inte exakt säljpris om kursen gapar",
        "hävstång": "att få större marknadsexponering än det kapital man satt in. Det förstorar både vinster och förluster och innebär högre risk",
        "diversifiering": "att sprida kapitalet på flera innehav så att ett enskilt bolag inte får lika stor påverkan på hela portföljen",
    }
    return explanations.get(term, term)


def plain_finance_text(value: Any) -> str:
    """Presentation-only translation of model language for novice surfaces."""
    return simplify_decision_text(value)


def render_beginner_glossary(key: str = "guide") -> None:
    with st.expander("Vad betyder börsorden?", expanded=False):
        st.markdown(
            "**P/E:** priset jämfört med bolagets vinst.  \\n"
            "**RSI:** om kursen nyligen gått ovanligt starkt eller svagt.  \\n"
            "**SMA200:** kursen jämfört med sitt långa genomsnitt.  \\n"
            "**ATR:** hur mycket kursen brukar röra sig per dag.  \\n"
            "**Direktavkastning:** utdelningen jämfört med aktiens pris."
        )

def apply_discovery_intent(df: pd.DataFrame, intent: str) -> pd.DataFrame:
    """Rank the already screened universe by a beginner-friendly goal without changing core scores."""
    out = df.copy()
    def c(name: str, default: float = 50.0) -> pd.Series:
        if name not in out.columns:
            return pd.Series(default, index=out.index, dtype=float)
        return pd.to_numeric(out[name], errors="coerce").fillna(default)
    if intent == "Bra långsiktig investering":
        match = c("INVEST Score")
    elif intent == "Utdelningsaktier":
        match = .55*c("Utdelning") + .20*c("Kvalitet") + .15*c("Risk") + .10*c("Värdering")
        dy = pd.to_numeric(out.get("Direktavkastning"), errors="coerce")
        out = out[dy.notna() & (dy > 0)].copy(); match = match.loc[out.index]
    elif intent == "Billiga kvalitetsbolag":
        match = .45*c("Värdering") + .35*c("Kvalitet") + .20*c("Risk")
    elif intent == "Aktier som fallit mycket":
        match = c("REVERSAL Score")
    elif intent == "Kortsiktigt köpläge":
        match = c("SWING Score")
    elif intent == "Stabilare aktier":
        match = .55*c("Risk") + .30*c("Kvalitet") + .15*c("Värdering")
    else:
        match = c("Borsify Score")
    out["Match Score"] = pd.to_numeric(match, errors="coerce").reindex(out.index).fillna(0).round(1)
    return out.sort_values(["Match Score", "Datatäckning"], ascending=[False, False])


def intent_plain_text(intent: str) -> str:
    texts = {
        "Bästa möjligheter just nu": "En bred ranking av aktier som sammantaget ser mest intressanta ut enligt din valda Borsify-strategi.",
        "Bra långsiktig investering": "Prioriterar bolag som kombinerar kvalitet, rimlig värdering och risk för ett längre ägande.",
        "Utdelningsaktier": "Visar bara bolag med registrerad utdelning och prioriterar både direktavkastning och hur hållbar utdelningen verkar vara.",
        "Billiga kvalitetsbolag": "Letar efter en kombination av attraktiv värdering och starkare bolagskvalitet – inte bara lågt P/E.",
        "Aktier som fallit mycket": "Letar efter möjliga överreaktioner efter kursfall, men väger samtidigt in kvalitet och risk för att undvika rena fallande knivar.",
        "Kortsiktigt köpläge": "Prioriterar kursläge, trend och momentum för dagar till veckor. Det är mer timing än bolagsvärdering.",
        "Stabilare aktier": "Prioriterar högre riskbetyg och kvalitet. Stabilare betyder inte riskfritt – aktier kan alltid falla.",
    }
    return texts.get(intent, "")


def dividend_safety_label(row: pd.Series) -> tuple[str, str]:
    payout = _num(row.get("Utdelningsandel")); quality = _num(row.get("Kvalitet")); dy = _num(row.get("Direktavkastning"))
    if not np.isfinite(dy) or dy <= 0:
        return "Ingen registrerad utdelning", "Datakällan visar ingen positiv direktavkastning just nu."
    if not np.isfinite(payout):
        return "Oklar", "Utdelningsandelen saknas, så Borsify kan inte bedöma hur stor del av vinsten som delas ut."
    if payout > 1:
        return "Förhöjd risk", "Bolaget delar enligt aktuell data ut mer än hela vinsten. Det kan vara tillfälligt men bör kontrolleras."
    if payout > .80:
        return "Bevaka", "En stor del av vinsten delas ut. Det lämnar mindre marginal om vinsten försvagas."
    if .25 <= payout <= .75 and np.isfinite(quality) and quality >= 60:
        return "Ser rimlig ut", "Utdelningen tar en måttlig del av vinsten och bolagets kvalitetsbetyg är samtidigt relativt starkt."
    return "Neutral", "Utdelningen ser inte uppenbart ansträngd ut i de få mått Borsify har, men historiken behöver fortfarande kontrolleras."


def quality_at_fair_price_snapshot(row: pd.Series) -> tuple[float, list[str], list[str]]:
    """Current-snapshot quality/value check inspired by long-term quality-at-a-fair-price thinking.

    This deliberately does not pretend to measure multi-year durability because the current
    Yahoo snapshot does not provide point-in-time 5-10 year fundamentals in the screener.
    """
    quality = _num(row.get("Kvalitet")); valuation = _num(row.get("Värdering")); risk = _num(row.get("Risk"))
    roe = _num(row.get("ROE")); margin = _num(row.get("Vinstmarginal")); debt = _num(row.get("Skuld/eget kapital"))
    fcf = _num(row.get("FCF-yield")); growth = _num(row.get("Vinsttillväxt"))
    parts = [x for x in [quality, valuation, risk] if np.isfinite(x)]
    base = np.mean(parts) if parts else 50.0
    score = .45*(quality if np.isfinite(quality) else base) + .35*(valuation if np.isfinite(valuation) else base) + .20*(risk if np.isfinite(risk) else base)
    positives, cautions = [], []
    if np.isfinite(roe):
        (positives if roe >= .15 else cautions).append(f"ROE {fmt_pct(roe)}: " + ("bolaget använder ägarnas kapital effektivt i dagens data." if roe >= .15 else "lönsamheten är inte särskilt hög i dagens data."))
    if np.isfinite(margin):
        (positives if margin >= .10 else cautions).append(f"Vinstmarginal {fmt_pct(margin)}: " + ("en hygglig del av försäljningen blir vinst." if margin >= .10 else "marginalen är tunnare och ger mindre felmarginal."))
    if np.isfinite(debt):
        (positives if debt <= 100 else cautions).append(f"Skuld/eget kapital {debt:.0f}: " + ("skuldsättningen ser måttlig ut i den här grova kontrollen." if debt <= 100 else "skuldsättningen är högre och behöver granskas närmare."))
    if np.isfinite(fcf):
        (positives if fcf > .03 else cautions).append(f"Fritt kassaflöde/börsvärde {fmt_pct(fcf)}: " + ("bolaget genererar kontanter i förhållande till priset." if fcf > .03 else "kassaflödesavkastningen är låg eller svag just nu."))
    if np.isfinite(growth) and growth < 0:
        cautions.append(f"Vinsttillväxt {fmt_pct(growth)}: vinsten minskar enligt senaste tillgängliga uppgift.")
    return round(float(np.clip(score, 0, 100)), 1), positives[:4], cautions[:4]


def render_quality_at_fair_price(df: pd.DataFrame) -> None:
    if df.empty:
        return
    rows=[]
    for _, r in df.iterrows():
        score, positives, cautions = quality_at_fair_price_snapshot(r)
        rr=r.copy(); rr["QRP Score"]=score; rr["QRP Positives"]=positives; rr["QRP Cautions"]=cautions; rows.append(rr)
    q=pd.DataFrame(rows).sort_values(["QRP Score", "Datatäckning"], ascending=[False, False]).head(5)
    st.subheader("Kvalitet till rätt pris · långsiktig kontroll")
    st.caption("Inspirerad av principen att hellre leta efter bra bolag till rimliga priser än enbart billiga aktier. Detta är en nulägeskontroll – Borsify saknar ännu 5–10 års point-in-time fundamentahistorik för att bevisa uthålligheten.")
    for rank, (_, r) in enumerate(q.iterrows(), 1):
        with st.container(border=True):
            c1,c2,c3,c4=st.columns([2.7,1,1,1])
            c1.markdown(f"**{rank}. {_stock_identity(r)}**")
            c1.caption("Bra företag + rimligt pris + hanterbar risk väger tyngst i den här kontrollen.")
            c2.metric("Kvalitet/pris", f"{_num(r.get('QRP Score')):.0f}/100")
            c3.metric("Kvalitet", f"{_num(r.get('Kvalitet')):.0f}/100")
            c4.metric("Värdering", f"{_num(r.get('Värdering')):.0f}/100")
            pos=r.get("QRP Positives") or []; caut=r.get("QRP Cautions") or []
            if pos: st.write("**Det som talar för:** " + " ".join(pos))
            if caut: st.write("**Det som behöver kollas:** " + " ".join(caut))
            qrp = _num(r.get("QRP Score"))
            if qrp >= 75:
                st.success("Enkelt förklarat: bolaget ser just nu ut att kombinera god kvalitet med ett ganska rimligt pris. Det är värt en djupare kontroll, inte ett automatiskt köp.")
            elif qrp >= 60:
                st.info("Enkelt förklarat: flera delar ser bra ut, men pris, kvalitet eller risk är inte tillräckligt starka för ett tydligt grönt ljus ännu.")
            else:
                st.warning("Enkelt förklarat: Borsify ser för många frågetecken i pris, kvalitet eller risk för att kalla detta ett starkt långsiktigt fynd just nu.")


@st.cache_data(ttl=900, show_spinner=False)
def fetch_idea_flow_cached() -> tuple[pd.DataFrame, list[str]]:
    return fetch_public_idea_flow()


def render_idea_flow(scored: pd.DataFrame) -> None:
    st.subheader("Idéflöde · vad pratas det om just nu?")
    st.caption("Borsify använder media och forum för att hitta uppslag – aldrig som bevis för att en aktie är bra. Varje matchad aktie måste därefter klara kontrollen av pris, kvalitet, risk och övriga nyckeltal.")
    st.info("Många omnämnanden kan göra ett uppslag lättare att upptäcka, men de höjer **inte** Borsify Score. Forum väger dessutom lägre än ekonomimedia i själva upptäcktsstyrkan.")

    f1, f2 = st.columns([1.2, 2.2])
    with f1:
        fetch_clicked = st.button("Hämta senaste uppslag", key="idea_flow_fetch", type="primary", use_container_width=True)
    with f2:
        flow_filter = st.radio("Visa", ["Alla", "Ekonomimedia", "Forum"], horizontal=True, key="idea_flow_kind_filter")

    if fetch_clicked:
        with st.spinner("Hämtar publika rubriker och foruminlägg…"):
            feed, errors = fetch_idea_flow_cached()
            st.session_state["idea_flow_feed"] = feed
            st.session_state["idea_flow_errors"] = errors

    feed = st.session_state.get("idea_flow_feed")
    errors = st.session_state.get("idea_flow_errors", [])
    if feed is None:
        st.write("Tryck på knappen. Borsify läser endast publika RSS/Atom-flöden och återger rubrik, källa och länk – inte hela artiklar.")
        with st.expander("Vilka typer av källor bevakas?"):
            st.write("Ekonomimedia: EFN direkt RSS samt svenska ekonomimedier via Google News, inklusive flöden för breda börsnyheter, analyser/riktkurser och bolagshändelser. Forum: Reddit Aktiemarknaden och ISKbets. ISKbets behandlas uttryckligen som en mer spekulativ idékälla.")
        return

    if errors:
        with st.expander(f"{len(errors)} källa/källor kunde inte läsas"):
            st.write("Övriga källor används ändå. Felet kan vara tillfälligt eller bero på att en publik feed ändrats.")
            for e in errors:
                st.write(f"• {e}")
    if feed.empty:
        st.warning("Inga externa rubriker kunde hämtas just nu.")
        return

    view_feed = feed.copy()
    if flow_filter == "Ekonomimedia":
        view_feed = view_feed[view_feed["kind"] == "media"]
    elif flow_filter == "Forum":
        view_feed = view_feed[view_feed["kind"] == "forum"]

    mentions = map_mentions(view_feed, scored)
    ideas = build_verified_ideas(mentions, scored)
    media_items = int((feed["kind"] == "media").sum())
    forum_items = int((feed["kind"] == "forum").sum())
    publishers = int(feed.get("publisher", feed["source"]).astype(str).nunique())
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Uppslag hämtade", len(feed))
    m2.metric("Ekonomimedia", media_items)
    m3.metric("Forum", forum_items)
    m4.metric("Olika källor", publishers)

    if ideas.empty:
        st.info("Uppslag hämtades, men inget bolag kunde matchas säkert mot aktierna i ditt nuvarande universum med valt källfilter.")
        return

    passed = int((ideas.get("Borsify-granskning", pd.Series(dtype=str)) == "Klarar första kontrollen").sum())
    combo_series = ideas.get("Kombinationssignal", pd.Series(dtype=str)).astype(str)
    strong_combos = int(combo_series.isin(["Ovanligt intressant kombination", "Kvalitetsbolag i fokus", "Möjlig återhämtningsidé", "Kortsiktigt läge i fokus"]).sum())
    st.caption(f"{len(ideas)} aktier matchades · {passed} klarar Borsifys första kontroll · {strong_combos} har en tydlig kombination av extern uppmärksamhet och Borsify-data. Upptäcktsstyrka betyder hur brett och nyligen aktien nämnts – inte förväntad avkastning.")

    if strong_combos:
        st.markdown("### Kombinationer värda att läsa först")
        st.write("Här lyfts bara aktier där ett externt uppslag sammanfaller med något som redan syns i Borsifys egna siffror. Media eller forum får fortfarande **inte** höja Borsify Score.")
        combo_view = ideas[combo_series.isin(["Ovanligt intressant kombination", "Kvalitetsbolag i fokus", "Möjlig återhämtningsidé", "Kortsiktigt läge i fokus"])].head(5)
        for _, cr in combo_view.iterrows():
            with st.container(border=True):
                cc1, cc2 = st.columns([3.5, 1])
                cc1.markdown(f"**{_stock_identity(cr)}**")
                cc1.write(f"**{cr.get('Kombinationssignal','')}** — {cr.get('Kombinationsförklaring','')}")
                event = str(cr.get("Huvudhändelse", "Övrigt / oklart"))
                cc1.caption(f"Varför aktien syns just nu: **{event}**")
                impact = str(cr.get("Case Impact", "Oklart om caset förändrats"))
                cc1.caption(f"Påverkan på caset: **{impact}**")
                prio = _num(cr.get('Idéprioritet'))
                cc2.metric("Läs först", f"{prio:.0f}/100" if np.isfinite(prio) else "—")
        st.caption("Läs först är endast en kö-prioritering för externa uppslag: 72 % Borsify Score + 28 % upptäcktsstyrka. Den är inte en ny investeringsscore eller avkastningsprognos.")

    st.markdown("### Alla matchade uppslag")
    for _, r in ideas.head(12).iterrows():
        status = str(r.get("Borsify-granskning", ""))
        with st.container(border=True):
            a, b, c = st.columns([3.2, 1, 1.25])
            a.markdown(f"### {_stock_identity(r)}")
            media_sources = int(r.get("Mediekällor", 0) or 0)
            forum_sources = int(r.get("Forumkällor", 0) or 0)
            pulse = str(r.get("Mediepuls", ""))
            recent24 = int(r.get("Omnämnanden 24h", 0) or 0)
            pulse_text = f" · {pulse}" if pulse else ""
            a.caption(f"{int(r.get('Antal omnämnanden',0))} uppslag · {recent24} senaste 24 h · {media_sources} mediekälla/källor · {forum_sources} forumkälla/källor{pulse_text}")
            b.metric("Borsify", f"{_num(r.get('Borsify Score')):.0f}/100" if np.isfinite(_num(r.get('Borsify Score'))) else "—")
            c.metric("Kontroll", status)
            st.write(str(r.get("Förklaring", "")))
            event_label = str(r.get("Huvudhändelse", "Övrigt / oklart"))
            event_expl = str(r.get("Händelseförklaring", ""))
            st.markdown(f"**Varför uppmärksammas aktien?** {event_label}")
            if event_expl:
                st.caption(event_expl)
            impact_label = str(r.get("Case Impact", "Oklart om caset förändrats"))
            impact_expl = str(r.get("Case Impact Förklaring", ""))
            impact_level_num = _num(r.get("Case Impact Nivå", 0))
            impact_level = int(impact_level_num) if np.isfinite(impact_level_num) else 0
            if impact_level >= 3 and "risk" in impact_label.lower():
                st.warning(f"**Ändrar detta investeringscaset? {impact_label}.** {impact_expl}")
            elif impact_level >= 3:
                st.info(f"**Ändrar detta investeringscaset? {impact_label}.** {impact_expl}")
            else:
                st.caption(f"**Ändrar detta investeringscaset? {impact_label}.** {impact_expl}")
            combo_label = str(r.get("Kombinationssignal", ""))
            combo_expl = str(r.get("Kombinationsförklaring", ""))
            if combo_label and combo_label != "Ingen särskild kombination":
                st.success(f"**{combo_label}:** {combo_expl}")
            else:
                st.caption(combo_expl)
            st.caption(f"Upptäcktsstyrka {_num(r.get('Upptäcktsstyrka')):.0f}/100 · mäter bara hur tydligt uppslaget syns i externa källor.")
            flags = str(r.get("Riskflaggor", ""))
            if flags and flags not in {"—", "nan"}:
                st.caption(f"Riskflaggor: {flags}")
            headlines = r.get("Rubriker") or []
            if headlines:
                with st.expander("Visa rubrikerna bakom uppslaget"):
                    for h in headlines:
                        title = str(h.get("title", "")).replace("[", "(").replace("]", ")")
                        link = str(h.get("link", ""))
                        source = str(h.get("source", ""))
                        category = str(h.get("category", ""))
                        event_types = h.get("event_types") or []
                        event_text = " / ".join(str(x) for x in event_types[:2])
                        label = f"{source} · {category}" if category else source
                        if event_text:
                            label += f" · {event_text}"
                        if link.startswith("http"):
                            st.markdown(f"- [{title}]({link}) · {label}")
                        else:
                            st.write(f"• {title} · {label}")

    with st.expander("Så ska mediabevakningen tolkas"):
        st.write("Borsify försöker hitta **uppslag**, inte följa flocken. Mediepuls visar om uppmärksamheten har ökat det senaste dygnet jämfört med den senaste veckan. Det är inte ett köp- eller säljsentiment. Flera oberoende mediekällor ger högre upptäcktsstyrka än många inlägg från ett enda forum. Ett bolag kan ändå sorteras bort direkt om nyckeltalen är svaga. Spekulativa forumkällor får lägre vikt och kan aldrig ensamma ge maximal upptäcktsstyrka.")
        st.write("**Kombinationssignal** betyder bara att två separata saker råkar sammanfalla: Borsifys egen analys ser något intressant och externa källor har samtidigt börjat uppmärksamma bolaget. Det gör aktien värd att läsa om tidigare i kön, men det är fortfarande ingen köpsignal.")
        st.write("**Varför uppmärksammas aktien?** Borsify klassificerar rubrikerna i enkla händelsetyper som rapport, prognos, riktkurs, insiderhandel, order, förvärv, utdelning, emission eller vinstvarning. Klassningen hjälper dig att förstå vad du ska läsa först – den avgör inte om nyheten är positiv eller negativ.")
        st.write("**Ändrar detta investeringscaset?** Case Impact skiljer händelser som kan ändra bolagets vinst, risk eller finansiering från sådant som främst är åsikter eller marknadsbrus. När rubriken inte räcker för att avgöra riktningen säger Borsify uttryckligen att informationen måste verifieras i originalkällan.")
        st.caption("Bevakningen bygger på publika flöden. Paywall-innehåll läses inte och rubrikklassningen är en första sortering, inte ett verifierat faktapåstående om bolaget. Läs originalkällan innan du drar slutsatser.")


def render_dividend_discovery(df: pd.DataFrame) -> None:
    if df.empty: return
    div = apply_discovery_intent(df, "Utdelningsaktier").head(5)
    if div.empty: return
    st.subheader("Utdelningsläge · topp 5")
    st.caption("Hög direktavkastning är inte automatiskt bra. Borsify väger även in utdelningsandel, kvalitet och risk.")
    for rank, (_, r) in enumerate(div.iterrows(), 1):
        dy = _num(r.get("Direktavkastning")); payout = _num(r.get("Utdelningsandel")); label, why = dividend_safety_label(r)
        with st.container(border=True):
            a,b,c,d = st.columns([2.5,1,1,1.2])
            a.markdown(f"**{rank}. {_stock_identity(r)}**")
            a.caption(why)
            b.metric("Direktavkastning", fmt_pct(dy))
            annual = dy*10000 if np.isfinite(dy) else np.nan
            c.metric("På 10 000 kr/år*", f"{annual:,.0f} kr".replace(",", " ") if np.isfinite(annual) else "—")
            d.metric("Utdelning", label)
            st.caption(f"Utdelningsandel: {fmt_pct(payout)} · *ungefärligt belopp före skatt om utdelningen ligger kvar och kurs/utdelning motsvarar dagens uppgifter.")

def _download_close_series(frame: pd.DataFrame, ticker: str = "^OMXS30") -> pd.Series:
    if frame is None or frame.empty:
        return pd.Series(dtype=float)
    data = frame.copy()
    if isinstance(data.columns, pd.MultiIndex):
        level0 = set(map(str, data.columns.get_level_values(0)))
        level1 = set(map(str, data.columns.get_level_values(1)))
        try:
            if ticker in level0:
                data = data[ticker]
            elif ticker in level1:
                data = data.xs(ticker, axis=1, level=1, drop_level=True)
        except Exception:
            return pd.Series(dtype=float)
    if "Close" not in data.columns:
        return pd.Series(dtype=float)
    close = pd.to_numeric(data["Close"], errors="coerce").dropna()
    close.index = pd.to_datetime(close.index).tz_localize(None) if getattr(pd.to_datetime(close.index), "tz", None) is not None else pd.to_datetime(close.index)
    return close.sort_index()


def _performance_stats(index_series: pd.Series) -> dict[str, float]:
    s = pd.to_numeric(index_series, errors="coerce").dropna()
    if len(s) < 2 or _num(s.iloc[0]) <= 0:
        return {"return": np.nan, "cagr": np.nan, "volatility": np.nan, "sharpe": np.nan, "max_drawdown": np.nan}
    total = _num(s.iloc[-1] / s.iloc[0] - 1)
    days = max((pd.Timestamp(s.index[-1]) - pd.Timestamp(s.index[0])).days, 1)
    cagr = (s.iloc[-1] / s.iloc[0]) ** (365.25 / days) - 1 if s.iloc[-1] > 0 else np.nan
    rets = s.pct_change().dropna()
    vol = _num(rets.std(ddof=1) * np.sqrt(252)) if len(rets) >= 2 else np.nan
    sharpe = _num(rets.mean() / rets.std(ddof=1) * np.sqrt(252)) if len(rets) >= 2 and _num(rets.std(ddof=1)) > 0 else np.nan
    dd = s / s.cummax() - 1
    return {"return": total, "cagr": _num(cagr), "volatility": vol, "sharpe": sharpe, "max_drawdown": _num(dd.min())}


def parse_symbols(text: str) -> list[str]:
    symbols = []
    for item in text.replace(";", ",").replace("\n", ",").split(","):
        s = item.strip().upper()
        if not s: continue
        if "." not in s and "-" not in s: s += ".ST"
        symbols.append(s)
    return list(dict.fromkeys(symbols))


def dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    cols = ["Ticker", "Namn", "Sektor", "Match Score", "Borsify Score", "Signal", "Pris", "Prisdatum", "Dagsförändring", "P/E", "Direktavkastning", "52v från topp", "RSI14", "Värdering", "Kvalitet", "Marknadsläge", "Risk", "Riskflaggor", "Varför"]
    display = df[[c for c in cols if c in df.columns]].copy()
    for col in ["Dagsförändring", "Direktavkastning", "52v från topp"]:
        if col in display: display[col] = pd.to_numeric(display[col], errors="coerce") * 100
    return display



def render_discovery_shortlist(df: pd.DataFrame, intent: str, horizon: str = "Alla tidshorisonter") -> None:
    st.subheader("Bäst för dina val")
    st.caption("Borsify visar de starkaste matchningarna först.")
    picks = df.head(5)
    if picks.empty:
        st.info("Inga aktier matchar din sökning tillsammans med de övriga filtren.")
        return
    for rank, (_, r) in enumerate(picks.iterrows(), 1):
        with st.container(border=True):
            a, b, c = st.columns([3.3, 1.0, 1.15])
            a.markdown(f"**{rank}. {_stock_identity(r)}**")
            match_value = _num(r.get("Sökpoäng" if horizon != "Alla tidshorisonter" else "Match Score"))
            b.metric("Match", f"{match_value:.0f}/100" if np.isfinite(match_value) else "—")
            c.metric("Borsify", f"{_num(r.get('Borsify Score')):.0f}/100")

            price_sek = _num(r.get("Pris SEK"))
            original_price = _num(r.get("Pris")); ccy = str(r.get("Valuta") or "")
            if np.isfinite(price_sek):
                price_line = f"**Pris:** cirka {price_sek:,.0f} SEK".replace(",", " ")
                if np.isfinite(original_price) and ccy and ccy != "SEK":
                    price_line += f" · {original_price:.2f} {ccy}"
                st.markdown(price_line)
            else:
                render_recommendation_price(r)

            x, y = st.columns(2)
            with x:
                st.markdown("**Varför den passar**")
                st.write(intent_match_reason(r, intent))
                st.write(horizon_match_reason(r, horizon))
                st.caption(" · ".join(requirement_statuses(r, horizon)))
            with y:
                st.markdown("**Viktigaste risk**")
                st.write(main_risk_text(r))
                st.caption(f"Data: {data_status_text(r)}")

            with st.expander("Visa mer om matchningen", expanded=False):
                st.write(str(r.get("Varför", "Borsify har rankat aktien högt utifrån dina val.")))
                st.caption("Placeringen visar hur bra aktien passar dina val – inte hur säkert ett köp är.")

    if len(df) > len(picks):
        near = df.iloc[len(picks)]
        with st.expander("Varför fick en annan aktie inte plats?", expanded=False):
            st.markdown(f"**{_stock_identity(near)}**")
            st.write(near_miss_reason(near, intent, horizon))
            st.caption("Den passade dina val sämre just nu.")

def investment_analysis_text(row: pd.Series, horizon: str = "INVEST") -> str:
    """Grounded explanation in plain Swedish for users without finance background."""
    name = str(row.get("Namn") or row.get("Ticker") or "Aktien")
    score_col = {"INVEST": "INVEST Score", "SWING": "SWING Score", "REVERSAL": "REVERSAL Score"}.get(horizon, "INVEST Score")
    score = _num(row.get(score_col)); val = _num(row.get("Värdering")); qual = _num(row.get("Kvalitet"))
    pe = _num(row.get("P/E")); roe = _num(row.get("ROE")); growth = _num(row.get("Vinsttillväxt")); m3 = _num(row.get("3 mån")); rsi = _num(row.get("RSI14")); vol = _num(row.get("Volymkvot")); draw = _num(row.get("52v från topp")); daily = _num(row.get("Dagsförändring")); dist = _num(row.get("Avstånd SMA200")); dy = _num(row.get("Direktavkastning"))
    flags = str(row.get("Riskflaggor", "—"))
    intro = f"{name} får {score:.0f}/100" if np.isfinite(score) else name
    if horizon == "INVEST":
        parts = [f"{intro} för långsiktigt ägande."]
        if np.isfinite(val) and val >= 65: parts.append("Priset ser relativt rimligt ut jämfört med liknande bolag.")
        if np.isfinite(qual) and qual >= 65: parts.append("Bolagets lönsamhet, tillväxt och ekonomi ser sammantaget starka ut i modellen.")
        if np.isfinite(pe): parts.append(f"P/E är {pe:.1f}; det betyder förenklat att marknaden betalar cirka {pe:.1f} gånger ett års nuvarande vinst.")
        if np.isfinite(roe): parts.append(f"ROE är {roe:.1%}; det visar hur effektivt bolaget använder ägarnas kapital.")
        if np.isfinite(growth): parts.append(f"Den registrerade vinsttillväxten är {growth:+.1%}.")
        if np.isfinite(dy) and dy > 0: parts.append(f"Direktavkastningen är cirka {dy:.1%}, alltså ungefär {dy*100:.1f} kr i årlig utdelning per 100 kr investerat om utdelningen ligger kvar.")
    elif horizon == "SWING":
        parts = [f"{intro} för ett kortare kursläge på dagar till veckor."]
        if np.isfinite(dist): parts.append("Kursen ligger över sitt 200-dagarssnitt, vilket brukar ses som en starkare lång trend." if dist >= 0 else "Kursen ligger under sitt 200-dagarssnitt, vilket betyder att den längre trenden är svagare.")
        if np.isfinite(m3): parts.append(f"På tre månader har kursen rört sig {m3:+.1%}.")
        if np.isfinite(rsi): parts.append(f"RSI är {rsi:.0f}; det är ett temperaturmått på den senaste kursrörelsen, där lägre nivåer ofta betyder att aktien pressats ned.")
        if np.isfinite(vol): parts.append(f"Handelsvolymen är {vol:.1f} gånger normalnivån för de senaste 20 dagarna.")
    else:
        parts = [f"{intro} som möjlig återhämtning efter en nedgång."]
        if np.isfinite(daily): parts.append(f"Aktien har rört sig {daily:+.1%} idag.")
        if np.isfinite(draw): parts.append(f"Den ligger cirka {abs(draw):.1%} under sin högsta nivå det senaste året.")
        if np.isfinite(rsi): parts.append(f"RSI är {rsi:.0f}; ett lågt värde kan betyda att säljtrycket varit ovanligt stort, men det garanterar inte en uppgång.")
        if np.isfinite(qual): parts.append(f"Bolagets kvalitetsbetyg är {qual:.0f}/100, vilket hjälper modellen att skilja en möjlig överreaktion från ett bolag med tydliga grundproblem.")
    if flags == "—":
        parts.append("Modellen hittar inga av sina grövre riskflaggor just nu.")
    else:
        parts.append(f"Det viktigaste att vara försiktig med är: {flags}.")
    parts.append("Se detta som en förklaring till varför aktien hamnat högt i Borsify – inte som ett löfte om att kursen kommer stiga.")
    return " ".join(parts)


def render_engine_board(df: pd.DataFrame) -> None:
    st.subheader("Olika sätt att hitta köplägen")
    st.caption("Välj tidsperspektiv. Borsify letar på olika sätt beroende på hur länge du tänker äga aktien.")
    specs=[("INVEST", "INVEST Score", "Lång sikt · ca 1–5 år"), ("SWING", "SWING Score", "Kort sikt · ca 2 dagar–8 veckor"), ("REVERSAL", "REVERSAL Score", "Överreaktion · dagar–månader") ]
    cols=st.columns(3)
    for col,(label,score_col,horizon) in zip(cols,specs):
        with col:
            st.markdown(f"### {label}")
            st.caption(horizon)
            top=df.sort_values([score_col,"Datatäckning"], ascending=[False,False]).head(3)
            for rank,(_,r) in enumerate(top.iterrows(),1):
                with st.container(border=True):
                    st.markdown(f"**{rank}. {r['Namn']} · {r['Ticker']}**")
                    e1, e2 = st.columns(2)
                    e1.metric(label, f"{_num(r[score_col]):.0f}/100")
                    price = _num(r.get("Pris"))
                    price_text = fmt_price_with_sek(r)
                    e2.metric("Aktuell kurs", price_text, fmt_pct(r.get("Dagsförändring")))
                    st.caption(f"Senaste kursdag: {r.get('Prisdatum', '—')}")
                    st.write(investment_analysis_text(r,label))


def render_detail(row: pd.Series, profile: str, key_prefix: str = "detail", horizon: str = "long", rank: int = 0) -> None:
    st.subheader(f"{row['Namn']} · {row['Ticker']}")
    _company_axis = assess_company_quality(row)
    _entry_axis = assess_entry_timing(row, horizon)
    _ca, _ea = st.columns(2)
    _ca.markdown(f"**Bra bolag?** {_company_axis['Bolagsbedömning']}")
    _ca.caption(_company_axis['Bolagsbedömning skäl'])
    _ea.markdown(f"**Bra köpläge?** {_entry_axis['Ingångsläge']}")
    _ea.caption(_entry_axis['Ingångsläge skäl'] + (f" · Vänta på: {_entry_axis['Vänta på']}" if _entry_axis['Vänta på'] != 'ingen tydlig väntesignal' else ''))
    if str(_entry_axis.get("Bättre ingång", "—")) != "—":
        _currency = str(row.get("Valuta", "") or "")
        _ea.info(
            f"**Bättre ingångszon:** {_entry_axis['Bättre ingång']} {_currency}".strip()
            + f"\n\n{_entry_axis.get('Bättre ingång skäl', '')}"
        )
    _deal = assess_good_deal({**dict(row), **_company_axis, **_entry_axis}, horizon)
    st.markdown(f"### {_deal['Affärsläge']}")
    st.caption(_deal["Affärsläge förklaring"])
    _conv = assess_deal_conviction(row, "long")
    st.markdown(f"### {_conv['Deal Conviction']}")
    st.caption(f"Score {_conv['Deal Conviction Score']:.0f}/100 · {_conv['Deal Conviction förklaring']}")
    _bmi = assess_business_management_intelligence(row)
    _failure = assess_failure_transparency(row)
    st.markdown("### Data Trust & Failure Transparency")
    st.write(_failure["Data Failure status"])
    st.caption(_failure["Data Failure förklaring"] or "Inga kända dataproblem registrerade.")
    _aconf = assess_analysis_confidence({**row.to_dict(), **_failure})
    st.markdown(f"### {_aconf['Analysis Confidence']}")
    st.caption(f"{_aconf['Analysis Confidence Score']:.0f}/100 · {_aconf['Analysis Confidence förklaring']}")
    _decision = assess_confidence_adjusted_decision({**row.to_dict(), **_failure, **_aconf, **_conv})
    st.markdown(f"### {_decision['Decision Support']}")
    st.caption(_decision["Decision Support förklaring"])
    st.markdown("### Verksamhet & ledning")
    st.write({
        "Bolagstyp": _bmi["Business profile"],
        "Viktigaste KPI:er att följa": _bmi["Business key KPIs"],
        "KPI-underlag": _bmi["Business KPI coverage"],
        "Management execution": _bmi["Management execution"],
    })
    if _bmi["Business KPI gaps"]:
        st.caption("Datagap: " + _bmi["Business KPI gaps"])
    st.caption(_bmi["Management execution förklaring"])
    _kpiinf = assess_kpi_inflection({**row.to_dict(), **_bmi})
    st.markdown(f"#### {_kpiinf['KPI Inflection']}")
    st.caption(_kpiinf["KPI Inflection förklaring"])
    if row.get("Inflection Sequence"):
        st.markdown("#### Inflection Sequence")
        st.write(row.get("Inflection Sequence"))
        st.caption(str(row.get("Inflection Sequence förklaring") or ""))
    if row.get("False Start status"):
        st.markdown("#### False Start / Confirmation")
        st.write(row.get("False Start status"))
        st.caption(str(row.get("False Start förklaring") or ""))
    _current_promises = pd.DataFrame(parse_explicit_guidance(row.get("Report Delta guidance"), row.get("Rapportminne rapportdatum"), str(row.get("Ticker") or "")))
    _promise_eval = assess_promise_delivery(_current_promises)
    st.markdown("#### Management Promise vs Delivery")
    st.write(_promise_eval["Management promise status"])
    st.caption(_promise_eval["Management promise förklaring"] + " Full träffsäkerhet byggs prospektivt från frysta guidance-punkter; äldre löften backfillas inte.")
    _sale = assess_negative_overreaction(row)
    if _sale.get("Negativ överreaktion nivå", 0) != 0:
        st.markdown(f"### {_sale['Negativ överreaktion']}")
        st.caption(_sale["Negativ överreaktion förklaring"])
    _accel = assess_mispriced_acceleration({**dict(row), **_sale})
    if _accel.get("Mispriced acceleration nivå", 0) != 0:
        st.markdown(f"### {_accel['Mispriced acceleration']}")
        st.caption(_accel["Mispriced acceleration förklaring"])
    _hidden = assess_hidden_inflection(row)
    if _hidden.get("Hidden inflection nivå", 0) != 0:
        st.markdown(f"### {_hidden['Hidden inflection']}")
        st.caption(_hidden["Hidden inflection förklaring"])
    _compounder = assess_quality_compounder_ignored(row, horizon)
    if _compounder.get("Ignored compounder nivå", 0) != 0:
        st.markdown(f"### {_compounder['Ignored compounder']}")
        st.caption(_compounder["Ignored compounder förklaring"])
    _underfollowed_quality = assess_underfollowed_quality(row, horizon)
    if _underfollowed_quality.get("Underfollowed Quality nivå", 0) != 0:
        st.markdown(f"### {_underfollowed_quality['Underfollowed Quality']}")
        st.caption(_underfollowed_quality["Underfollowed Quality förklaring"])
    _earnings_power = assess_earnings_power_noise(row, horizon)
    if _earnings_power.get("Earnings power noise nivå", 0) != 0:
        st.markdown(f"### {_earnings_power['Earnings power noise']}")
        st.caption(_earnings_power["Earnings power förklaring"])
    _operating_leverage = assess_operating_leverage_setup(row, horizon)
    if _operating_leverage.get("Operating leverage nivå", 0) != 0:
        st.markdown(f"### {_operating_leverage['Operating leverage']}")
        st.caption(_operating_leverage["Operating leverage förklaring"])
    _bs_opt = assess_balance_sheet_optionality(row, horizon)
    if _bs_opt.get("Balance-sheet optionality nivå", 0) != 0:
        st.markdown(f"### {_bs_opt['Balance-sheet optionality']}")
        st.caption(_bs_opt["Balance-sheet optionality förklaring"])
    _position = assess_position_entry({**dict(row), **_company_axis, **_entry_axis})
    st.markdown(f"### {_position['Positionsråd']}")
    st.caption(_position["Positionsråd skäl"])
    st.metric("Första storlek", _position["Första positionsstorlek"])
    st.caption(_position["Positionsstorlek skäl"] + " Storleken avser andel av din egen tänkta maxposition – inte andel av hela portföljen.")
    c1, c2, c3, c4, c5 = st.columns(5)
    prev = previous_score_snapshot(str(row["Ticker"]), profile)
    score_delta = None
    if prev and np.isfinite(_num(prev.get("score"))): score_delta = _num(row.get("Borsify Score")) - _num(prev.get("score"))
    c1.metric("Borsify Score", f"{row['Borsify Score']:.0f}/100", f"{score_delta:+.1f}" if score_delta is not None else None)
    c2.metric("Pris", fmt_price_with_sek(row), fmt_pct(row.get("Dagsförändring")))
    c3.metric("Värdering", f"{row['Värdering']:.0f}")
    st.markdown("### Varför är aktien intressant?")
    st.write(investment_analysis_text(row, "INVEST"))
    qrp_score, qrp_pos, qrp_cautions = quality_at_fair_price_snapshot(row)
    with st.expander("Är bolaget bra utan att aktien verkar för dyr?"):
        st.metric("Helhetsbedömning", f"{qrp_score:.0f}/100")
        st.write("Borsify kontrollerar om bolaget tjänar pengar, har rimlig ekonomi och om aktien verkar rimligt prissatt.")
        if qrp_pos: st.write("**Talar för:** " + " ".join(qrp_pos))
        if qrp_cautions: st.write("**Behöver kollas:** " + " ".join(qrp_cautions))
    _value_range_status = str(row.get("Fundamental Value Range status") or "")
    if _value_range_status:
        with st.expander("Fundamentalt värdeintervall · rådgivande", expanded=False):
            st.markdown(f"**{row.get('Fundamental Value Range', '❔ Kan inte bedömas')}**")
            st.write(str(row.get("Fundamental Value Range summary") or row.get("Fundamental Value Range reason") or "—"))
            if _value_range_status == "SUPPORTED":
                _vr_currency = str(row.get("Valuta") or "").strip()
                _vr_unit = f" {_vr_currency}" if _vr_currency else ""
                _vr1, _vr2, _vr3 = st.columns(3)
                _vr1.metric("Bear-range", f"{row.get('Fundamental Value Range bear low')}–{row.get('Fundamental Value Range bear high')}{_vr_unit}")
                _vr2.metric("Base-range", f"{row.get('Fundamental Value Range base low')}–{row.get('Fundamental Value Range base high')}{_vr_unit}")
                _vr3.metric("Bull-range", f"{row.get('Fundamental Value Range bull low')}–{row.get('Fundamental Value Range bull high')}{_vr_unit}")
                st.caption(str(row.get("Fundamental Value Range assumptions") or ""))
            _vr_warning = str(row.get("Fundamental Value Range warnings") or "").strip()
            if _vr_warning:
                st.warning(_vr_warning)
            st.caption("Påverkar inte Borsify Score eller huvudrankingen. Intervallen är scenarios, inte riktkurser eller sannolikheter.")
    render_beginner_glossary(f"{key_prefix}_terms")
    e1, e2, e3 = st.columns(3)
    e1.metric("INVEST", f"{_num(row.get('INVEST Score')):.0f}/100")
    e2.metric("SWING", f"{_num(row.get('SWING Score')):.0f}/100")
    e3.metric("REVERSAL", f"{_num(row.get('REVERSAL Score')):.0f}/100")
    with st.expander("Visa andra tidsperspektiv"):
        st.markdown("**SWING · dagar–veckor**")
        st.write(investment_analysis_text(row, "SWING"))
        st.markdown("**REVERSAL · möjlig överreaktion**")
        st.write(investment_analysis_text(row, "REVERSAL"))
    c4.metric("Kvalitet", f"{row['Kvalitet']:.0f}")
    c5.metric("Risk", f"{row['Risk']:.0f}")
    st.markdown(f"**Bedömning:** {row['Signal']}  \n**Kort förklaring:** {row['Varför']}  \n**Riskflaggor:** {row['Riskflaggor']}")

    factor_df, strengths, weaknesses = _score_explanation(row, profile)
    with st.expander("Visa hur Borsify räknat", expanded=False):
        st.markdown("#### Så räknar Borsify")
        st.caption("Detaljer för dig som vill gå djupare.")
    st.dataframe(
        factor_df, use_container_width=True, hide_index=True,
        column_config={
            "Score": st.column_config.ProgressColumn("Score", min_value=0, max_value=100, format="%.0f"),
            "Vikt %": st.column_config.NumberColumn("Vikt", format="%.0f%%"),
            "Viktade poäng": st.column_config.NumberColumn("Viktade poäng", format="%.1f"),
            "Påverkan mot neutral": st.column_config.NumberColumn("Påverkan vs neutral", format="%+.1f"),
        },
    )
    base_score = float(pd.to_numeric(factor_df["Viktade poäng"], errors="coerce").sum())
    coverage_for_calc = _num(row.get("Datatäckning"))
    coverage_factor = .80 + .20 * coverage_for_calc if np.isfinite(coverage_for_calc) else .80
    calc_final = base_score * coverage_factor
    q1, q2, q3 = st.columns(3)
    q1.metric("Viktad grundscore", f"{base_score:.1f}")
    q2.metric("Datatäckningsfaktor", f"{coverage_factor:.3f}")
    q3.metric("Beräknad slutscore", f"{calc_final:.1f}")
    st.caption("Saknad data gör Borsify mer försiktigt.")
    sx, wx = st.columns(2)
    with sx:
        st.markdown("**Styrkor modellen ser**")
        if strengths:
            for item in strengths: st.markdown(f"- {item}")
        else: st.caption("Inga tydliga styrkor sticker ut i tillgänglig data.")
    with wx:
        st.markdown("**Svagheter / det som drar ned**")
        if weaknesses:
            for item in weaknesses: st.markdown(f"- {item}")
        else: st.caption("Inga tydliga svagheter sticker ut i tillgänglig data.")

    if prev:
        component_map = [("Värdering","valuation"),("Kvalitet","quality"),("Marknadsläge","setup"),("Utdelning","income"),("Risk","risk")]
        changes=[]
        for label,key in component_map:
            old=_num(prev.get(key)); cur=_num(row.get(label))
            if np.isfinite(old) and np.isfinite(cur): changes.append((label,cur-old,old,cur))
        if changes:
            changes.sort(key=lambda x: abs(x[1]), reverse=True)
            st.markdown("#### Vad har ändrats sedan föregående registrerade dag?")
            st.caption(f"Jämförelse mot {prev.get('captured_date','föregående snapshot')}. Historiken sparas för bevakade aktier.")
            cols=st.columns(min(3,len(changes)))
            for i,(label,delta,old,cur) in enumerate(changes[:3]):
                cols[i].metric(label, f"{cur:.0f}", f"{delta:+.1f}")
    elif is_watched(str(row["Ticker"])):
        st.info("Förändringsförklaringen visas när det finns minst en tidigare dagsnapshot för den här bevakade aktien.")

    coverage=_num(row.get("Datatäckning"))
    if np.isfinite(coverage):
        if coverage < .60: st.warning(f"Underlaget är bara {coverage:.0%} komplett. Flera viktiga bolagsuppgifter saknas, så Borsifys betyg är mer osäkert än vanligt.")
        else: st.caption(f"Datatäckning i kärnmodellen: {coverage:.0%}.")
    price_date = str(row.get("Prisdatum") or "—")
    fundamental_at = str(row.get("Fundamental hämtad") or "—")
    st.caption(f"Data: kurs {price_date} · bolagsdata hämtad {fundamental_at}")

    watched = is_watched(str(row["Ticker"]))
    if st.button("Ta bort från bevakning" if watched else "Lägg till i bevakning", key=f"{key_prefix}_watch_{row['Ticker']}"):
        toggle_watchlist(str(row["Ticker"])); st.rerun()
    hist = row.get("_history")
    if isinstance(hist, pd.DataFrame) and not hist.empty:
        chart = hist[["Close"]].copy(); chart["SMA50"] = chart["Close"].rolling(50).mean(); chart["SMA200"] = chart["Close"].rolling(200).mean()
        st.line_chart(chart, height=320)
    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown("#### Värdering"); st.write({"P/E": fmt_num(row.get("P/E")), "Forward P/E": fmt_num(row.get("Forward P/E")), "P/B": fmt_num(row.get("P/B")), "EV/EBITDA": fmt_num(row.get("EV/EBITDA")), "FCF-yield": fmt_pct(row.get("FCF-yield"))})
    with m2:
        st.markdown("#### Kvalitet"); st.write({"ROE": fmt_pct(row.get("ROE")), "Vinstmarginal": fmt_pct(row.get("Vinstmarginal")), "Omsättningstillväxt": fmt_pct(row.get("Omsättningstillväxt")), "Vinsttillväxt": fmt_pct(row.get("Vinsttillväxt")), "Skuld/eget kapital": fmt_num(row.get("Skuld/eget kapital"), 0)})
    with m3:
        st.markdown("#### Utdelning / setup"); st.write({"Direktavkastning": fmt_pct(row.get("Direktavkastning")), "Utdelningsandel": fmt_pct(row.get("Utdelningsandel")), "RSI14": fmt_num(row.get("RSI14"),0), "3 mån": fmt_pct(row.get("3 mån")), "52v från topp": fmt_pct(row.get("52v från topp"))})
    with st.expander("Rapportdatum och senaste nyheter", expanded=False):
        events = fetch_company_events(str(row["Ticker"]))
        e1, e2 = st.columns(2)
        e1.metric("Nästa rapport enligt Yahoo", _fmt_date(events.get("earnings")))
        e2.metric("Ex-dag enligt Yahoo", _fmt_date(events.get("ex_dividend")))
        news = events.get("news") or []
        if news:
            st.markdown("**Senaste rubriker**")
            for item in news:
                title = item.get("title", "Nyhet"); provider = item.get("provider", ""); link = item.get("link"); suffix = f" · {provider}" if provider else ""
                st.markdown(f"- [{title}]({link}){suffix}" if link else f"- {title}{suffix}")
        else: st.caption("Ingen nyhetsdata kunde hämtas just nu.")
        ni_status = str(row.get("News Impact Status") or "")
        if ni_status:
            st.markdown("**Nyhetspåverkan**")
            st.write(f"{ni_status} · {row.get('News Impact Summary', '—')}")
            reaction = _num(row.get("News Impact Primary Reaction"))
            drift = _num(row.get("News Impact Primary Drift"))
            if np.isfinite(reaction):
                st.caption(f"Initial close-to-close-reaktion: {reaction:+.1%}" + (f" · fortsatt rörelse ca 5 sessioner: {drift:+.1%}" if np.isfinite(drift) else ""))
            st.caption(str(row.get("News Impact Warning") or "Rubriker och kursrörelser visar samband, inte bevisad kausalitet."))
        nf_status = str(row.get("News Flow Status") or "")
        if nf_status:
            st.markdown("**Nyhetsflöde · senaste 30 dagarna**")
            st.write(f"{nf_status} · {row.get('News Flow Summary', '—')}")
            pos14 = int(_num(row.get("News Flow Positive 14d"))) if np.isfinite(_num(row.get("News Flow Positive 14d"))) else 0
            neg14 = int(_num(row.get("News Flow Negative 14d"))) if np.isfinite(_num(row.get("News Flow Negative 14d"))) else 0
            price_pattern = str(row.get("News Flow Price Pattern") or "—")
            st.caption(f"14 dagar: {pos14} tydligt positiva · {neg14} tydligt negativa · Kursmönster: {price_pattern}.")
            st.caption(str(row.get("News Flow Warning") or "Nyhetsserier visar samband, inte bevisad kausalitet."))
        ns_status = str(row.get("News Surprise Status") or "")
        if ns_status:
            st.markdown("**Nyhetsöverraskning & kursrespons**")
            st.write(f"{ns_status} · {row.get('News Surprise Summary', '—')}")
            ns_i = _num(row.get("News Surprise Immediate Reaction"))
            ns_5 = _num(row.get("News Surprise Five Day Reaction"))
            ns_ref = int(_num(row.get("News Surprise Reference N"))) if np.isfinite(_num(row.get("News Surprise Reference N"))) else 0
            details = []
            if np.isfinite(ns_i): details.append(f"direkt {ns_i:+.1%}")
            if np.isfinite(ns_5): details.append(f"ca 5 sessioner {ns_5:+.1%}")
            if ns_ref >= 2: details.append(f"jämförelse med {ns_ref} äldre liknande händelser")
            if details: st.caption(" · ".join(details))
            st.caption(str(row.get("News Surprise Warning") or "Överraskning är en rubrikproxy och kursrespons är inte kausalitetsbevis."))
        nem_status = str(row.get("News Event Memory Status") or "")
        if nem_status:
            st.markdown("**Nyhetsminne · samma bolag**")
            st.write(f"{nem_status} · {row.get('News Event Memory Summary', '—')}")
            nem_n = int(_num(row.get("News Event Memory N"))) if np.isfinite(_num(row.get("News Event Memory N"))) else 0
            nem_i = _num(row.get("News Event Memory Median Immediate"))
            nem_5 = _num(row.get("News Event Memory Median Five Day"))
            parts = [f"N={nem_n}"]
            if np.isfinite(nem_i): parts.append(f"historisk median direkt {nem_i:+.1%}")
            if np.isfinite(nem_5): parts.append(f"ca 5 sessioner {nem_5:+.1%}")
            st.caption(" · ".join(parts))
            st.caption(str(row.get("News Event Memory Warning") or "Historiken beskriver tidigare utfall och är inte en prognos."))
        st.caption("Kalender- och nyhetsdata kommer från Yahoo Finance och bör verifieras mot bolagets IR-sida.")
    st.link_button("Öppna hos Yahoo Finance", str(row["Yahoo"]))
    render_case_ai_qa(row, horizon, rank)


def render_quick_change_target(scored: pd.DataFrame, signal_history: pd.DataFrame, profile: str) -> None:
    """Inline destination for actions from Nytt sedan sist.

    Streamlit tabs cannot be switched reliably from a button, so the destination
    is rendered immediately on the overview instead of pretending navigation occurred.
    """
    ticker = str(st.session_state.get("bq_quick_open_ticker") or "").strip()
    mode = str(st.session_state.get("bq_quick_open_mode") or "").strip()
    if not ticker or not mode:
        return
    with st.container(border=True):
        h1, h2 = st.columns([5, 1])
        h1.markdown(f"### Öppnad från Nytt sedan sist · {ticker}")
        if h2.button("Stäng", key=f"quick_close_{ticker}_{mode}", use_container_width=True):
            st.session_state.pop("bq_quick_open_ticker", None)
            st.session_state.pop("bq_quick_open_mode", None)
            st.rerun()

        row_df = scored[scored["Ticker"].astype(str) == ticker].head(1) if not scored.empty else pd.DataFrame()
        if mode == "analysis":
            if row_df.empty:
                st.info("Aktien finns inte i den aktuella analyskörningen. Byt marknad/universum eller öppna den från bevakningslistan.")
            else:
                render_detail(row_df.iloc[0], profile, key_prefix=f"quick_{ticker}")
        elif mode == "journal":
            if row_df.empty:
                st.info("Case Journal kan visas när aktien finns i den aktuella analysen eller bevakningen.")
            else:
                wr = row_df.iloc[0]
                hist = get_score_history(ticker, profile)
                current_case = {
                    "score": _num(wr.get("Borsify Score")),
                    "valuation": _num(wr.get("Värdering")),
                    "quality": _num(wr.get("Kvalitet")),
                    "setup": _num(wr.get("Marknadsläge")),
                    "income": _num(wr.get("Utdelning")),
                    "risk": _num(wr.get("Risk")),
                    "coverage": _num(wr.get("Datatäckning")),
                }
                journal = assess_case_change(hist, current_case)
                st.markdown("**Case Journal · vad har förändrats?**")
                delta = _num(journal.get("score_delta"))
                delta_text = f"{delta:+.1f} poäng sedan start" if np.isfinite(delta) else "historiken byggs upp"
                st.write(f"**{journal.get('status', 'Historiken byggs upp')}** · {delta_text}")
                for change in journal.get("changes", []):
                    st.write(f"• {change}")
                jt = journal_table(hist)
                if len(jt) >= 2:
                    st.dataframe(jt, use_container_width=True, hide_index=True)
                else:
                    st.caption("Efter fler sparade analyser visas utvecklingen här.")
        elif mode == "signal":
            hist = signal_history[signal_history["symbol"].astype(str) == ticker].copy() if not signal_history.empty else pd.DataFrame()
            st.markdown("**Signalhistorik**")
            if hist.empty:
                st.info("Ingen sparad signalhistorik hittades för aktien.")
            else:
                for _, sig in hist.sort_values(["created_at"], ascending=False).head(12).iterrows():
                    read_label = "Läst" if bool(sig.get("is_read")) else "Oläst"
                    st.markdown(f"**{sig.get('kind','Signal')} · {sig.get('occurred_date','')} · {read_label}**")
                    st.write(str(sig.get("text") or ""))



def _market_label_for_ticker(symbol: str) -> str:
    s = str(symbol or "").upper()
    suffix_map = {
        ".ST": "Sverige", ".CO": "Danmark", ".OL": "Norge", ".HE": "Finland",
        ".DE": "Tyskland", ".L": "Storbritannien", ".TO": "Kanada", ".V": "Kanada",
        ".PA": "Frankrike", ".AS": "Nederländerna", ".BR": "Belgien",
        ".MI": "Italien", ".MC": "Spanien", ".SW": "Schweiz", ".LS": "Portugal",
    }
    for suffix, country in suffix_map.items():
        if s.endswith(suffix):
            return country
    return "USA"


def _country_flag(country: str) -> str:
    flags = {
        "Sverige": "🇸🇪", "Danmark": "🇩🇰", "Norge": "🇳🇴", "Finland": "🇫🇮",
        "Tyskland": "🇩🇪", "Storbritannien": "🇬🇧", "Kanada": "🇨🇦",
        "Frankrike": "🇫🇷", "Nederländerna": "🇳🇱", "Belgien": "🇧🇪",
        "Italien": "🇮🇹", "Spanien": "🇪🇸", "Schweiz": "🇨🇭",
        "Portugal": "🇵🇹", "USA": "🇺🇸",
    }
    return flags.get(str(country or ""), "🏳️")


def _stock_identity(row: pd.Series | dict[str, Any], include_name: bool = True) -> str:
    ticker = str(row.get("Ticker", "—") or "—").upper()
    country = _market_label_for_ticker(ticker)
    flag = _country_flag(country)
    name = str(row.get("Namn", ticker) or ticker)
    if include_name:
        return f"{flag} {name} · {ticker} · {country}"
    return f"{flag} {ticker} · {country}"


def render_horizon_toplists(scored: pd.DataFrame, market: str) -> None:
    st.markdown("## Borsifys bästa köp")
    st.caption("Bara köp som klarar Borsifys krav. Är inget tillräckligt bra lämnas listan tom.")
    avanza_catalog = load_avanza_universe(AVANZA_UNIVERSE_PATH)
    if not avanza_catalog.empty:
        summary = breadth_summary(avanza_catalog)
        catalog_audit = audit_catalog(AVANZA_UNIVERSE_PATH)
        catalog_q = catalog_integrity_summary(catalog_audit)
        with st.expander(f"Marknadstäckning · {summary['total']} aktier · {summary['countries']} länder", expanded=False):
            st.dataframe(coverage_table(avanza_catalog), use_container_width=True, hide_index=True)
            if catalog_q["excluded"]:
                st.warning(f"{catalog_q['excluded']} katalogposter stoppades före datahämtning på grund av lokala katalogfel.")
            else:
                st.caption(f"Katalogkontroll: {catalog_q['approved']} av {catalog_q['total']} poster klarar lokala format- och dubblettkontroller.")
            st.caption("Katalogkontrollen bevisar inte att aktien handlas eller att Yahoo-data är korrekt. Det verifieras först när marknadsdata hämtas. Kärna = kuraterat basurval. Bred = utökat kandidatuniversum.")
    if "Universe QC" in scored.columns:
        qsum = quality_summary(scored)
        with st.expander("✅ Kontroll av börsdata · denna körning", expanded=False):
            q1,q2,q3 = st.columns(3)
            q1.metric("Verifierade", qsum["verified"])
            q2.metric("Delvis verifierade", qsum["partial"])
            q3.metric("Hårt exkluderade", int(st.session_state.get("bq_qc_hard_rejected", 0)))
            country_q = scored.copy()
            country_q["Land"] = country_q["Ticker"].astype(str).map(_market_label_for_ticker)
            rows=[]
            for country,g in country_q.groupby("Land"):
                qs=quality_summary(g)
                rows.append({
                    "Land":country,
                    "Verifierade":qs["verified"],
                    "Delvis verifierade":qs["partial"],
                    "Analyserbara":qs["verified"]+qs["partial"],
                })
            if rows:
                st.dataframe(pd.DataFrame(rows).sort_values(["Analyserbara","Land"],ascending=[False,True]), use_container_width=True, hide_index=True)
            st.caption(
                "Den här kontrollen bedömer bara om Borsify har tillräckligt bra data för att jämföra aktien med andra. "
                "Den säger inte om aktien är ett bra köp. Aktier med trasig kursdata eller för kort historik tas bort automatiskt."
            )
    persistent_qc = get_universe_qc_states()
    if not persistent_qc.empty:
        psum = quarantine_summary(persistent_qc)
        with st.expander("🛡️ Datakontroll över tid · fel & karantän", expanded=False):
            p1,p2,p3,p4 = st.columns(4)
            p1.metric("Tickers med historik", psum["total"])
            p2.metric("I karantän", psum["quarantined"])
            p3.metric("Med felserie", psum["failing"])
            p4.metric("Hoppades över nu", int(st.session_state.get("bq_qc_skipped_quarantine", 0)))
            health_ratio = float(st.session_state.get("bq_qc_scan_health", 1.0))
            provider_ok = bool(st.session_state.get("bq_qc_provider_healthy", True))
            provider_rule = str(st.session_state.get("bq_qc_provider_rule", ""))
            st.caption(
                f"Senaste datahämtningen lyckades för {health_ratio:.0%} av aktierna. "
                + ("Tillräckligt många fungerade för att Borsify ska kunna bedöma enskilda fel."
                   if provider_ok else
                   "Så få aktier fungerade att Borsify misstänker problem hos datakällan. Saknade aktier får därför ingen felmarkering eller karantän på grund av den här körningen.")
                + (f" Säkerhetsregel: {provider_rule}." if provider_rule else "")
            )
            quarantine_rows = persistent_qc[persistent_qc.apply(is_quarantined, axis=1)].copy()
            if not quarantine_rows.empty:
                show = quarantine_rows[[
                    "symbol","failure_streak","last_verified_at","last_reason","quarantine_until"
                ]].rename(columns={
                    "symbol":"Ticker","failure_streak":"Fel i följd",
                    "last_verified_at":"Senast verifierad","last_reason":"Senaste problem",
                    "quarantine_until":"Karantän till",
                })
                st.dataframe(show, use_container_width=True, hide_index=True)
            else:
                st.success("Ingen ticker ligger i aktiv karantän.")
            st.caption(
                "En aktie måste misslyckas vid tre separata dagar innan Borsify tillfälligt slutar försöka läsa in den i sju dagar. "
                "Om problemet verkar ligga hos datakällan räknas det inte som ett fel på aktien."
            )
    if st.session_state.get("bq_qc_state_migration_needed"):
        st.warning("Supabase saknar v2.45-tabellerna för persistent Universe QC. Kör den nya SQL-migreringen för permanent molnlagring.")
    if market == "Alla marknader":
        st.caption(
            "Topp 3 över alla marknader Borsify stöder just nu. "
            "Datatäckningen omfattar Borsifys 15 Avanza-inspirerade direktmarknader. "
            "Listan är ännu inte en komplett scanning av varje aktie som kan handlas hos Avanza."
        )
    else:
        st.warning(
            f"Du har filtrerat marknaden till {market}. Topplistorna nedan avser därför {market}. "
            "Välj **Alla marknader** i vänstermenyn för Borsifys globala ranking."
        )

    available_countries = sorted({
        _market_label_for_ticker(sym) for sym in scored.get("Ticker", pd.Series(dtype=str)).astype(str).tolist()
    })
    selected_countries = st.multiselect(
        "Filtrera Topplistor på land",
        options=available_countries,
        default=available_countries,
        help="Välj ett eller flera länder. Alla fyra Top 3-listorna räknas om direkt inom de valda länderna.",
        key="toplist_country_filter",
    )
    if selected_countries:
        toplist_base = scored[
            scored["Ticker"].astype(str).map(_market_label_for_ticker).isin(selected_countries)
        ].copy()
    else:
        toplist_base = scored.iloc[0:0].copy()
        st.info("Välj minst ett land för att visa Topplistor.")

    sections = [
        ("⚡ Bästa köp · 1–2 dagar", "day", "Daytrade Score",
         "Mycket kort sikt baserad på dagsdata – inte en realtids- eller intradagssignal. Borsify vill se styrka, tillräcklig handel och en tydlig riskplan, men försöker samtidigt undvika aktier som redan rusat så mycket att ett nytt köp riskerar att komma för sent."),
        ("📈 Bästa köp · 1 vecka–3 månader", "medium", "Mellan Score",
         "Borsify tittar på hur kursen gått de senaste 1–3 månaderna och väger ihop det med bolagets kvalitet, prisnivå och risk. En aktie som redan gått extremt långt kan stoppas trots ett högt betyg."),
        ("🏗️ Bästa köp · 1–5 år", "long", "Lång Score",
         "För flera års ägande väger bolagets kvalitet, prisnivå och risk betydligt tyngre än korta kursrörelser."),
        ("♾️ Bästa köp · mycket lång sikt", "lifetime", "Livstid Score",
         "Här krävs extra hög och uthållig kvalitet, god lönsamhet och en robust ekonomi. Det betyder inte att aktien ska ägas för alltid – den måste fortsätta förtjäna sin plats."),
    ]
    for title, horizon, score_col, caption in sections:
        st.markdown(f"### {title}")
        st.caption(caption)
        top3 = top_three(toplist_base, horizon)
        if top3.empty:
            st.info(
                "Inget köpcase är både tillräckligt starkt och tillräckligt väl underbyggt för den här horisonten just nu. "
                "Borsify lämnar hellre platsen tom än visar ett case med för svagt underlag."
            )
            continue
        cols = st.columns(3)
        for rank, (col, (_, row)) in enumerate(zip(cols, top3.iterrows()), start=1):
            with col:
                with st.container(border=True):
                    st.markdown(f"### {rank}. {_stock_identity(row)}")
                    price = _num(row.get("Pris"))
                    ccy = str(row.get("Valuta","") or "")
                    if np.isfinite(price):
                        st.markdown(f"**{price:.2f} {ccy}**")
                    score = _num(row.get(score_col))

                    st.markdown("**Varför köpa?**")
                    st.write(str(row.get("Varför köpa","—")))
                    st.markdown("**Varför just nu?**")
                    st.write(str(row.get("Varför nu","—")))
                    st.markdown("**Största risken**")
                    st.write(str(row.get("Största risk","—")))
                    st.markdown("**Vad ska du kontrollera?**")
                    st.write(str(row.get("Vad ändrar Borsifys syn","—")))

                    rr_plan = row.get("RR plan") if isinstance(row.get("RR plan"), dict) else {}

                    buy_position = str(row.get("Köpläge","") or "")
                    if buy_position == "VAR FÖRSIKTIG":
                        st.warning("⚠️ **Har aktien redan gått långt?** " + str(row.get("Köplägesförklaring","")))
                    elif buy_position == "FÖR SENT ATT JAGA?":
                        st.warning("⚠️ **Risk att köpa efter en stor uppgång:** " + str(row.get("Köplägesförklaring","")))

                    with st.expander("Visa mer om bedömningen", expanded=False):
                        st.metric("Borsifys betyg för tidshorisonten", f"{score:.0f}/100" if np.isfinite(score) else "—")
                        readiness = _num(row.get("Case Readiness"))
                        readiness_status = str(row.get("Case Readiness status","") or "")
                        if readiness_status:
                            st.caption(f"Underlaget: {readiness_status}" + (f" · {readiness:.0f}/100" if np.isfinite(readiness) else ""))
                        trust_status = str(row.get("Data Trust status","") or "")
                        if trust_status:
                            st.caption(f"Datakoll: {trust_status} · källa {row.get('Data Trust källa','Yahoo Finance via yfinance')} · kursdatum {row.get('Data Trust kursdatum','—')}")
                            _failure = assess_failure_transparency(row)
                            st.caption(f"{_failure['Data Failure status']} · {_failure['Data Failure förklaring']}")
                            trust_warn = str(row.get("Data Trust varningar","") or "")
                            if trust_warn and trust_warn != "inga tydliga datavarningar":
                                st.caption("Datavarning: " + trust_warn)
                        valuation_profile = str(row.get("Värderingsprofil", "") or "")
                        valuation_basis = str(row.get("Värderingsunderlag", "") or "")
                        valuation_note = str(row.get("Värderingsnotis", "") or "")
                        valuation_count = _num(row.get("Värderingsmått antal"))
                        if valuation_profile:
                            st.markdown("**Hur priset bedöms**")
                            detail = f"{valuation_profile} · {valuation_basis or 'underlag okänt'}"
                            if np.isfinite(valuation_count):
                                detail += f" · {int(valuation_count)} relevanta mått"
                            st.caption(detail)
                            if valuation_note:
                                st.caption(valuation_note)
                        st.caption("Fördjupning: handel, marknad, jämförelser och riskplan.")
                        if horizon in {"day","medium"}:
                            liq_status = str(row.get("Likviditetskontroll","") or "")
                            liq_text = str(row.get("Likviditet förklaring","") or "")
                            if liq_status:
                                st.markdown("**Går aktien rimligt att handla?**")
                                if liq_status == "GODTAGBAR HANDEL":
                                    st.success(liq_status)
                                elif liq_status == "TUNNARE HANDEL":
                                    st.warning(liq_status)
                                else:
                                    st.error(liq_status)
                                if liq_text:
                                    st.write(liq_text)
                                st.caption(
                                    "Borsify använder dagsdata här – inte realtid. Aktuell spread och orderboksdjup kan därför inte verifieras."
                   