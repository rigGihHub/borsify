"""Small independently checked issuer registry. Unknown domains remain untrusted."""
import re
from urllib.parse import urlsplit

SOURCES = {
    "industrivärden": {
        "hosts": {"industrivarden.se", "www.industrivarden.se"},
        "index": "https://www.industrivarden.se/media/Pressmeddelanden/",
        "evidence": "https://www.industrivarden.se/investerare/Kalender/",
    },
    "investor": {
        "hosts": {"investorab.com", "www.investorab.com"},
        "index": "https://www.investorab.com/investors-media/reports-presentations/",
        "evidence": "https://www.investorab.com/investors-media/reports-presentations/2026",
    },
}

def issuer_name(value):
    tokens = re.findall(r"[^\W_]+", re.sub(r"\bA\s*/\s*S\b", "", str(value or ""), flags=re.I).casefold())
    if re.search(r'\bser\.?\s+[a-z]\b', str(value or ''), re.I):
        tokens = tokens[:tokens.index('ser')]
    return ' '.join(t for t in tokens if t not in {'ab', 'publ', 'plc', 'inc', 'asa', 'as', 'corp', 'corporation', 'ltd'})

def source_for_issuer(name):
    return SOURCES.get(issuer_name(name))

def verified_issuer_url(url, name):
    source = source_for_issuer(name)
    try:
        p = urlsplit(str(url))
        return bool(source and p.scheme == 'https' and not p.username and not p.password and p.hostname in source['hosts'])
    except ValueError:
        return False
