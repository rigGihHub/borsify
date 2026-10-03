from __future__ import annotations

from io import BytesIO
from typing import Any
from urllib.request import Request, urlopen
import re
import json
from html.parser import HTMLParser
from urllib.parse import urljoin
from issuer_report_sources import source_for_issuer, verified_issuer_url

from report_sources import accept_report_candidate, candidate_report
from report_verification import verify_report_text

MAX_REPORT_BYTES = 4_000_000


def _clean_html(html: str) -> str:
    main = re.search(r"(?is)<(?:main|article)\b[^>]*>(.*?)</(?:main|article)>", html)
    html = main.group(1) if main else html
    text = re.sub(r"(?is)<(script|style|nav|header|footer|aside)\b.*?>.*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""
    try:
        reader = PdfReader(BytesIO(data))
        pages = []
        for page in reader.pages[:40]:
            pages.append(page.extract_text() or "")
        return re.sub(r"\s+", " ", " ".join(pages)).strip()
    except Exception:
        return ""


def original_publication_time(html: str) -> str:
    for block in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.I | re.S):
        try:
            value = json.loads(block)
            items = value if isinstance(value, list) else [value]
            for item in items:
                if isinstance(item, dict) and item.get("datePublished"):
                    return str(item["datePublished"])
        except (ValueError, TypeError):
            continue
    return ""


def discover_issuer_report_events(company_name: str, timeout: float = 8.0) -> list[dict[str, Any]]:
    source = source_for_issuer(company_name)
    if not source:
        return []
    url = source["index"]
    try:
        with urlopen(Request(url, headers={"User-Agent": "Borsify report discovery"}), timeout=timeout) as response:
            if not verified_issuer_url(response.geturl(), company_name):
                return []
            html = response.read(MAX_REPORT_BYTES).decode("utf-8", errors="replace")
    except Exception:
        return []
    class Links(HTMLParser):
        def __init__(self):
            super().__init__(); self.href = ""; self.words = []; self.links = []
        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.href = dict(attrs).get("href", ""); self.words = []
        def handle_data(self, data):
            if self.href:
                self.words.append(data)
        def handle_endtag(self, tag):
            if tag == "a" and self.href:
                self.links.append((self.href, " ".join(self.words).strip())); self.href = ""
    parser = Links(); parser.feed(html)
    result = []
    for href, title in parser.links:
        target = urljoin(url, href)
        if not verified_issuer_url(target, company_name):
            continue
        cand = candidate_report(title, "", target)
        if cand["is_financial_report"] and len(title) >= 10:
            result.append({"title": title, "link": target, "published_at": "", "provider": company_name + " IR"})
    return result[:8]


def fetch_report_text(url: str, timeout: float = 8.0, max_bytes: int = MAX_REPORT_BYTES) -> dict[str, Any]:
    """Fetch report text conservatively from a direct primary-source URL."""
    target = str(url or "").strip()
    if not target.lower().startswith(("https://", "http://")):
        return {"ok": False, "text": "", "error": "Ogiltig rapport-URL."}
    try:
        req = Request(target, headers={"User-Agent": "Borsify/4 report provenance checker"})
        with urlopen(req, timeout=timeout) as response:
            resolved_url = response.geturl()
            content_type = str(response.headers.get("content-type") or "").lower()
            data = response.read(max_bytes + 1)
    except Exception as exc:
        return {"ok": False, "text": "", "error": f"Rapport kunde inte hämtas ({type(exc).__name__})."}

    if len(data) > max_bytes:
        return {"ok": False, "text": "", "error": "Rapporten var större än Borsifys säkra hämtningsgräns."}
    if "pdf" in content_type or target.lower().split("?", 1)[0].endswith(".pdf"):
        text = _pdf_text(data)
        if not text:
            return {"ok": False, "text": "", "error": "PDF kunde hämtas men text kunde inte extraheras."}
        return {"ok": True, "text": text, "error": "", "resolved_url": resolved_url}
    try:
        raw = data.decode("utf-8", errors="replace")
    except Exception:
        raw = ""
    text = _clean_html(raw) if "<" in raw and ">" in raw else re.sub(r"\s+", " ", raw).strip()
    return {"ok": bool(text), "text": text, "error": "" if text else "Ingen läsbar text hittades.", "resolved_url": resolved_url, "original_published_at": original_publication_time(raw)}


def verify_primary_report_from_events(
    events: dict[str, Any] | None,
    country: str,
    timeout: float = 8.0,
    company_name: str = "",
) -> dict[str, Any] | None:
    """Try one already-discovered primary report link; never search broadly here."""
    news = (events or {}).get("news") if isinstance(events, dict) else None
    news = list(news) if isinstance(news, list) else []
    # Use configured original issuer sources when vendor news has no accepted report.
    if not any(accept_report_candidate({**candidate_report(str(n.get("title") or ""), str(n.get("published_at") or ""), str(n.get("link") or "")), "issuer_name": company_name}, country)[0] for n in news if isinstance(n, dict)):
        news += discover_issuer_report_events(company_name, timeout=timeout)
    import pandas as pd
    def timestamp(item):
        try:
            return pd.Timestamp(item.get("published_at"), tz="UTC").value
        except Exception:
            try:
                return pd.Timestamp(item.get("published_at")).value
            except Exception:
                return 0
    failed = None
    for item in sorted([n for n in news if isinstance(n, dict)], key=timestamp, reverse=True)[:8]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        url = str(item.get("link") or "")
        published_at = str(item.get("published_at") or "")
        provider = str(item.get("provider") or "")
        cand = candidate_report(title, published_at, url, url, provider)
        cand["issuer_name"] = company_name
        accepted, _reason = accept_report_candidate(cand, country)
        if not accepted:
            continue
        fetched = fetch_report_text(url, timeout=timeout)
        # Validate the source of the downloaded body, not only the original link.
        if fetched.get("resolved_url"):
            cand["attachment_url"] = fetched["resolved_url"]
        cand["original_published_at"] = fetched.get("original_published_at") or ""
        if not cand["published_at"]:
            cand["published_at"] = cand["original_published_at"]
        report = verify_report_text(cand, country, str(fetched.get("text") or ""), company_name=company_name)
        report["Rapport begärd URL"] = url
        if not fetched.get("ok") and not report.get("Rapport läst"):
            report["Rapport kontroll"] = str(fetched.get("error") or report.get("Rapport kontroll") or "")
        if report.get("Rapport läst"):
            return report
        if failed is None:
            failed = report
    return failed
