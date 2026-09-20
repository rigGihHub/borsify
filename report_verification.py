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
