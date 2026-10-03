"""Scheduled outcome follow-up. Never sends messages or rewrites captures/outcomes."""
import json
import os
import pandas as pd
from recommendation_ledger import evaluate_record_from_history, horizons_for_record, target_date


def evaluate_due_records(records, existing_keys, history_for, benchmark_for, as_of=None, limit=40):
    now = pd.Timestamp(as_of or pd.Timestamp.now(tz='UTC'))
    naive = now.tz_localize(None) if now.tzinfo else now
    results = []; checked = 0
    for record in records:
        try:
            frozen = json.loads(record.get('snapshot_json') or '{}')
        except (TypeError, ValueError):
            continue
        if not isinstance(frozen, dict) or frozen.get('PIT Outcome Basis') != 'next_session_close_total_return_v1':
            continue
        due = [h for h, days in horizons_for_record(record).items()
               if naive.normalize() >= target_date(record['captured_date'], days).normalize() + pd.Timedelta(days=4)
               and (record['record_id'], h) not in existing_keys]
        if not due:
            continue
        if checked >= limit:
            break
        checked += 1
        history = history_for(record['symbol'], record['captured_date'])
        if history.empty:
            continue
        symbol, name, benchmark = benchmark_for(record['market'], record['captured_date'])
        for outcome in evaluate_record_from_history(record, history, as_of=now, benchmark_history=benchmark, benchmark_symbol=symbol, benchmark_name=name):
            if outcome['horizon'] in due:
                results.append({'user_id': record['user_id'], **outcome})
    return results


def main():
    from supabase import create_client
    import app as core
    url = os.getenv('BORSIFY_SUPABASE_URL', '').strip()
    key = os.getenv('BORSIFY_SUPABASE_SERVICE_ROLE_KEY', '').strip()
    if not url or not key:
        print('Prospective follow-up is not configured: Supabase server credentials are missing.')
        return 1
    client = create_client(url, key)
    records=[]; existing=set()
    for table, destination in [('recommendation_ledger', records), ('recommendation_outcomes', existing)]:
        offset=0
        while True:
            columns='*' if table=='recommendation_ledger' else 'user_id,record_id,horizon'
            query=client.table(table).select(columns).order('record_id').order('user_id')
            if table=='recommendation_outcomes': query=query.order('horizon')
            query=query.range(offset,offset+499)
            page=query.execute().data or []
            if table=='recommendation_ledger': destination.extend(page)
            else: destination.update((r['user_id'],r['record_id'],r['horizon']) for r in page)
            if len(page)<500: break
            offset+=500
    records.sort(key=lambda r:r['captured_date'])
    # Outcome keys include users; each user's capture remains isolated.
    total=0
    for uid in sorted({r['user_id'] for r in records}):
        cohort=[r for r in records if r['user_id']==uid]
        keys={(rid,h) for user,rid,h in existing if user==uid}
        def benchmark_for(market, date):
            symbol,name=core._ledger_benchmark_for_market(market)
            return symbol,name,core.fetch_ledger_benchmark_history(symbol,date)
        rows=evaluate_due_records(cohort,keys,core.fetch_ledger_history,benchmark_for)
        if rows:
            client.table('recommendation_outcomes').upsert(rows,on_conflict='user_id,record_id,horizon',ignore_duplicates=True).execute()
            total+=len(rows)
    print(f'Prospective follow-up: {total} previously missing outcomes saved.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())
