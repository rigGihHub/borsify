from __future__ import annotations

from datetime import date, datetime, time
from hashlib import sha1
from typing import Any, Iterable


def _dt(value: Any) -> datetime | None:
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        try:
            parsed = datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed


def change_key(ticker: str, kind: str, headline: str, changed_at: Any, source_key: str = '') -> str:
    """Stable key for review state. Source event keys win when available."""
    if str(source_key or '').strip():
        return f"source:{str(source_key).strip()}"
    occurred = _dt(changed_at)
    stamp = occurred.isoformat(timespec='seconds') if occurred else str(changed_at or '')
    raw = '|'.join([str(ticker).strip().upper(), str(kind).strip(), str(headline).strip(), stamp])
    return 'change:' + sha1(raw.encode('utf-8')).hexdigest()[:20]


def visit_label(last_seen: Any, now: datetime | None = None) -> str:
    previous = _dt(last_seen)
    now = now or datetime.now()
    if previous is None:
        return 'Första besöket'
    delta = max(0.0, (now - previous).total_seconds())
    if delta < 3600:
        mins = max(1, int(delta // 60))
        return f'Sedan förra besöket · cirka {mins} min'
    if previous.date() == now.date():
        hours = max(1, int(delta // 3600))
        return f'Sedan tidigare i dag · cirka {hours} h'
    if (now.date() - previous.date()).days == 1:
        return 'Sedan i går'
    days = max(1, (now.date() - previous.date()).days)
    return f'Sedan senaste besöket · {days} dagar'


def build_since_last_visit(
    last_seen: Any,
    signals: Iterable[dict[str, Any]] | None = None,
    watch_changes: Iterable[dict[str, Any]] | None = None,
    reviewed_keys: Iterable[str] | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return new, timestamped changes not already marked as reviewed.

    This is a navigation/review layer only. It never calculates or modifies an
    investment score. Items without a timestamp are intentionally not called new.
    """
    previous = _dt(last_seen)
    if previous is None:
        return []
    reviewed = {str(x) for x in (reviewed_keys or []) if str(x).strip()}

    pool: list[dict[str, Any]] = []
    for sig in signals or []:
        occurred = _dt(sig.get('created_at') or sig.get('occurred_date'))
        if occurred is None or occurred <= previous:
            continue
        ticker = str(sig.get('symbol') or sig.get('Ticker') or '').strip()
        if not ticker:
            continue
        try:
            priority = int(float(sig.get('priority', 1)))
        except (TypeError, ValueError):
            priority = 1
        headline = str(sig.get('kind') or 'Ny Radar-signal')
        key = change_key(ticker, 'Ny signal', headline, occurred, str(sig.get('event_key') or ''))
        if key in reviewed:
            continue
        pool.append({
            'key': key,
            'ticker': ticker,
            'name': str(sig.get('name') or ticker),
            'kind': 'Ny signal',
            'headline': headline,
            'why': str(sig.get('text') or 'Borsify har registrerat en ny signal.'),
            'changed_at': occurred,
            'rank_score': 60 + min(30, max(1, priority) * 10),
            'target': 'signal',
        })

    for item in watch_changes or []:
        occurred = _dt(item.get('changed_at') or item.get('captured_date'))
        if occurred is None or occurred <= previous:
            continue
        ticker = str(item.get('ticker') or item.get('Ticker') or '').strip()
        if not ticker:
            continue
        tone = str(item.get('tone') or '').lower()
        urgency = 30 if tone in {'negative', 'critical'} else 18 if tone == 'warning' else 8
        headline = str(item.get('status') or 'Caset har förändrats')
        key = change_key(ticker, 'Bevakat case', headline, occurred, str(item.get('event_key') or ''))
        if key in reviewed:
            continue
        pool.append({
            'key': key,
            'ticker': ticker,
            'name': str(item.get('name') or ticker),
            'kind': 'Bevakat case',
            'headline': headline,
            'why': str(item.get('summary') or item.get('why') or 'Borsifys mätbild har förändrats.'),
            'changed_at': occurred,
            'rank_score': 65 + urgency,
            'target': 'journal',
        })

    best: dict[str, dict[str, Any]] = {}
    for item in pool:
        ticker = item['ticker']
        if ticker not in best or (item['rank_score'], item['changed_at']) > (best[ticker]['rank_score'], best[ticker]['changed_at']):
            best[ticker] = item

    ranked = sorted(best.values(), key=lambda x: (-x['rank_score'], -x['changed_at'].timestamp(), x['ticker']))
    return ranked[: max(0, int(limit))]
