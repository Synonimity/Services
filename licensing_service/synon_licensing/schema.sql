-- synon_licensing schema
-- Run this in your Supabase project's SQL editor before using the module.
--
-- RLS: zero permissive anon/authenticated policies, matching your
-- KerfSuite convention. All access happens server-side via the
-- service_role key.

create table if not exists license_keys (
    id uuid primary key default gen_random_uuid(),
    key text not null unique,
    product text not null,
    status text not null default 'active',
    source text not null default 'on_demand',
    bound_machine_id text,
    customer_email text,
    issued_at timestamptz not null default now(),
    revoked_at timestamptz
);

create table if not exists license_key_pool (
    id uuid primary key default gen_random_uuid(),
    key text not null unique,
    product text not null,
    assigned boolean not null default false
);

create table if not exists trial_usage (
    id uuid primary key default gen_random_uuid(),
    license_key_id uuid not null references license_keys(id) on delete cascade,
    max_days integer,
    max_runs integer,
    started_at timestamptz not null default now(),
    run_count integer not null default 0,
    unique (license_key_id)
);

create index if not exists idx_license_keys_lookup
    on license_keys (key, product);

create index if not exists idx_license_pool_unassigned
    on license_key_pool (product, assigned)
    where assigned = false;

alter table license_keys enable row level security;
alter table license_key_pool enable row level security;
alter table trial_usage enable row level security;

-- No policies created intentionally — service_role bypasses RLS by
-- design, same as synon_webhooks/synon_scheduler.


-- ---------------------------------------------------------------------
-- Atomic pool claim function
--
-- WHY THIS EXISTS: same race condition as synon_scheduler's
-- claim_jobs() — if two issuances happen at the same moment (e.g. two
-- PayPal webhooks landing in the same second), a plain SELECT
-- unassigned key then UPDATE assigned=true has a race window where
-- both could select the same row before either UPDATE lands. A single
-- atomic UPDATE ... RETURNING closes that window.
-- ---------------------------------------------------------------------

create or replace function claim_pool_key(
    p_table text,
    p_product text
)
returns table(key text)
language plpgsql
as $$
begin
    return query execute format(
        'update %I
         set assigned = true
         where id = (
             select id from %I
             where product = $1 and assigned = false
             limit 1
             for update skip locked
         )
         returning key',
        p_table, p_table
    )
    using p_product;
end;
$$;
