from __future__ import annotations

from typing import Any
from datetime import datetime, timezone
import hashlib
import re
from issuer_report_sources import issuer_name

from report_sources import accept_report_candidate, report_identity, report_freshness
from report_reader import report_reader_fields, report_reader_user_text

MIN_REPORT_TEXT_CHARS = 1500
REPORT_VERIFICATION_VERSION = 3

# These checks establish report-like content, not the correctness of its figures
# or any investment conclusion. At least two numeric financial topics must occur.
FINANCIAL_TOPICS = {
    "omsättning": r"\b(?:revenue|sales|net sales|omsättning|nettoomsättning)\b",
    "resultat": r"\b(?:profit|earnings|eps|ebit|ebita|ebitda|resultat|vinst|rörelseresultat)\b",
    "kassaflöde": r"\b(?:cash flow|free cash flow|kassaflöde|fcf)\b",
    "marginal": r"\b(?:margin|marginal|rörelsemarginal)\b",
    "substansvärde": r"\b(?:NAV|net asset value|substansvärde)\b",
}
REPORT_PERIOD = re.compile(
    r"\b(?:Q[1-4]\s*[-/]?\s*20\d{2}|20\d{2}\s*[-/]?\s*Q[1-4]|"
    r"(?:annual|quarterly|interim|half[- ]year(?:ly)?|year[- ]end) report\s*(?:for\s*)?20\d{2}|"
    r"(?:årsrapport|årsredovisning|delårsrapport|halvårsrapport|bokslutskommuniké|bokslutsrapport)\s*20\d{2}|"
    r"(?:1\s+)?januari\s*[-–]\s*(?:31\s+mars|30\s+juni|30\s+september|31\s+december)\s+20\d{2})\b",
    re.IGNORECASE,
)


def _numeric_financial_evidence(text: str) -> list[dict[str, str]]:
    found = []
    for name, pattern in FINANCIAL_TOPICS.items():
        for match in re.finditer(pattern, text, re.IGNORECASE):
            # Require a number close to the topic, in the same sentence.
            following = text[match.end():match.end() + 100]
            following = re.split(r"[.!?](?:\s|$)", following, maxsplit=1)[0]
            if re.search(r"\d", following):
                found.append({"ämne": name, "textutdrag": text[match.start():match.end()] + following})
                break
    return found

def verify_report_text(candidate: dict[str, Any], country: str, text: str, company_name: str = "") -> dict[str, Any]:
    """A report is 'read' only after primary-source and content checks pass."""
    accepted, reason = accept_report_candidate(candidate, country)
    identity = report_identity(candidate)
    freshness = report_freshness(str(candidate.get("published_at") or ""))
    clean = re.sub(r"\s+", " ", str(text or "")).strip()

    base = {
        **identity,
        "Rapport färskhet": freshness.get("label"),
        "Rapport datum verifierat": False,
        "Rapport datum tolkat": freshness.get("known") is True,
        "Rapport bolag verifierat": False,
        "Rapport textlängd": len(clean),
        "Rapport verifieringsversion": REPORT_VERIFICATION_VERSION,
        "Rapport kontrollerad": datetime.now(timezone.utc).isoformat(),
    }
    if not accepted:
        return {**base, "Rapport läst": False, "Rapport kontroll": reason}
    if len(clean) < MIN_REPORT_TEXT_CHARS:
        return {
            **base,
            "Rapport läst": False,
            "Rapport kontroll": "För lite faktisk rapporttext hämtades för att kalla rapporten läst.",
        }

    # Exact token-normalised issuer aliases only; a ticker or a generic word is insufficient.
    def normal(value):
        return issuer_name(value)
    aliases = [company_name] if company_name else [str(candidate.get("issuer_name") or "")]
    issuer = normal(clean)
    names = [normal(name) for name in aliases if len(normal(name)) >= 5]
    if not names or not any(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", issuer) for name in names):
        return {**base, "Rapport läst": False, "Rapport kontroll": "Rapporttexten kunde inte knytas till det analyserade bolaget."}
    base["Rapport bolag verifierat"] = True
    period = REPORT_PERIOD.search(clean)
    excerpts = _numeric_financial_evidence(clean)
    topics = [excerpt["ämne"] for excerpt in excerpts]
    base.update({
        "Rapport periodtext": period.group(0) if period else "",
        "Rapport finansiella ämnen": topics,
        "Rapport textutdrag": excerpts,
    })
    if not period or len(topics) < 2:
        return {
            **base,
            "Rapport läst": False,
            "Rapport kontroll": "Rapportperiod och minst två ämnen med finansiella tal kunde inte verifieras i texten.",
        }
    title = str(candidate.get("title") or "")
    title_quarter = re.search(r"\bQ([1-4])\b", title, re.IGNORECASE)
    title_year = re.search(r"\b20\d{2}\b", title)
    periods = [match.group(0) for match in REPORT_PERIOD.finditer(clean)]
    matching = [label for label in periods if (
        (not title_quarter or f"q{title_quarter.group(1)}" in label.lower())
        and (not title_year or title_year.group(0) in label)
    )]
    if not matching:
        return {**base, "Rapport läst": False, "Rapport kontroll": "Rapportperioden i texten stämmer inte med rapportlänkens titel."}
    base["Rapport periodtext"] = matching[0]
    base["Rapport faktacitat"] = [{**item, "källa": identity["Rapport URL"], "rapportperiod": matching[0]} for item in excerpts]
    base["Rapport fakta status"] = "Finansiella textcitat; belopp och redovisningsdefinitioner ej avstämda"
    # A vendor timestamp is parsed metadata, not independent publication verification.
    base["Rapport publicering status"] = "Leverantörens datum; originalpublicering ej avstämd"
    import pandas as pd
    original = pd.to_datetime(candidate.get("original_published_at"), utc=True, errors="coerce")
    claimed = pd.to_datetime(candidate.get("published_at"), utc=True, errors="coerce")
    if pd.notna(original) and pd.notna(claimed) and abs((original - claimed).total_seconds()) <= 60 and freshness.get("known"):
        base["Rapport datum verifierat"] = True
        base["Rapport publicering status"] = "Originalsidans publiceringstid matchar kandidatens datum"

    fields = report_reader_fields(
        clean,
        source_url=identity["Rapport URL"],
        published_at=identity["Rapport publicerad"],
    )
    return {
        **base,
        **fields,
        "Rapport läst": True,
        "Rapport text SHA256": hashlib.sha256(clean.encode("utf-8")).hexdigest(),
        "Rapport kontroll": "Primär källa, rapportperiod och finansiellt textinnehåll kontrollerade. Siffrornas riktighet är inte verifierad.",
        "Rapport användartext": report_reader_user_text(fields),
    }

def can_support_fresh_recommendation(report: dict[str, Any]) -> bool:
    if report.get("Rapport läst") is not True or report.get("Rapport datum verifierat") is not True:
        return False
    freshness = str(report.get("Rapport färskhet") or "").lower()
    return "för gammal" not in freshness and "okänt" not in freshness and "kontrollera" not in freshness

def report_data_provenance(raw: dict[str, Any] | None, verified_report: dict[str, Any] | None = None) -> dict[str, Any]:
    """Expose what report evidence the current analysis actually has.

    Report Delta uses structured market/fundamental fields even when primary
    report text was checked separately. Text availability must not imply that
    the calculation extracted facts from that text.
    """
    if (verified_report and verified_report.get("Rapport läst") is True
            and verified_report.get("Rapport verifieringsversion") == REPORT_VERIFICATION_VERSION
            and verified_report.get("Rapport text SHA256")):
        return {
            **verified_report,
            "Rapport text verifierad": True,
            "Rapport primärkälla verifierad": True,
            "Report Delta datagrund": "Strukturerade bolags- och kursdata. Primär rapporttext har kontrollerats separat och används inte i Report Delta-beräkningen.",
        }

    source = ""
    if isinstance(raw, dict):
        health = raw.get("source_health")
        if isinstance(health, dict):
            source = str(health.get("source") or "")
    return {
        **(verified_report or {}),
        "Rapport läst": False,
        "Rapport text verifierad": False,
        "Rapport primärkälla verifierad": False,
        "Rapport textlängd": (verified_report or {}).get("Rapport textlängd", 0),
        "Rapport källa": (verified_report or {}).get("Rapport källa") or source or "Ej verifierad primär rapportkälla",
        "Rapport URL": (verified_report or {}).get("Rapport URL", ""),
        "Rapport kontroll": (verified_report or {}).get("Rapport kontroll") or "Ingen verifierad primär rapporttext hämtades för den här analysen.",
        "Rapport användartext": "Borsify har inte läst originalrapporten. Report Delta bygger på strukturerade bolagsdata, estimatfält och kursreaktion, inte på verifierad rapporttext.",
        "Report Delta datagrund": "Strukturerade yfinance/Yahoo-fält och kursdata; ingen verifierad primär rapporttext.",
    }
