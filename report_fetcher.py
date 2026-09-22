from __future__ import annotations

from io import BytesIO
from typing import Any
from urllib.request import Request, urlopen
import re

from report_sources import accept_report_candidate, candidate_report
from report_verification import verify_report_text

MAX_REPORT_BYTES = 4_000_000


def _clean_html(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
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


def fetch_report_text(url: str, timeout: float = 8.0, max_bytes: int = MAX_REPORT_BYTES) -> dict[str, Any]:
    """Fetch report text conservatively from a direct primary-source URL."""
    target = str(url or "").strip()
    if not target.lower().startswith(("https://", "http://")):
        return {"ok": False, "text": "", "error": "Ogiltig rapport-URL."}
    try:
        req = Request(target, headers={"User-Agent": "Borsify/4 report provenance checker"})
        with urlopen(req, timeout=timeout) as response:
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
        return {"ok": True, "text": text, "error": ""}
    try:
        raw = data.decode("utf-8", errors="replace")
    except Exception:
        raw = ""
    text = _clean_html(raw) if "<" in raw and ">" in raw else re.sub(r"\s+", " ", raw).strip()
    return {"ok": bool(text), "text": text, "error": "" if text else "Ingen läsbar text hittades."}


def verify_primary_report_from_events(
    events: dict[str, Any] | None,
    country: str,
    timeout: float = 8.0,
) -> dict[str, Any] | None:
    """Try one already-discovered primary report link; never search broadly here."""
    news = (events or {}).get("news") if isinstance(events, dict) else None
    if not isinstance(news, list):
        return None
    for item in news[:8]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "")
        url = str(item.get("link") or "")
        published_at = str(item.get("published_at") or "")
        provider = str(item.get("provider") or "")
        cand = candidate_report(title, published_at, url, url, provider)
        accepted, _reason = accept_report_candidate(cand, country)
        if not accepted:
            continue
        fetched = fetch_report_text(url, timeout=timeout)
        report = verify_report_text(cand, country, str(fetched.get("text") or ""))
        if not fetched.get("ok") and not report.get("Rapport läst"):
            report["Rapport kontroll"] = str(fetched.get("error") or report.get("Rapport kontroll") or "")
        return report
    return None
