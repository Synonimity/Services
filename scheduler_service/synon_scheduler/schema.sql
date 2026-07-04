-- synon_scheduler schema
-- Run this in your Supabase project's SQL editor before using the module.
--
-- RLS: zero permissive anon/authenticated policies, matching your
-- KerfSuite convention. All access happens server-side via the
-- service_role key.

create table if not exists scheduled_jobs (
    id uuid primary key default gen_random_uuid(),
    job_type text not null,
    payload jsonb not null default '{}'::jsonb,
    status text not null default 'pending',
    run_at timestamptz not null default now(),
    attempt_count integer not null default 0,
    max_retries integer not null default 5,
    last_error text,
    claimed_at timestamptz,
    created_at timestamptz not null default now(),
    completed_at timestamptz
);

create table if not exists recurring_jobs (
    id uuid primary key default gen_random_uuid(),
    job_type text not null unique,
    interval_seconds integer not null,
    payload jsonb not null default '{}'::jsonb,
    enabled boolean not null default true,
    next_run_at timestamptz not null default now(),
    last_run_at timestamptz
);

-- Speeds up "get due jobs" — the hot path, runs every worker tick
create index if not exists idx_scheduled_jobs_pending
    on scheduled_jobs (status, run_at)
    where status = 'pending';

create index if not exists idx_recurring_jobs_due
    on recurring_jobs (enabled, next_run_at)
    where enabled = true;

alter table scheduled_jobs enable row level security;
alter table recurring_jobs enable row level security;

-- No policies created intentionally — service_role bypasses RLS by
-- design, same as synon_webhooks. Add narrowly-scoped policies only
-- if a client ever needs direct read access.


-- ---------------------------------------------------------------------
-- Atomic claim function
--
-- WHY THIS EXISTS: a plain "SELECT due jobs, then UPDATE to running"
-- has a race window — if two worker ticks overlap (a slow tick still
-- running when a new one fires), both could SELECT the same rows
-- before either UPDATE lands, and the job runs twice. Wrapping the
-- select+update in a single UPDATE ... RETURNING, inside one
-- Postgres function call, closes that window: Postgres guarantees
-- the UPDATE itself is atomic, so only one caller can claim a given
-- row.
--
-- p_stale_cutoff exists so a job stuck in 'running' because a worker
-- crashed mid-job doesn't sit claimed forever — after
-- JOB_CLAIM_TIMEOUT_MINUTES it becomes claimable again.
-- ---------------------------------------------------------------------

create or replace function claim_jobs(
    p_table text,
    p_limit int,
    p_now timestamptz,
    p_stale_cutoff timestamptz
)
returns setof scheduled_jobs
language plpgsql
as $$
begin
    return query execute format(
        'update %I
         set status = ''running'', claimed_at = $1
         where id in (
             select id from %I
             where (status = ''pending'' and run_at <= $1)
                or (status = ''running'' and claimed_at <= $2)
             order by run_at
             limit $3
             for update skip locked
         )
         returning *',
        p_table, p_table
    )
    using p_now, p_stale_cutoff, p_limit;
end;
$$;
