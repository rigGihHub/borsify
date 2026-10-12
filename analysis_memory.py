"""Backup/restore of analysis facts. Existing baselines never get overwritten."""
import json
import sqlite3
from datetime import datetime
import math

TABLES = {
    'research_rotation': ('symbol', 'attempted', 'payload'),
    'holding_review_baselines': ('holding_id', 'captured', 'payload'),
}


def export_memory(db_path, holding_ids=(), baseline_db_path=None):
    result = {'version': 1, 'tables': {}}
    for table, columns in TABLES.items():
        target = baseline_db_path if table == 'holding_review_baselines' and baseline_db_path else db_path
        with sqlite3.connect(target, timeout=10) as conn:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            rows = conn.execute(f"SELECT {','.join(columns)} FROM {table}").fetchall() if exists else []
            if table == 'holding_review_baselines':
                allowed = set(map(int, holding_ids))
                rows = [r for r in rows if int(r[0]) in allowed]
            result['tables'][table] = [dict(zip(columns, r)) for r in rows]
    return result


def restore_memory(db_path, payload, holding_ids=(), baseline_db_path=None):
    if not isinstance(payload, dict) or payload.get('version') != 1:
        raise ValueError('Okänt säkerhetskopieformat')
    allowed = set(map(int, holding_ids)); validated = {}
    for table, columns in TABLES.items():
        rows = payload.get('tables', {}).get(table, [])
        if not isinstance(rows, list) or len(rows) > 10000:
            raise ValueError('Ogiltigt antal rader')
        validated[table] = []
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(columns):
                raise ValueError('Ogiltiga fält')
            # Invalid nested JSON is rejected before any database change.
            nested = json.loads(row['payload'])
            if table == 'research_rotation':
                datetime.fromisoformat(row['attempted'])
                if not isinstance(nested, dict) or not isinstance(nested.get('row'), dict):
                    raise ValueError('Ogiltigt bolagsunderlag')
                datetime.fromisoformat(nested['saved'])
                if str(nested['row'].get('Ticker', '')).upper() != str(row['symbol']).upper():
                    raise ValueError('Bolagsidentiteten stämmer inte')
            else:
                datetime.fromisoformat(row['captured'])
                if not isinstance(nested, list):
                    raise ValueError('Ogiltiga basvärden')
                for point in nested:
                    if not isinstance(point, dict) or not {'Fält', 'Utgångsvärde', 'Underlagsdatum', 'regel', 'gräns', 'Mått', 'Ompröva om'}.issubset(point):
                        raise ValueError('Ofullständiga basvärden')
                    if not math.isfinite(float(point['Utgångsvärde'])) or point['regel'] not in {'negative','drop','increase'}:
                        raise ValueError('Ogiltig bevakningsregel')
            if table == 'holding_review_baselines' and int(row['holding_id']) not in allowed:
                continue
            validated[table].append(tuple(row[c] for c in columns))
    for table, columns in TABLES.items():
        target = baseline_db_path if table == 'holding_review_baselines' and baseline_db_path else db_path
        with sqlite3.connect(target, timeout=10) as conn:
            if table == 'research_rotation':
                conn.execute('CREATE TABLE IF NOT EXISTS research_rotation (symbol TEXT PRIMARY KEY, attempted TEXT NOT NULL, payload TEXT NOT NULL)')
            else:
                conn.execute('CREATE TABLE IF NOT EXISTS holding_review_baselines (holding_id INTEGER PRIMARY KEY, captured TEXT, payload TEXT)')
            placeholders = ','.join('?' for _ in columns)
            conn.executemany(f"INSERT OR IGNORE INTO {table} ({','.join(columns)}) VALUES ({placeholders})", validated[table])


def cloud_restore(client, user_id, db_path, holding_ids=(), baseline_db_path=None):
    if client is None or not user_id:
        return False
    rows = client.table('analysis_memory').select('payload').eq('user_id', user_id).eq('memory_key', 'research-v1').limit(1).execute().data or []
    if rows:
        restore_memory(db_path, rows[0]['payload'], holding_ids, baseline_db_path)
    return bool(rows)


def cloud_save(client, user_id, db_path, holding_ids=(), baseline_db_path=None):
    if client is None or not user_id:
        return False
    payload = export_memory(db_path, holding_ids, baseline_db_path)
    client.table('analysis_memory').upsert({'user_id': user_id, 'memory_key': 'research-v1', 'payload': payload}, on_conflict='user_id,memory_key').execute()
    return True
