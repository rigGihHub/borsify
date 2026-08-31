from __future__ import annotations

import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IdeaSource:
    name: str
    kind: str
    url: str
    category: str = "Brett flöde"
    weight: float = 1.0


def _google_news_query(query: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=sv&gl=SE&ceid=SE:sv"
    )


# Externa källor används bara som radar för uppslag. De ändrar aldrig Borsify Score.
# Direkt RSS används där en stabil publik feed finns; i övrigt används Google News RSS
# för att undvika skör sid-scraping av respektive mediesajt.
DEFAULT_SOURCES = [
    IdeaSource(
        "EFN · direkt RSS",
        "media",
        "https://efn.se/rss/infront",
        category="Ekonomimedia",
        weight=1.15,
    ),
    IdeaSource(
        "Svensk ekonomimedia · brett",
        "media",
        _google_news_query(
            '(aktie OR börs OR rapport OR utdelning OR riktkurs) '
            '(site:di.se OR site:placera.se OR site:affarsvarlden.se OR site:borskollen.se '
            'OR site:efn.se OR site:privataaffarer.se OR site:dagensps.se OR site:borsvarlden.com)'
        ),
        category="Ekonomimedia",
        weight=1.0,
    ),
    IdeaSource(
        "Analyser & rekommendationer",
        "media",
        _google_news_query(
            '(aktie OR bolag) (analys OR rekommendation OR riktkurs OR köprekommendation OR säljrekommendation) '
            '(site:di.se OR site:placera.se OR site:affarsvarlden.se OR site:borskollen.se '
            'OR site:efn.se OR site:privataaffarer.se OR site:borsvarlden.com)'
        ),
        category="Analys & rekommendation",
        weight=1.05,
    ),
    IdeaSource(
        "Rapporter & bolagshändelser",
        "media",
        _google_news_query(
            '(rapport OR vinstvarning OR utdelning OR insynsköp OR order OR förvärv OR emission) '
            '(site:di.se OR site:placera.se OR site:affarsvarlden.se OR site:borskollen.se '
            'OR site:efn.se OR site:privataaffarer.se OR site:borsvarlden.com)'
        ),
        category="Bolagshändelse",
        weight=1.1,
    ),
    IdeaSource(
        "Forum · Reddit Aktiemarknaden",
        "forum",
        "https://www.reddit.com/r/Aktiemarknaden/new/.rss",
        category="Forum",
        weight=0.65,
    ),
    IdeaSource(
        "Forum · Reddit ISKbets",
        "forum",
        "https://www.reddit.com/r/ISKbets/new/.rss",
        category="Forum · hög spekulationsrisk",
        weight=0.45,
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
            ts = pd.Timestamp(value)
            return ts.tz_localize(None) if ts.tzinfo is not None else ts
        except Exception:
            return pd.NaT


def _fetch_xml(url: str, timeout: int = 8) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Borsify/2.13 (+https://borsify.se; public-feed-reader)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
        return response.read()


def _publisher_from_title(title: str, fallback: str) -> str:
    # Google News brukar lägga publicisten sist i rubriken: "Rubrik - EFN".
    if " - " in title:
        suffix = title.rsplit(" - ", 1)[-1].strip()
        if 2 <= len(suffix) <= 40:
            return suffix
    return fallback


def parse_feed(xml_bytes: bytes, source: IdeaSource, max_items: int = 40) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    rows: list[dict] = []

    for item in root.findall(".//item")[:max_items]:
        title = _clean_html(item.findtext("title") or "")
        summary = _clean_html(item.findtext("description") or "")
        link = (item.findtext("link") or "").strip()
        published = _parse_date(item.findtext("pubDate"))
        xml_publisher = _clean_html(item.findtext("source") or "")
        publisher = xml_publisher or _publisher_from_title(title, source.name)
        rows.append({
            "source": source.name,
            "publisher": publisher,
            "kind": source.kind,
            "category": source.category,
            "source_weight": source.weight,
            "title": title,
            "summary": summary,
            "link": link,
            "published": published,
        })

    if rows:
        return rows

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
        rows.append({
            "source": source.name,
            "publisher": source.name,
            "kind": source.kind,
            "category": source.category,
            "source_weight": source.weight,
            "title": title,
            "summary": summary,
            "link": link,
            "published": published,
        })
    return rows


def fetch_public_idea_flow(
    sources: Iterable[IdeaSource] = DEFAULT_SOURCES,
    max_items_per_source: int = 40,
) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict] = []
    errors: list[str] = []
    for source in sources:
        try:
            rows.extend(parse_feed(_fetch_xml(source.url), source, max_items=max_items_per_source))
        except Exception as exc:
            errors.append(f"{source.name}: {type(exc).__name__}")
    columns = ["source", "publisher", "kind", "category", "source_weight", "title", "summary", "link", "published"]
    if not rows:
        return pd.DataFrame(columns=columns), errors
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
    tokens = _normalize(clean_name).split()
    if tokens and len(tokens[0]) >= 4:
        candidates.append(tokens[0])
    return sorted({x for x in candidates if len(x) >= 3}, key=len, reverse=True)


def _mentioned(text: str, aliases: list[str]) -> bool:
    hay = f" {_normalize(text)} "
    return any(f" {alias} " in hay for alias in aliases)


def map_mentions(feed: pd.DataFrame, stocks: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Ticker", "Namn", "Antal omnämnanden", "Källor", "Forum", "Media", "Senast nämnd",
        "Rubriker", "Mediekällor", "Forumkällor", "Kategorier", "Viktade omnämnanden",
    ]
    if feed.empty or stocks.empty:
        return pd.DataFrame(columns=columns)
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
        publisher_series = m.get("publisher", m["source"]).fillna(m["source"]).astype(str)
        media_mask = m["kind"].eq("media")
        forum_mask = m["kind"].eq("forum")
        headlines = []
        for _, r in m.sort_values("published", ascending=False, na_position="last").head(6).iterrows():
            headlines.append({
                "title": str(r.get("title", "")),
                "source": str(r.get("publisher", r.get("source", ""))),
                "feed": str(r.get("source", "")),
                "category": str(r.get("category", "")),
                "kind": str(r.get("kind", "")),
                "link": str(r.get("link", "")),
                "published": r.get("published"),
            })
        weights = pd.to_numeric(m.get("source_weight", 1.0), errors="coerce").fillna(1.0)
        stock_rows.append({
            "Ticker": ticker,
            "Namn": name,
            "Antal omnämnanden": int(len(m)),
            "Källor": int(publisher_series.nunique()),
            "Forum": int(forum_mask.sum()),
            "Media": int(media_mask.sum()),
            "Senast nämnd": latest,
            "Rubriker": headlines,
            "Mediekällor": int(publisher_series[media_mask].nunique()),
            "Forumkällor": int(publisher_series[forum_mask].nunique()),
            "Kategorier": int(m.get("category", pd.Series(dtype=str)).nunique()),
            "Viktade omnämnanden": float(weights.sum()),
        })
    return pd.DataFrame(stock_rows)


def discovery_strength(row: pd.Series, now: pd.Timestamp | None = None) -> float:
    """Mäter bredd + aktualitet i externa uppslag, inte hur bra investeringen är."""
    now = now or pd.Timestamp.utcnow().tz_localize(None)
    weighted_mentions = float(row.get("Viktade omnämnanden", row.get("Antal omnämnanden", 0)) or 0)
    publishers = float(row.get("Källor", 0) or 0)
    media_publishers = float(row.get("Mediekällor", 0) or 0)
    latest = pd.to_datetime(row.get("Senast nämnd"), errors="coerce")
    if pd.isna(latest):
        recency = 4.0
    else:
        age_days = max((now - pd.Timestamp(latest).tz_localize(None)).total_seconds() / 86400.0, 0.0)
        recency = max(0.0, 24.0 - min(age_days, 12.0) * 2.0)
    score = min(30.0, weighted_mentions * 6.0) + min(36.0, publishers * 12.0) + recency
    if media_publishers >= 2:
        score += 10.0
    # Forum kan hitta idéer snabbt, men många foruminlägg ska inte ensamma ge "stark" upptäckt.
    if media_publishers == 0:
        score = min(score, 68.0)
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
        b_num = pd.to_numeric(r.get("Borsify Score"), errors="coerce")
        q_num = pd.to_numeric(r.get("Kvalitet"), errors="coerce")
        risk_num = pd.to_numeric(r.get("Risk"), errors="coerce")
        cov_num = pd.to_numeric(r.get("Datatäckning"), errors="coerce")
        b = float(b_num) if pd.notna(b_num) else np.nan
        q = float(q_num) if pd.notna(q_num) else np.nan
        risk = float(risk_num) if pd.notna(risk_num) else np.nan
        cov = float(cov_num) if pd.notna(cov_num) else np.nan
        if not np.isfinite(b):
            return "Kan inte verifieras", "Aktien nämns externt men Borsify saknar tillräcklig marknadsdata för kontroll."
        if np.isfinite(cov) and cov < 0.45:
            return "För lite data", "Det finns för lite fundamental data för att ge idén grönt ljus."
        if b >= 70 and (not np.isfinite(q) or q >= 55) and (not np.isfinite(risk) or risk >= 50):
            return "Klarar första kontrollen", "Uppslaget har nu klarat Borsifys första kontroll av pris, kvalitet och risk. Läs ändå vad som faktiskt hänt i bolaget innan du agerar."
        if b >= 60:
            return "Värd att undersöka", "Idén är inte bortsorterad, men siffrorna är inte starka nog för en tydlig kvalitetsstämpel."
        return "Uppslag, inte fynd", "Aktien diskuteras eller syns i media, men Borsifys nyckeltal ger inte stöd för att lyfta den just nu."

    verdicts = merged.apply(verdict, axis=1, result_type="expand")
    merged["Borsify-granskning"] = verdicts[0]
    merged["Förklaring"] = verdicts[1]
    order = {"Klarar första kontrollen": 0, "Värd att undersöka": 1, "För lite data": 2, "Uppslag, inte fynd": 3, "Kan inte verifieras": 4}
    merged["_order"] = merged["Borsify-granskning"].map(order).fillna(9)
    return merged.sort_values(["_order", "Upptäcktsstyrka", "Borsify Score"], ascending=[True, False, False]).drop(columns=["_order"]).reset_index(drop=True)
