-- Borsiq v1.8.0 – kompatibel med v1.7-schema; kör i Supabase SQL Editor vid uppgradering från äldre version.
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
