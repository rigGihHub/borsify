from __future__ import annotations

from typing import Any
import re

from report_sources import accept_report_candidate, report_identity, report_freshness
from report_reader import report_reader_fields, report_reader_user_text

MIN_REPORT_TEXT_CHARS = 1500

def verify_report_text(candidate: dict[str, Any], country: str, text: str) -> dict[str, Any]:
    """A report is 'read' only after primary-source and content checks pass."""
    accepted, reason = accept_report_candidate(candidate, country)
    identity = report_identity(candidate)
    freshness = report_freshness(str(candidate.get("published_at") or ""))
    clean = re.sub(r"\s+", " ", str(text or "")).strip()

    base = {
        **identity,
        "Rapport färskhet": freshness.get("label"),
        "Rapport textlängd": len(clean),
    }
    if not accepted:
        return {**base, "Rapport läst": False, "Rapport kontroll": reason}
    if len(clean) < MIN_REPORT_TEXT_CHARS:
        return {
            **base,
            "Rapport läst": False,
            "Rapport kontroll": "För lite faktisk rapporttext hämtades för att kalla rapporten läst.",
        }

    fields = report_reader_fields(
        clean,
        source_url=identity["Rapport URL"],
        published_at=identity["Rapport publicerad"],
    )
    return {
        **base,
        **fields,
        "Rapport läst": True,
        "Rapport kontroll": "Primär källa och faktisk rapporttext verifierad.",
        "Rapport användartext": report_reader_user_text(fields),
    }

def can_support_fresh_recommendation(report: dict[str, Any]) -> bool:
    if not bool(report.get("Rapport läst")):
        return False
    freshness = str(report.get("Rapport färskhet") or "").lower()
    return "för gammal" not in freshness and "okänt" not in freshness

def report_data_provenance(raw: dict[str, Any] | None, verified_report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Expose what report evidence the current analysis actually has.

    Until a primary-source report fetcher supplies verified report text, Report
    Delta is based on structured market/fundamental fields. That can be useful,
    but it must not be presented as if Borsify read the original report.
    """
    if verified_report and bool(verified_report.get("Rapport läst")):
        return {
            **verified_report,
            "Rapport text verifierad": True,
            "Rapport primärkälla verifierad": True,
            "Report Delta datagrund": "Verifierad primär rapporttext + strukturerade bolags- och kursdata.",
        }

    source = ""
    if isinstance(raw, dict):
        health = raw.get("source_health")
        if isinstance(health, dict):
            source = str(health.get("source") or "")
    return {
        "Rapport läst": False,
        "Rapport text verifierad": False,
        "Rapport primärkälla verifierad": False,
        "Rapport textlängd": 0,
        "Rapport källa": source or "Ej verifierad primär rapportkälla",
        "Rapport URL": "",
        "Rapport kontroll": "Ingen verifierad primär rapporttext hämtades för den här analysen.",
        "Rapport användartext": "Borsify har inte läst originalrapporten. Report Delta bygger på strukturerade bolagsdata, estimatfält och kursreaktion, inte på verifierad rapporttext.",
        "Report Delta datagrund": "Strukturerade yfinance/Yahoo-fält och kursdata; ingen verifierad primär rapporttext.",
    }
