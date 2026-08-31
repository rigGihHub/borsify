from __future__ import annotations

import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IdeaSource:
    name: str
    kind: str
    url: str


DEFAULT_SOURCES = [
    IdeaSource(
        "Ekonomimedia · Google News",
        "media",
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote('(aktie OR börs OR rapport OR utdelning) (site:di.se OR site:placera.se OR site:affarsvarlden.se OR site:borskollen.se)')
        + "&hl=sv&gl=SE&ceid=SE:sv",
    ),
    IdeaSource(
        "Forum · Reddit Aktiemarknaden",
        "forum",
        "https://www.reddit.com/r/Aktiemarknaden/new/.rss",
    ),
]


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(value: str | None) -> pd.Timestamp:
    if not value:
        return pd.NaT
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return pd.Timestamp(dt)
    except Exception:
        try:
            return pd.Timestamp(value).tz_localize(None)
        except Exception:
            return pd.NaT


def _fetch_xml(url: str, timeout: int = 8) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Borsify/2.12 (+https://borsify.se; public-feed-reader)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
        return response.read()


def parse_feed(xml_bytes: bytes, source: IdeaSource, max_items: int = 40) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    rows: list[dict] = []

    # RSS 2.0
    for item in root.findall(".//item")[:max_items]:
        title = _clean_html(item.findtext("title") or "")
        summary = _clean_html(item.findtext("description") or "")
        link = (item.findtext("link") or "").strip()
        published = _parse_date(item.findtext("pubDate"))
        rows.append({"source": source.name, "kind": source.kind, "title": title, "summary": summary, "link": link, "published": published})

    if rows:
        return rows

    # Atom
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//a:entry", ns)[:max_items]:
        title = _clean_html(entry.findtext("a:title", default="", namespaces=ns))
        summary = _clean_html(
            entry.findtext("a:summary", default="", namespaces=ns)
            or entry.findtext("a:content", default="", namespaces=ns)
        )
        link_el = entry.find("a:link", ns)
        link = link_el.attrib.get("href", "") if link_el is not None else ""
        published = _parse_date(
            entry.findtext("a:published", default="", namespaces=ns)
            or entry.findtext("a:updated", default="", namespaces=ns)
        )
        rows.append({"source": source.name, "kind": source.kind, "title": title, "summary": summary, "link": link, "published": published})
    return rows


def fetch_public_idea_flow(sources: Iterable[IdeaSource] = DEFAULT_SOURCES, max_items_per_source: int = 40) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict] = []
    errors: list[str] = []
    for source in sources:
        try:
            rows.extend(parse_feed(_fetch_xml(source.url), source, max_items=max_items_per_source))
        except Exception as exc:
            errors.append(f"{source.name}: {type(exc).__name__}")
    if not rows:
        return pd.DataFrame(columns=["source", "kind", "title", "summary", "link", "published"]), errors
    frame = pd.DataFrame(rows)
    frame["published"] = pd.to_datetime(frame["published"], errors="coerce")
    frame = frame.drop_duplicates(subset=["title", "link"], keep="first")
    return frame.sort_values("published", ascending=False, na_position="last").reset_index(drop=True), errors


def _normalize(text: str) -> str:
    text = (text or "").lower().replace("&", " och ")
    text = re.sub(r"[^a-z0-9åäö]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _aliases(name: str, ticker: str) -> list[str]:
    base = re.sub(r"\.ST$", "", ticker or "", flags=re.I)
    base = re.sub(r"-[A-Z]$", "", base, flags=re.I)
    clean_name = re.sub(r"\b(ab|publ|class|ser\.?\s*[ab]|aktiebolag)\b", " ", name or "", flags=re.I)
    candidates = [_normalize(clean_name), _normalize(base)]
    # Add first meaningful name token for cases such as "Investor AB (publ)".
    tokens = _normalize(clean_name).split()
    if tokens and len(tokens[0]) >= 4:
        candidates.append(tokens[0])
    return sorted({x for x in candidates if len(x) >= 3}, key=len, reverse=True)


def _mentioned(text: str, aliases: list[str]) -> bool:
    hay = f" {_normalize(text)} "
    for alias in aliases:
        if f" {alias} " in hay:
            return True
    return False


def map_mentions(feed: pd.DataFrame, stocks: pd.DataFrame) -> pd.DataFrame:
    if feed.empty or stocks.empty:
        return pd.DataFrame(columns=["Ticker", "Namn", "Antal omnämnanden", "Källor", "Forum", "Media", "Senast nämnd", "Rubriker"])
    stock_rows = []
    for _, stock in stocks.iterrows():
        ticker = str(stock.get("Ticker", ""))
        name = str(stock.get("Namn", ticker))
        aliases = _aliases(name, ticker)
        matches = []
        for _, item in feed.iterrows():
            text = f"{item.get('title','')} {item.get('summary','')}"
            if _mentioned(text, aliases):
                matches.append(item)
        if not matches:
            continue
        m = pd.DataFrame(matches)
        published = pd.to_datetime(m["published"], errors="coerce")
        latest = published.max() if published.notna().any() else pd.NaT
        headlines = []
        for _, r in m.sort_values("published", ascending=False, na_position="last").head(4).iterrows():
            headlines.append({"title": str(r.get("title", "")), "source": str(r.get("source", "")), "link": str(r.get("link", ""))})
        stock_rows.append({
            "Ticker": ticker,
            "Namn": name,
            "Antal omnämnanden": int(len(m)),
            "Källor": int(m["source"].nunique()),
            "Forum": int((m["kind"] == "forum").sum()),
            "Media": int((m["kind"] == "media").sum()),
            "Senast nämnd": latest,
            "Rubriker": headlines,
        })
    return pd.DataFrame(stock_rows)


def discovery_strength(row: pd.Series, now: pd.Timestamp | None = None) -> float:
    now = now or pd.Timestamp.utcnow().tz_localize(None)
    mentions = float(row.get("Antal omnämnanden", 0) or 0)
    sources = float(row.get("Källor", 0) or 0)
    latest = pd.to_datetime(row.get("Senast nämnd"), errors="coerce")
    if pd.isna(latest):
        recency = 10.0
    else:
        age_days = max((now - pd.Timestamp(latest).tz_localize(None)).total_seconds() / 86400.0, 0.0)
        recency = max(0.0, 35.0 - min(age_days, 14.0) * 2.5)
    score = min(35.0, mentions * 10.0) + min(30.0, sources * 15.0) + recency
    return round(min(score, 100.0), 1)


def build_verified_ideas(mentions: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
    if mentions.empty or scored.empty:
        return pd.DataFrame()
    keep = [c for c in [
        "Ticker", "Namn", "Pris", "Valuta", "Borsify Score", "INVEST Score", "SWING Score", "REVERSAL Score",
        "Värdering", "Kvalitet", "Risk", "Direktavkastning", "P/E", "ROE", "Skuld/eget kapital", "Riskflaggor", "Datatäckning"
    ] if c in scored.columns]
    merged = mentions.merge(scored[keep], on="Ticker", how="left", suffixes=("", "_score"))
    merged["Upptäcktsstyrka"] = merged.apply(discovery_strength, axis=1)

    def verdict(r: pd.Series) -> tuple[str, str]:
        b = float(pd.to_numeric(r.get("Borsify Score"), errors="coerce")) if pd.notna(pd.to_numeric(r.get("Borsify Score"), errors="coerce")) else np.nan
        q = float(pd.to_numeric(r.get("Kvalitet"), errors="coerce")) if pd.notna(pd.to_numeric(r.get("Kvalitet"), errors="coerce")) else np.nan
        risk = float(pd.to_numeric(r.get("Risk"), errors="coerce")) if pd.notna(pd.to_numeric(r.get("Risk"), errors="coerce")) else np.nan
        cov = float(pd.to_numeric(r.get("Datatäckning"), errors="coerce")) if pd.notna(pd.to_numeric(r.get("Datatäckning"), errors="coerce")) else np.nan
        if not np.isfinite(b):
            return "Kan inte verifieras", "Aktien nämns externt men Borsify saknar tillräcklig marknadsdata för kontroll."
        if np.isfinite(cov) and cov < 0.45:
            return "För lite data", "Det finns för lite fundamental data för att ge idén grönt ljus."
        if b >= 70 and (not np.isfinite(q) or q >= 55) and (not np.isfinite(risk) or risk >= 50):
            return "Klarar första kontrollen", "Externt uppslag + Borsifys nyckeltal ger ett tillräckligt bra första underlag för vidare analys."
        if b >= 60:
            return "Värd att undersöka", "Idén är inte bortsorterad, men siffrorna är inte starka nog för en tydlig kvalitetsstämpel."
        return "Uppslag, inte fynd", "Aktien diskuteras eller syns i media, men Borsifys nyckeltal ger inte stöd för att lyfta den just nu."

    verdicts = merged.apply(verdict, axis=1, result_type="expand")
    merged["Borsify-granskning"] = verdicts[0]
    merged["Förklaring"] = verdicts[1]
    order = {"Klarar första kontrollen": 0, "Värd att undersöka": 1, "För lite data": 2, "Uppslag, inte fynd": 3, "Kan inte verifieras": 4}
    merged["_order"] = merged["Borsify-granskning"].map(order).fillna(9)
    return merged.sort_values(["_order", "Upptäcktsstyrka", "Borsify Score"], ascending=[True, False, False]).drop(columns=["_order"]).reset_index(drop=True)
