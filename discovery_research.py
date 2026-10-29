"""Issuer-bound report research for discovery cards; never changes buy policy."""
from report_fetcher import verify_primary_report_from_events
from report_verification import report_data_provenance
from business_report_evidence import usable_business_evidence
from issuer_report_sources import verified_issuer_url
from future_discovery import REPORTS


ISSUERS = {
    "ALAB": "Astera Labs", "CRDO": "Credo Technology", "RKLB": "Rocket Lab",
    "S": "SentinelOne", "IOT": "Samsara", "AXON": "Axon Enterprise",
    "GRAB": "Grab Holdings Limited", "PHARM.AS": "Pharming Group",
    "RR.L": "Rolls-Royce Holdings", "0XXT.IL": "Atlas Copco",
    "ATCO-A.ST": "Atlas Copco", "ATCO-B.ST": "Atlas Copco",
}

# Dated, directly inspected reports. These are fallbacks, not a claim that the
# archive contains no newer publication. Runtime source/body checks still apply.
DIRECT_REPORTS = {
    "Atlas Copco": {"title": "Q3 2026 quarterly report", "published_at": "2026-10-22", "link": "https://www.atlascopcogroup.com/content/dam/atlas-copco/group/documents/investors/financial-publications/english/20261022-en-q3-2026-dd.pdf"},
    "Pharming Group": {"title": "Q3 2026 financial results", "published_at": "2026-10-27", "link": "https://www.pharming.com/our-news/pharming-reports-third-quarter-2026-financial-results"},
    "Grab Holdings Limited": {"title": "Q2 2026 financial results", "published_at": "2026-08-04", "link": "https://www.grab.com/sg/press/others/grab-reports-record-second-quarter-2026-results-raises-full-year-guidance-and-announces-750-million-share-repurchase-program/"},
}


def research_report(ticker, reader=verify_primary_report_from_events):
    name = ISSUERS.get(str(ticker).strip().upper())
    if not name:
        return {"status": "Källa saknas", "message": "Bolaget saknar ännu en verifierad rapportkälla i Borsifys register.", "excerpts": []}
    try:
        seed = REPORTS.get(str(ticker).strip().upper())
        events = {"news": []}
        if name in DIRECT_REPORTS:
            events["news"].append(DIRECT_REPORTS[name].copy())
        if seed and verified_issuer_url(seed["url"], name):
            events["news"].append({"title": f"{seed['period']} financial results", "published_at": seed["date"], "link": seed["url"], "provider": name + " IR"})
        report = reader(events, "", company_name=name, budget_seconds=12, timeout=6)
    except Exception as exc:
        return {"status": "Hämtning misslyckades", "message": f"Rapportgranskningen avbröts ({type(exc).__name__}). Försök senare.", "excerpts": []}
    provenance = report_data_provenance({}, report)
    if provenance.get("Rapport text verifierad") is not True:
        return {"status": "Inte verifierad", "message": provenance["Rapport kontroll"], "excerpts": []}
    # Bound quotations and preserve whole sentences, including negative wording.
    excerpts = []; words = 0; seen = set()
    for item in usable_business_evidence(provenance):
        sentence = str(item.get("text") or "")
        count = len(sentence.split())
        if not 1 <= count <= 35 or words + count > 100 or sentence in seen:
            continue
        excerpts.append(item); words += count; seen.add(sentence)
        if len(excerpts) == 4:
            break
    return {"status": "Rapporttext kontrollerad", "message": provenance["Rapport kontroll"],
            "url": provenance.get("Rapport URL"), "period": provenance.get("Rapport periodtext"),
            "published": provenance.get("Rapport publicerad"),
            "publication_verified": provenance.get("Rapport datum verifierat") is True,
            "checked": provenance.get("Rapport kontrollerad"), "excerpts": excerpts,
            "topics": provenance.get("Rapport finansiella ämnen", []),
            "limits": "Textutdragen är bolagets uppgifter. Belopp, organisk tillväxt, förvärvseffekter, konkurrensfördel och prognoser är inte oberoende avstämda. Granskningen ändrar varken betyg eller köpbeslut."}
