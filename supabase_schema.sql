-- Borsify v2.0.1 – kompatibel med v1.7-schema; kör i Supabase SQL Editor vid uppgradering från äldre version.
create table if not exists public.watchlist (
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  note text not null default '',
  target_price double precision,
  signal_score_threshold double precision not null default 75,
  signal_score_move double precision not null default 8,
  signal_daily_drop double precision not null default 5,
  added_at timestamptz not null default now(),
  primary key (user_id, symbol)
);

create table if not exists public.score_history (
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  score double precision not null,
  profile text not null,
  captured_date date not null default current_date,
  created_at timestamptz not null default now(),
  primary key (user_id, symbol, profile, captured_date)
);

-- v1.7 explainability: component history for watched shares
alter table public.score_history add column if not exists valuation double precision;
alter table public.score_history add column if not exists quality double precision;
alter table public.score_history add column if not exists setup double precision;
alter table public.score_history add column if not exists income double precision;
alter table public.score_history add column if not exists risk double precision;
alter table public.score_history add column if not exists coverage double precision;

create table if not exists public.radar_history (
  user_id uuid not null references auth.users(id) on delete cascade,
  symbol text not null,
  profile text not null,
  rank integer not null,
  score double precision not null,
  captured_date date not null default current_date,
  created_at timestamptz not null default now(),
  primary key (user_id, symbol, profile, captured_date)
);

alter table public.watchlist enable row level security;
alter table public.score_history enable row level security;
alter table public.radar_history enable row level security;

drop policy if exists "watchlist_select_own" on public.watchlist;
create policy "watchlist_select_own" on public.watchlist for select using (auth.uid() = user_id);
drop policy if exists "watchlist_insert_own" on public.watchlist;
create policy "watchlist_insert_own" on public.watchlist for insert with check (auth.uid() = user_id);
drop policy if exists "watchlist_update_own" on public.watchlist;
create policy "watchlist_update_own" on public.watchlist for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "watchlist_delete_own" on public.watchlist;
create policy "watchlist_delete_own" on public.watchlist for delete using (auth.uid() = user_id);

drop policy if exists "score_select_own" on public.score_history;
create policy "score_select_own" on public.score_history for select using (auth.uid() = user_id);
drop policy if exists "score_insert_own" on public.score_history;
create policy "score_insert_own" on public.score_history for insert with check (auth.uid() = user_id);
drop policy if exists "score_update_own" on public.score_history;
create policy "score_update_own" on public.score_history for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "score_delete_own" on public.score_history;
create policy "score_delete_own" on public.score_history for delete using (auth.uid() = user_id);


drop policy if exists "radar_select_own" on public.radar_history;
create policy "radar_select_own" on public.radar_history for select using (auth.uid() = user_id);
drop policy if exists "radar_insert_own" on public.radar_history;
create policy "radar_insert_own" on public.radar_history for insert with check (auth.uid() = user_id);
drop policy if exists "radar_update_own" on public.radar_history;
create policy "radar_update_own" on public.radar_history for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "radar_delete_own" on public.radar_history;
create policy "radar_delete_own" on public.radar_history for delete using (auth.uid() = user_id);


-- v1.5 migrations for existing projects
alter table public.watchlist add column if not exists signal_score_threshold double precision not null default 75;
alter table public.watchlist add column if not exists signal_score_move double precision not null default 8;
alter table public.watchlist add column if not exists signal_daily_drop double precision not null default 5;

create table if not exists public.signal_history (
  user_id uuid not null references auth.users(id) on delete cascade,
  event_key text not null,
  symbol text not null,
  kind text not null,
  text text not null,
  priority integer not null default 1,
  profile text not null,
  occurred_date date not null default current_date,
  is_read boolean not null default false,
  created_at timestamptz not null default now(),
  primary key (user_id, event_key)
);
alter table public.signal_history enable row level security;
drop policy if exists "signal_select_own" on public.signal_history;
create policy "signal_select_own" on public.signal_history for select using (auth.uid() = user_id);
drop policy if exists "signal_insert_own" on public.signal_history;
create policy "signal_insert_own" on public.signal_history for insert with check (auth.uid() = user_id);
drop policy if exists "signal_update_own" on public.signal_history;
create policy "signal_update_own" on public.signal_history for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "signal_delete_own" on public.signal_history;
create policy "signal_delete_own" on public.signal_history for delete using (auth.uid() = user_id);

-- v1.6 migrations: e-postnotiser och leveransstatus
alter table public.signal_history add column if not exists email_sent_at timestamptz;

create table if not exists public.notification_preferences (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email_enabled boolean not null default false,
  email text not null default '',
  min_priority smallint not null default 2 check (min_priority between 1 and 3),
  notify_kinds text[] not null default array[
    'Ny i topp 10',
    'Score lyfter',
    'Scoregräns passerad',
    'Målkurs nådd',
    'Kraftigt dagsfall',
    'Score faller'
  ]::text[],
  updated_at timestamptz not null default now()
);

alter table public.notification_preferences enable row level security;
drop policy if exists "notification_preferences_select_own" on public.notification_preferences;
create policy "notification_preferences_select_own" on public.notification_preferences for select using (auth.uid() = user_id);
drop policy if exists "notification_preferences_insert_own" on public.notification_preferences;
create policy "notification_preferences_insert_own" on public.notification_preferences for insert with check (auth.uid() = user_id);
drop policy if exists "notification_preferences_update_own" on public.notification_preferences;
create policy "notification_preferences_update_own" on public.notification_preferences for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "notification_preferences_delete_own" on public.notification_preferences;
create policy "notification_preferences_delete_own" on public.notification_preferences for delete using (auth.uid() = user_id);

-- v2.21.0 Case-breaker rules on watched shares.
-- 0 means disabled. Safe to run repeatedly.
alter table public.watchlist add column if not exists breaker_min_score double precision not null default 0;
alter table public.watchlist add column if not exists breaker_min_quality double precision not null default 0;
alter table public.watchlist add column if not exists breaker_min_risk double precision not null default 0;
alter table public.watchlist add column if not exists breaker_max_score_drop double precision not null default 0;

-- v2.25.0: persistent marker used by "Nytt sedan sist".
-- Safe to run repeatedly. RLS keeps each user's visit marker private.
create table if not exists public.visit_state (
  user_id uuid primary key references auth.users(id) on delete cascade,
  last_seen_at timestamptz not null default now()
);
alter table public.visit_state enable row level security;
drop policy if exists "visit_state_select_own" on public.visit_state;
create policy "visit_state_select_own" on public.visit_state for select using (auth.uid() = user_id);
drop policy if exists "visit_state_insert_own" on public.visit_state;
create policy "visit_state_insert_own" on public.visit_state for insert with check (auth.uid() = user_id);
drop policy if exists "visit_state_update_own" on public.visit_state;
create policy "visit_state_update_own" on public.visit_state for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- v2.26.0: explicit review state for "Nytt sedan sist".
-- Safe to run repeatedly. Review state is private per authenticated user.
create table if not exists public.reviewed_changes (
  user_id uuid not null references auth.users(id) on delete cascade,
  change_key text not null,
  reviewed_at timestamptz not null default now(),
  primary key (user_id, change_key)
);
alter table public.reviewed_changes enable row level security;
drop policy if exists "reviewed_changes_select_own" on public.reviewed_changes;
create policy "reviewed_changes_select_own" on public.reviewed_changes for select using (auth.uid() = user_id);
drop policy if exists "reviewed_changes_insert_own" on public.reviewed_changes;
create policy "reviewed_changes_insert_own" on public.reviewed_changes for insert with check (auth.uid() = user_id);
drop policy if exists "reviewed_changes_delete_own" on public.reviewed_changes;
create policy "reviewed_changes_delete_own" on public.reviewed_changes for delete using (auth.uid() = user_id);


-- v2.35.0: Recommendation Ledger + frozen point-in-time outcomes.
-- All daily finalists are stored, not only promoted cases, to reduce selection bias.
create table if not exists public.recommendation_ledger (
  user_id uuid not null references auth.users(id) on delete cascade,
  record_id text not null,
  symbol text not null,
  name text not null default '',
  horizon_type text not null check (horizon_type in ('short','long')),
  model_version text not null,
  profile text not null,
  market text not null,
  rank integer not null,
  entry_price double precision not null,
  gate text not null default '',
  score double precision,
  confidence double precision,
  evidence_count integer,
  why_now text not null default '',
  primary_catalyst text not null default '',
  captured_date date not null,
  captured_at timestamptz not null,
  snapshot_json text not null default '{}',
  primary key (user_id, record_id)
);
alter table public.recommendation_ledger enable row level security;
drop policy if exists "recommendation_ledger_select_own" on public.recommendation_ledger;
create policy "recommendation_ledger_select_own" on public.recommendation_ledger for select using (auth.uid() = user_id);
drop policy if exists "recommendation_ledger_insert_own" on public.recommendation_ledger;
create policy "recommendation_ledger_insert_own" on public.recommendation_ledger for insert with check (auth.uid() = user_id);
drop policy if exists "recommendation_ledger_update_own" on public.recommendation_ledger;
create policy "recommendation_ledger_update_own" on public.recommendation_ledger for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

create table if not exists public.recommendation_outcomes (
  user_id uuid not null references auth.users(id) on delete cascade,
  record_id text not null,
  symbol text not null,
  horizon text not null,
  trading_days integer not null,
  evaluated_date date not null,
  evaluated_price double precision not null,
  return_pct double precision not null,
  positive boolean not null default false,
  gain_10 boolean not null default false,
  loss_10 boolean not null default false,
  evaluated_at timestamptz not null default now(),
  primary key (user_id, record_id, horizon)
);
alter table public.recommendation_outcomes enable row level security;
drop policy if exists "recommendation_outcomes_select_own" on public.recommendation_outcomes;
create policy "recommendation_outcomes_select_own" on public.recommendation_outcomes for select using (auth.uid() = user_id);
drop policy if exists "recommendation_outcomes_insert_own" on public.recommendation_outcomes;
create policy "recommendation_outcomes_insert_own" on public.recommendation_outcomes for insert with check (auth.uid() = user_id);
drop policy if exists "recommendation_outcomes_update_own" on public.recommendation_outcomes;
create policy "recommendation_outcomes_update_own" on public.recommendation_outcomes for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

create index if not exists recommendation_ledger_user_date_idx
  on public.recommendation_ledger(user_id, captured_date desc);
create index if not exists recommendation_outcomes_user_symbol_idx
  on public.recommendation_outcomes(user_id, symbol, evaluated_date desc);


-- v2.37.0: per-user OpenAI usage and estimated cost meter.
create table if not exists public.ai_usage (
  user_id uuid not null references auth.users(id) on delete cascade,
  request_id text not null,
  symbol text not null default '',
  model text not null,
  input_tokens bigint not null default 0,
  output_tokens bigint not null default 0,
  cost_usd double precision not null default 0,
  created_at timestamptz not null default now(),
  primary key (user_id, request_id)
);
alter table public.ai_usage enable row level security;
drop policy if exists "ai_usage_select_own" on public.ai_usage;
create policy "ai_usage_select_own" on public.ai_usage for select using (auth.uid() = user_id);
drop policy if exists "ai_usage_insert_own" on public.ai_usage;
create policy "ai_usage_insert_own" on public.ai_usage for insert with check (auth.uid() = user_id);
drop policy if exists "ai_usage_update_own" on public.ai_usage;
create policy "ai_usage_update_own" on public.ai_usage for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create index if not exists ai_usage_user_created_idx
  on public.ai_usage(user_id, created_at desc);
