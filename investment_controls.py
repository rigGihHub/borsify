"""Observable portfolio exposure and dated, frozen holding checkpoints."""
import json
import sqlite3
from datetime import datetime, timezone
import math
import pandas as pd


def number(v):
    try:
        n = float(v)
        return n if math.isfinite(n) else math.nan
    except (TypeError, ValueError):
        return math.nan


RULES = (
    ('Omsättningstillväxt', 'Omsättningstillväxt', 'negative', 0),
    ('Vinstmarginal', 'Vinstmarginal', 'drop', .05),
    ('FCF-yield', 'Fritt kassaflöde / börsvärde', 'negative', 0),
    ('Skuld/eget kapital', 'Skuld/eget kapital', 'increase', .25),
)


def checkpoints(row):
    date = str(row.get('Fundamental hämtad') or row.get('Rapportdatum') or '')
    return [{'Mått': label, 'Fält': field, 'Utgångsvärde': number(row.get(field)), 'Underlagsdatum': date or 'Okänt',
             'Ompröva om': 'blir negativt' if rule == 'negative' else ('faller minst 5 procentenheter' if rule == 'drop' else 'ökar minst 25 % från positiv bas'),
             'regel': rule, 'gräns': threshold}
            for field, label, rule, threshold in RULES if math.isfinite(number(row.get(field)))]


def holding_review(holding_id, row, db_path):
    """Freeze at first observed review, never pretend it was the purchase-date thesis."""
    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path, timeout=10) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS holding_review_baselines (holding_id INTEGER PRIMARY KEY, captured TEXT, payload TEXT)')
        previous = conn.execute('SELECT captured, payload FROM holding_review_baselines WHERE holding_id=?', (int(holding_id),)).fetchone()
        if not previous:
            points = checkpoints(row)
            dates = [pd.to_datetime(p['Underlagsdatum'], errors='coerce', utc=True) for p in points]
            if points and all(pd.notna(d) and d <= pd.Timestamp(now) for d in dates):
                conn.execute('INSERT INTO holding_review_baselines VALUES (?,?,?)', (int(holding_id), now, json.dumps(points)))
                previous = (now, json.dumps(points))
        if not previous:
            return [], 'Daterade basvärden saknas; ingen tesuppföljning kan göras.'
    points = json.loads(previous[1]); result = []
    current_date = str(row.get('Fundamental hämtad') or row.get('Rapportdatum') or '')
    for p in points:
        value = number(row.get(p['Fält'])); base = p['Utgångsvärde']
        old = pd.to_datetime(p['Underlagsdatum'], errors='coerce', utc=True)
        new = pd.to_datetime(current_date, errors='coerce', utc=True)
        comparable = math.isfinite(value) and pd.notna(old) and pd.notna(new) and new > old
        broken = comparable and ((p['regel'] == 'negative' and base >= 0 and value < 0)
                   or (p['regel'] == 'drop' and value <= base - p['gräns'])
                   or (p['regel'] == 'increase' and base > 0 and value >= base * 1.25))
        result.append({**p, 'Nu': value, 'Status': 'OMPRÖVA' if broken else ('Ingen tröskel passerad' if comparable else 'Inväntar nyare jämförbart underlag')})
    return result, 'Basvärden sparade vid första granskningen ' + previous[0][:10] + '. Inte en återskapad bedömning från köpdatum. Trösklarna är bevakningsregler, inte automatiska säljorder. Leverantörsmått kan avse olika perioder och måste avstämmas i rapporten.'


def portfolio_exposure(holdings, quotes, candidate=None, amount_sek=0):
    lookup = {str(r['Ticker']).upper(): r for _, r in quotes.iterrows()}
    rows = []; missing = 0
    for _, h in holdings.iterrows():
        symbol = str(h['symbol']).upper(); q = lookup.get(symbol, {})
        value = number(q.get('Pris SEK')) * number(h.get('quantity'))
        if not math.isfinite(value) or value <= 0:
            missing += 1; continue
        rows.append({'Bolag': symbol, 'Sektor': str(q.get('Sektor') or 'Okänd'), 'Bransch': str(q.get('Bransch') or 'Okänd'), 'Noteringsvaluta': str(q.get('Valuta') or 'Okänd'), 'Värde SEK': value})
    if candidate is not None and math.isfinite(amount_sek) and amount_sek > 0:
        rows.append({'Bolag': str(candidate.get('Ticker')), 'Sektor': str(candidate.get('Sektor') or 'Okänd'), 'Bransch': str(candidate.get('Bransch') or 'Okänd'), 'Noteringsvaluta': str(candidate.get('Valuta') or 'Okänd'), 'Värde SEK': amount_sek})
    frame = pd.DataFrame(rows)
    if frame.empty:
        return {}, missing
    total = frame['Värde SEK'].sum()
    return {key: (frame.groupby(key)['Värde SEK'].sum().sort_values(ascending=False) / total * 100).rename('Andel av känt aktievärde %').reset_index() for key in ('Bolag', 'Sektor', 'Bransch', 'Noteringsvaluta')}, missing
