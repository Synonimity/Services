-- synon_webhooks schema
-- Run this in your Supabase project's SQL editor before using the module.
--
-- RLS: zero permissive anon/authenticated policies, matching your
-- KerfSuite convention. All access happens server-side via the
-- service_role key (see store.py) — nothing here is exposed to clients.

create table if not exists webhook_events (
    id uuid primary key default gen_random_uuid(),
    provider text not null,
    idempotency_key text not null,
    payload jsonb not null,
    headers jsonb not null default '{}'::jsonb,
    status text not null default 'pending',
    attempt_count integer not null default 0,
    max_retries integer not null default 5,
    next_retry_at timestamptz,
    last_error text,
    received_at timestamptz not null default now(),
    processed_at timestamptz
);

-- Speeds up the idempotency check (provider + key + status + processed_at)
create index if not exists idx_webhook_events_dedupe
    on webhook_events (provider, idempotency_key, status, processed_at);

-- Speeds up the "get due events" query
create index if not exists idx_webhook_events_pending
    on webhook_events (status, next_retry_at)
    where status = 'pending';

alter table webhook_events enable row level security;

-- No policies created intentionally — service_role bypasses RLS by
-- design. If you ever need a client to read its own webhook status,
-- add a narrowly-scoped SELECT policy then, don't default to open.


-- ---------------------------------------------------------------------
-- Atomic claim function
--
-- WHY THIS EXISTS: same race condition as synon_scheduler's
-- claim_jobs() — if two worker ticks overlap (e.g. a slow tick still
-- running when a new one fires), both could SELECT the same rows
-- before either UPDATE lands, and the webhook is processed twice.
-- A single atomic UPDATE ... RETURNING, inside one Postgres function
-- call, closes that window.
-- ---------------------------------------------------------------------

create or replace function claim_webhook_events(
    p_table text,
    p_limit int,
    p_now timestamptz
)
returns setof webhook_events
language plpgsql
as $$
begin
    return query execute format(
        'update %I
         set status = ''processing''
         where id in (
             select id from %I
             where (status = ''pending'' and (next_retry_at is null or next_retry_at <= $1))
             order by received_at
             limit $2
             for update skip locked
         )
         returning *',
        p_table, p_table
    )
    using p_now, p_limit;
end;
$$;
