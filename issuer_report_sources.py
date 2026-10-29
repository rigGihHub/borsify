"""Small independently checked issuer registry. Unknown domains remain untrusted."""
import re
from urllib.parse import urlsplit

SOURCES = {
    "atlas copco": {"hosts": {"www.atlascopcogroup.com", "atlascopcogroup.com"}, "index": "https://www.atlascopcogroup.com/en/investors/reports-and-presentations", "evidence": "https://www.atlascopcogroup.com/en/investors"},
    "grab holdings limited": {"hosts": {"investors.grab.com", "www.grab.com"}, "index": "https://investors.grab.com/financial-information/quarterly-results/", "evidence": "https://investors.grab.com/overview/"},
    "pharming group": {"hosts": {"www.pharming.com", "pharming.com"}, "index": "https://www.pharming.com/investors/investor-materials/financial-documents-reports", "evidence": "https://www.pharming.com/investors"},
    "rolls royce holdings": {"hosts": {"www.rolls-royce.com", "rolls-royce.com"}, "index": "https://www.rolls-royce.com/investors/results-reports-and-presentations/financial-results.aspx", "evidence": "https://www.rolls-royce.com/investors"},
    "astera labs": {"hosts": {"ir.asteralabs.com", "www.asteralabs.com"}, "index": "https://ir.asteralabs.com/", "evidence": "https://ir.asteralabs.com/"},
    "credo technology": {"hosts": {"investors.credosemi.com"}, "index": "https://investors.credosemi.com/news-events/news/default.aspx", "evidence": "https://investors.credosemi.com/"},
    "rocket lab": {"hosts": {"investors.rocketlabcorp.com"}, "index": "https://investors.rocketlabcorp.com/financial-information/quarterly-results", "evidence": "https://investors.rocketlabcorp.com/"},
    "sentinelone": {"hosts": {"investors.sentinelone.com"}, "index": "https://investors.sentinelone.com/financials/quarterly-results/default.aspx", "evidence": "https://investors.sentinelone.com/"},
    "samsara": {"hosts": {"investors.samsara.com"}, "index": "https://investors.samsara.com/overview/", "evidence": "https://investors.samsara.com/"},
    "axon enterprise": {"hosts": {"investor.axon.com"}, "index": "https://investor.axon.com/quarterly-results", "evidence": "https://investor.axon.com/"},
    "proact it group": {"hosts": {"proact.eu", "www.proact.eu"}, "index": "https://www.proact.eu/financial-reports/", "evidence": "https://www.proact.eu/investor-relations/"},
    "bavarian nordic": {"hosts": {"bavarian-nordic.com", "www.bavarian-nordic.com"}, "index": "https://www.bavarian-nordic.com/investor/financials.aspx", "evidence": "https://www.bavarian-nordic.com/investor/investor.aspx"},
    "hafnia limited": {"hosts": {"investor.hafnia.com"}, "index": "https://investor.hafnia.com/ir-news/", "evidence": "https://investor.hafnia.com/"},
    "meds apotek": {
        "hosts": {"corporate.meds.se"},
        "index": "https://corporate.meds.se/media/pressmeddelanden/",
        "evidence": "https://corporate.meds.se/finansiell-information/rapporter-och-presentationer/",
    },
    "moment group": {
        "hosts": {"momentgroup.com", "www.momentgroup.com"},
        "index": "https://momentgroup.com/finansiella-rapporter/",
        "evidence": "https://momentgroup.com/investor-relations/",
    },
    "observe medical": {
        "hosts": {"observemedical.com", "www.observemedical.com"},
        "index": "https://observemedical.com/investor-relations/",
        "evidence": "https://observemedical.com/regulatory-news/",
    },
    "industrivärden": {
        "hosts": {"industrivarden.se", "www.industrivarden.se"},
        "index": "https://www.industrivarden.se/investerare/rapporter-och-presentationer/Delarsrapporter/",
        "pdf_label": "Delårsrapport",
        "evidence": "https://www.industrivarden.se/investerare/Kalender/",
    },
    "investor": {
        "hosts": {"investorab.com", "www.investorab.com"},
        "index": "https://www.investorab.com/investors-media/reports-presentations/{year}",
        "evidence": "https://www.investorab.com/investors-media/reports-presentations/2026",
    },
}

def issuer_name(value):
    tokens = re.findall(r"[^\W_]+", re.sub(r"\bA\s*/\s*S\b", "", str(value or ""), flags=re.I).casefold())
    if re.search(r'\bser\.?\s+[a-z]\b', str(value or ''), re.I):
        tokens = tokens[:tokens.index('ser')]
    return ' '.join(t for t in tokens if t not in {'ab', 'publ', 'plc', 'inc', 'asa', 'as', 'corp', 'corporation', 'ltd'})

def source_for_issuer(name):
    normalized = issuer_name(name)
    return SOURCES.get(normalized) or (SOURCES["hafnia limited"] if normalized == "hafnia" else None)

def verified_issuer_url(url, name):
    source = source_for_issuer(name)
    try:
        p = urlsplit(str(url))
        return bool(source and p.scheme == 'https' and not p.username and not p.password and p.hostname in source['hosts'])
    except ValueError:
        return False
