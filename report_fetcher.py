from __future__ import annotations

from io import BytesIO
from typing import Any
from urllib.request import Request, urlopen
import re
import json
import time
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
    from datetime import datetime
    from zoneinfo import ZoneInfo
    year = datetime.now(ZoneInfo("Europe/Stockholm")).year
    pattern = source["index"]
    urls = [pattern.format(year=year), pattern.format(year=year - 1)] if "{year}" in pattern else [pattern]
    deadline = time.monotonic() + timeout
    result = []; seen = set()
    for url in urls:
        available = deadline - time.monotonic()
        if available <= 0:
            break
        try:
            with urlopen(Request(url, headers={"User-Agent": "Borsify report discovery"}), timeout=available) as response:
                if not verified_issuer_url(response.geturl(), company_name):
                    continue
                data = response.read(MAX_REPORT_BYTES + 1)
                if len(data) > MAX_REPORT_BYTES:
                    continue
                html = data.decode("utf-8", errors="replace")
        except Exception:
            continue
        parser = Links(); parser.feed(html)
        page_results = []
        for href, title in parser.links:
            target = urljoin(url, href)
            title = re.sub(r"\s+", " ", title).strip()
            if target in seen or not verified_issuer_url(target, company_name):
                continue
            if re.search(r"presentation|webcast|presentationer", title, re.I):
                continue
            if source.get("pdf_label") and target.lower().endswith('.pdf') and re.search(r"\b20\d{2}\b", title):
                title = source["pdf_label"] + " " + title
            cand = candidate_report(title, "", target)
            if cand["is_financial_report"] and len(title) >= 8:
                seen.add(target)
                page_results.append({"title": title, "link": target, "published_at": "", "provider": company_name + " IR"})
        # Current archive page first; only inspect previous year when empty.
        result.extend(page_results)
        if result:
            break
    def report_order(item):
        years = re.findall(r"20\d{2}", item['title'] + ' ' + item['link'])
        quarter = re.search(r"q([1-4])|\b(3|6|9|12)m\b", item['title'] + ' ' + item['link'], re.I)
        period = int(quarter.group(1)) if quarter and quarter.group(1) else (int(quarter.group(2)) // 3 if quarter else 0)
        return (max(map(int, years), default=0), period)
    return sorted(result, key=report_order, reverse=True)[:8]


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
    *,
    budget_seconds: float = 12.0,
) -> dict[str, Any] | None:
    """Try accepted reports only, then known issuer IR, within one request budget.

    The deadline limits new attempts; an in-flight socket operation can still run
    until its timeout. Missing/failed downloads never become read reports.
    """
    import pandas as pd
    deadline = time.monotonic() + max(0.0, budget_seconds)
    news = (events or {}).get("news") if isinstance(events, dict) else None
    news = list(news) if isinstance(news, list) else []

    def remaining():
        return max(0.0, min(timeout, deadline - time.monotonic()))

    def accepted_items(items):
        result = []
        for item in items:
            if not isinstance(item, dict):
                continue
            cand = {**candidate_report(str(item.get("title") or ""), str(item.get("published_at") or ""), str(item.get("link") or "")), "issuer_name": company_name}
            if accept_report_candidate(cand, country)[0]:
                result.append(item)
        def timestamp(item):
            parsed = pd.to_datetime(item.get("published_at"), utc=True, errors="coerce")
            return parsed.value if pd.notna(parsed) else 0
        return sorted(result, key=timestamp, reverse=True)

    failed = None
    attempted = set()
    # Filter before limiting: normal news must not consume report slots.
    candidates = accepted_items(news)
    for phase in range(2):
        if phase == 1:
            available = remaining()
            if available <= 0 or not source_for_issuer(company_name):
                break
            candidates = accepted_items(discover_issuer_report_events(company_name, timeout=available))
        for item in candidates:
            url = str(item.get("link") or "")
            if url in attempted:
                continue
            available = remaining()
            if available <= 0 or len(attempted) >= 8:
                break
            attempted.add(url)
            title = str(item.get("title") or "")
            published_at = str(item.get("published_at") or "")
            provider = str(item.get("provider") or "")
            cand = candidate_report(title, published_at, url, url, provider)
            cand["issuer_name"] = company_name
            fetched = fetch_report_text(url, timeout=available)
            # Validate the downloaded body's source after redirects too.
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
