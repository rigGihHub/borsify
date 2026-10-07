"""Persistent breadth: successful evidence and failed attempts have separate meaning."""
import json
import sqlite3
from datetime import datetime, timezone, timedelta
import pandas as pd


def _init(conn):
    conn.execute('CREATE TABLE IF NOT EXISTS research_rotation (symbol TEXT PRIMARY KEY, attempted TEXT NOT NULL, payload TEXT NOT NULL)')


def rotation_candidates(frame, db_path, limit=4):
    if frame.empty or limit <= 0:
        return frame.iloc[:0].copy()
    with sqlite3.connect(db_path, timeout=10) as conn:
        _init(conn)
        history = dict(conn.execute('SELECT symbol, attempted FROM research_rotation'))
    work = frame.drop_duplicates('Ticker').copy()
    work['_rotation_symbol'] = work['Ticker'].astype(str).str.upper().str.strip()
    work = work[work['_rotation_symbol'].ne('')]
    work['_last_attempt'] = work['_rotation_symbol'].map(history).fillna('')
    return work.sort_values(['_last_attempt', '_rotation_symbol'], kind='stable').head(limit).drop(columns=['_last_attempt', '_rotation_symbol'])


def save_research_batch(frame, db_path, now=None):
    stamp = (now or datetime.now(timezone.utc)).isoformat()
    # JSON via pandas converts NaN to null and timestamps to ISO strings.
    records = json.loads(frame.drop(columns=['_history'], errors='ignore').to_json(orient='records', date_format='iso', default_handler=str))
    with sqlite3.connect(db_path, timeout=10) as conn:
        _init(conn)
        for row in records:
            symbol = str(row.get('Ticker', '')).upper().strip()
            if not symbol:
                continue
            old = conn.execute('SELECT payload FROM research_rotation WHERE symbol=?', (symbol,)).fetchone()
            # Keep last successful facts when a later network request fails.
            if not row.get('Historik år') and old:
                payload = old[0]
            else:
                payload = json.dumps({'saved': stamp, 'row': row}, ensure_ascii=False)
            conn.execute('INSERT OR REPLACE INTO research_rotation VALUES (?, ?, ?)', (symbol, stamp, payload))


def cached_research(db_path, now=None):
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=7)
    with sqlite3.connect(db_path, timeout=10) as conn:
        _init(conn)
        payloads = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM research_rotation')]
    rows = [p['row'] for p in payloads if datetime.fromisoformat(p['saved']) >= cutoff and p['row'].get('Historik år')]
    return pd.DataFrame(rows)
