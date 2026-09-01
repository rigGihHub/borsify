from __future__ import annotations

from datetime import datetime, date, time
from typing import Any, Iterable
import math


MARKET_OPEN = time(9, 0)
MARKET_CLOSE = time(17, 30)


def _num(value: Any) -> float:
    try:
        out = float(value)
        return out if math.isfinite(out) else float('nan')
    except (TypeError, ValueError):
        return float('nan')


def _dt(value: Any) -> datetime | None:
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    try:
        # Avoid a pandas dependency in this small ranking helper.
        text = str(value).strip().replace('Z', '+00:00')
        parsed = datetime.fromisoformat(text)
        return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
    except (TypeError, ValueError):
        return None


def focus_context(now: datetime | None = None) -> dict[str, str]:
    """Return a simple Swedish-market reading context for the overview.

    This is deliberately a UX context, not an exchange calendar. Holidays and
    half-days can differ, so the UI never claims that the exchange is open.
    """
    now = now or datetime.now()
    if now.weekday() >= 5:
        return {
            'phase': 'weekend',
            'title': 'Helgens fokus',
            'intro': 'Det här är det viktigaste att gå igenom inför nästa handelsdag.',
        }
    if now.time() < MARKET_OPEN:
        return {
            'phase': 'preopen',
            'title': 'Inför börsöppning',
            'intro': 'Nytt sedan föregående dag och sådant som är värt att läsa innan handeln normalt börjar.',
        }
    if now.time() <= MARKET_CLOSE:
        return {
            'phase': 'session',
            'title': 'Under dagen',
            'intro': 'Det här har högst läsprioritet just nu. Nya signaler under dagen lyfts före äldre uppslag.',
        }
    return {
        'phase': 'afterclose',
        'title': 'Efter börsdagen',
        'intro': 'Sammanfatta vad som ändrats i dag och vad som bör följas upp inför nästa handelsdag.',
    }


def _freshness_label(value: Any, now: datetime) -> tuple[str, float]:
    parsed = _dt(value)
    if parsed is None:
        return '', 0.0
    # created_at can originate in UTC while Streamlit runs in another timezone.
    # We therefore use broad buckets and never claim minute-level precision.
    delta_hours = max(0.0, (now - parsed).total_seconds() / 3600.0)
    if delta_hours <= 8:
        return 'Nytt i dag', 8.0
    if delta_hours <= 30:
        return 'Sedan i går', 5.0
    if delta_hours <= 72:
        return 'Senaste dagarna', 2.0
    return 'Äldre uppslag', 0.0


def build_daily_focus(
    candidates: Iterable[dict[str, Any]] | None = None,
    watch_changes: Iterable[dict[str, Any]] | None = None,
    signals: Iterable[dict[str, Any]] | None = None,
    limit: int = 3,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Build a small, deduplicated and time-aware action list.

    Time and freshness only influence what to read first. They are not an
    investment score and never change Borsify Score/INVEST/SWING/REVERSAL.
    """
    now = now or datetime.now()
    ctx = focus_context(now)
    pool: list[dict[str, Any]] = []

    for row in candidates or []:
        ticker = str(row.get('Ticker') or row.get('ticker') or '').strip()
        if not ticker:
            continue
        priority = str(row.get('Prioritet') or '').lower()
        relevance = _num(row.get('Dagens relevans'))
        bscore = _num(row.get('Borsify Score'))
        rank_score = 45.0
        if priority == 'hög':
            rank_score += 25
        elif priority == 'medel':
            rank_score += 10
        if math.isfinite(relevance):
            rank_score += min(20.0, max(0.0, relevance) * 0.20)
        if math.isfinite(bscore):
            rank_score += min(10.0, max(0.0, bscore) * 0.10)
        action = 'Öppna analysen och kontrollera styrkor, risker och värdering innan du drar någon slutsats.'
        if ctx['phase'] == 'preopen':
            action = 'Läs analysen före öppning och bestäm i förväg vad som skulle göra caset intressant eller ointressant.'
        elif ctx['phase'] == 'afterclose':
            action = 'Gå igenom analysen efter dagens handel och avgör om aktien ska följas nästa handelsdag.'
        pool.append({
            'ticker': ticker,
            'name': str(row.get('Namn') or ticker),
            'kind': 'Dagens kandidat',
            'rank_score': rank_score,
            'headline': 'Ser mest intressant ut i dagens urval',
            'why': str(row.get('Varför idag') or 'Aktien rankas högt i dagens Borsify-urval.'),
            'action': action,
            'freshness': 'Aktuellt urval',
            'phase': ctx['phase'],
        })

    for item in watch_changes or []:
        ticker = str(item.get('ticker') or item.get('Ticker') or '').strip()
        if not ticker:
            continue
        delta = _num(item.get('score_delta'))
        tone = str(item.get('tone') or '').lower()
        status = str(item.get('status') or 'Bevakat case har förändrats')
        freshness, freshness_bonus = _freshness_label(item.get('changed_at') or item.get('captured_date'), now)
        rank_score = 55.0 + freshness_bonus
        if tone in {'negative', 'critical'}:
            rank_score += 30
        elif tone == 'warning':
            rank_score += 20
        elif tone == 'positive':
            rank_score += 8
        if math.isfinite(delta):
            rank_score += min(15.0, abs(delta))
        pool.append({
            'ticker': ticker,
            'name': str(item.get('name') or ticker),
            'kind': 'Bevakat case',
            'rank_score': rank_score,
            'headline': status,
            'why': str(item.get('summary') or item.get('why') or 'Borsifys mätbild har ändrats sedan du började följa aktien.'),
            'action': str(item.get('action') or 'Jämför med ditt ursprungliga case och kontrollera vad som faktiskt har ändrats.'),
            'freshness': freshness or 'Förändring i case',
            'phase': ctx['phase'],
        })

    for sig in signals or []:
        ticker = str(sig.get('symbol') or sig.get('Ticker') or '').strip()
        if not ticker:
            continue
        priority_num = _num(sig.get('priority'))
        priority = int(priority_num) if math.isfinite(priority_num) else 1
        freshness, freshness_bonus = _freshness_label(sig.get('created_at') or sig.get('occurred_date'), now)
        rank_score = 50.0 + min(30.0, priority * 10.0) + freshness_bonus
        pool.append({
            'ticker': ticker,
            'name': ticker,
            'kind': 'Ny signal',
            'rank_score': rank_score,
            'headline': str(sig.get('kind') or 'Ny Radar-signal'),
            'why': str(sig.get('text') or 'Borsify har registrerat en ny signal för aktien.'),
            'action': 'Kontrollera signalen och den fulla aktieanalysen innan du agerar.',
            'freshness': freshness or 'Ny signal',
            'phase': ctx['phase'],
        })

    # Keep the strongest reason per ticker so one company cannot occupy the whole list.
    best_by_ticker: dict[str, dict[str, Any]] = {}
    for item in pool:
        key = item['ticker']
        if key not in best_by_ticker or item['rank_score'] > best_by_ticker[key]['rank_score']:
            best_by_ticker[key] = item

    ranked = sorted(best_by_ticker.values(), key=lambda x: (-x['rank_score'], x['ticker']))
    return ranked[: max(0, int(limit))]
