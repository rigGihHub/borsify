from __future__ import annotations

"""Point-in-time memory for explicit management operating signals.

The memory stores only observed, concrete management signals produced by
``management_signal_layer``. It never backfills historical management language and
it does not turn generic optimism or the absence of news into a historical event.
Identical observed signal sets are de-duplicated with a stable fingerprint so a
repeated scan cannot manufacture a trend.
"""

import hashlib
import sqlite3
from typing import Any

TOPIC_FIELDS: tuple[tuple[str, str], ...] = (
    ("Efterfrågan", "demand"),
    ("Orderläge", "orders"),
    ("Marginal", "margin"),
    ("Prissättning", "pricing"),
    ("Lager", "inventory"),
    ("Investeringar", "investment"),
)


def _clean_date(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if len(text) >= 10 and text[:4].isdigit() else ""


def _topic_set(value: Any) -> set[str]:
    return {x.strip() for x in str(value or "").split(",") if x.strip()}


def _latest_matched_date(catalyst_events: dict[str, Any] | None, matched_titles: set[str]) -> str:
    if not isinstance(catalyst_events, dict) or not matched_titles:
        return ""
    dates: list[str] = []
    news = catalyst_events.get("news")
    if not isinstance(news, list):
        return ""
    for item in news:
        if not isinstance(item, dict) or str(item.get("title") or "").strip() not in matched_titles:
            continue
        date = _clean_date(item.get("published_at") or item.get("providerPublishTime") or item.get("pubDate"))
        if date:
            dates.append(date)
    return max(dates) if dates else ""


def ensure_management_signal_memory_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS management_signal_snapshots (
            symbol TEXT NOT NULL,
            signal_key TEXT NOT NULL,
            signal_date TEXT NOT NULL DEFAULT '',
            captured_date TEXT NOT NULL,
            positive_count INTEGER NOT NULL DEFAULT 0,
            negative_count INTEGER NOT NULL DEFAULT 0,
            demand INTEGER NOT NULL DEFAULT 0,
            orders INTEGER NOT NULL DEFAULT 0,
            margin INTEGER NOT NULL DEFAULT 0,
            pricing INTEGER NOT NULL DEFAULT 0,
            inventory INTEGER NOT NULL DEFAULT 0,
            investment INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT '',
            positive_topics TEXT NOT NULL DEFAULT '',
            negative_topics TEXT NOT NULL DEFAULT '',
            matched_titles TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(symbol, signal_key)
        )
    """)


def snapshot_from_management_signal(
    symbol: str,
    management_signal: dict[str, Any] | None,
    catalyst_events: dict[str, Any] | None,
    captured_date: str,
) -> dict[str, Any] | None:
    s = management_signal or {}
    positives = _topic_set(s.get("Ledningssignal positiva ämnen"))
    negatives = _topic_set(s.get("Ledningssignal negativa ämnen"))
    if not positives and not negatives:
        return None

    matched_titles = {x.strip() for x in str(s.get("Ledningssignal rubriker") or "").split("|") if x.strip()}
    state = {field: (1 if topic in positives else -1 if topic in negatives else 0) for topic, field in TOPIC_FIELDS}
    canonical = "|".join([
        ",".join(sorted(positives)),
        ",".join(sorted(negatives)),
        "||".join(sorted(matched_titles)),
    ])
    signal_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return {
        "symbol": str(symbol or "").strip().upper(),
        "signal_key": signal_key,
        "signal_date": _latest_matched_date(catalyst_events, matched_titles),
        "captured_date": _clean_date(captured_date) or str(captured_date),
        "positive_count": int(s.get("Ledningssignal positiva") or len(positives)),
        "negative_count": int(s.get("Ledningssignal negativa") or len(negatives)),
        **state,
        "status": str(s.get("Ledningssignal status") or ""),
        "positive_topics": ", ".join(sorted(positives)),
        "negative_topics": ", ".join(sorted(negatives)),
        "matched_titles": " | ".join(sorted(matched_titles)),
    }


def previous_management_snapshot(conn: sqlite3.Connection, symbol: str, signal_key: str) -> dict[str, Any] | None:
    ensure_management_signal_memory_table(conn)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT * FROM management_signal_snapshots
        WHERE symbol = ? AND signal_key <> ?
        ORDER BY captured_date DESC, created_at DESC
        LIMIT 1
        """,
        (str(symbol or "").strip().upper(), str(signal_key or "")),
    ).fetchone()
    return dict(row) if row else None


def save_management_snapshot(conn: sqlite3.Connection, snapshot: dict[str, Any] | None) -> None:
    if not snapshot:
        return
    ensure_management_signal_memory_table(conn)
    cols = [
        "symbol", "signal_key", "signal_date", "captured_date", "positive_count", "negative_count",
        "demand", "orders", "margin", "pricing", "inventory", "investment", "status",
        "positive_topics", "negative_topics", "matched_titles",
    ]
    conn.execute(
        f"INSERT OR IGNORE INTO management_signal_snapshots({','.join(cols)}) VALUES ({','.join(['?'] * len(cols))})",
        [snapshot.get(c) for c in cols],
    )


def compare_management_signal_memory(current: dict[str, Any] | None, previous: dict[str, Any] | None) -> dict[str, Any]:
    if not current:
        return {
            "Ledningsminne status": "Ingen konkret ledningssignal att frysa",
            "Ledningsminne historik": False,
            "Ledningsminne positiv": False,
            "Ledningsminne negativ": False,
            "Ledningsminne förklaring": "Borsify sparar inte frånvaro av ledningsuttalanden som historik.",
        }
    if not previous:
        return {
            "Ledningsminne status": "För lite ledningshistorik",
            "Ledningsminne historik": False,
            "Ledningsminne positiv": False,
            "Ledningsminne negativ": False,
            "Ledningsminne signaldatum": current.get("signal_date", ""),
            "Ledningsminne förklaring": "Detta är den första konkreta ledningssignalen som Borsify har fryst för bolaget. Ingen äldre historik återskapas.",
        }

    improving: list[str] = []
    weakening: list[str] = []
    for topic, field in TOPIC_FIELDS:
        old, new = int(previous.get(field) or 0), int(current.get(field) or 0)
        if new > old:
            improving.append(topic)
        elif new < old:
            weakening.append(topic)

    # A topic disappearing from an old headline set is not by itself evidence that
    # management changed its view. Require an explicit new positive/negative state.
    explicit_improving = [t for t in improving if any(t == topic and int(current.get(field) or 0) == 1 for topic, field in TOPIC_FIELDS)]
    explicit_weakening = [t for t in weakening if any(t == topic and int(current.get(field) or 0) == -1 for topic, field in TOPIC_FIELDS)]

    positive = bool(explicit_improving and not explicit_weakening)
    negative = bool(explicit_weakening and not explicit_improving)
    if len(explicit_improving) >= 2 and not explicit_weakening:
        status = "Ledningsspråket stärks brett"
        why = "Nya konkreta ledningsuttalanden är tydligare positiva inom flera operativa områden än föregående frysta signal."
    elif positive:
        status = "Ledningsspråket stärks"
        why = "Minst ett operativt område har skiftat till ett uttryckligen mer positivt ledningsuttalande."
    elif len(explicit_weakening) >= 2 and not explicit_improving:
        status = "Ledningsspråket försvagas brett"
        why = "Nya konkreta ledningsuttalanden är tydligare negativa inom flera operativa områden än föregående frysta signal."
    elif negative:
        status = "Ledningsspråket försvagas"
        why = "Minst ett operativt område har skiftat till ett uttryckligen mer negativt ledningsuttalande."
    elif explicit_improving and explicit_weakening:
        status = "Ledningsspråket är mer blandat"
        why = "Nya explicita ledningsuttalanden förbättras inom vissa områden men försämras inom andra."
    else:
        status = "Ingen tydlig förändring i ledningsspråk"
        why = "Borsify har flera frysta ledningssignaler, men ingen ny explicit polaritetsförändring är tillräckligt tydlig."

    return {
        "Ledningsminne status": status,
        "Ledningsminne historik": True,
        "Ledningsminne positiv": positive,
        "Ledningsminne negativ": negative,
        "Ledningsminne förbättrade ämnen": ", ".join(explicit_improving),
        "Ledningsminne försämrade ämnen": ", ".join(explicit_weakening),
        "Ledningsminne signaldatum": current.get("signal_date", ""),
        "Ledningsminne jämförelsedatum": previous.get("signal_date") or previous.get("captured_date", ""),
        "Ledningsminne förklaring": why,
    }
