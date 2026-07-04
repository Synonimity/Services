-- Run this in the Supabase SQL editor before starting the service.

create extension if not exists "uuid-ossp";

create table if not exists log_entries (
    id uuid primary key default gen_random_uuid(),
    service_name varchar(100) not null,
    environment varchar(30) not null default 'production',
    level varchar(20) not null,
    message text not null,
    context jsonb not null default '{}'::jsonb,
    external_user_id varchar(255),
    request_id varchar(100),
    created_at timestamptz not null default now()
);

create index if not exists ix_log_entries_service_env on log_entries (service_name, environment);
create index if not exists ix_log_entries_level on log_entries (level);
create index if not exists ix_log_entries_created_at on log_entries (created_at);
create index if not exists ix_log_entries_request_id on log_entries (request_id);

create table if not exists error_issues (
    id uuid primary key default gen_random_uuid(),
    service_name varchar(100) not null,
    environment varchar(30) not null default 'production',
    fingerprint varchar(64) not null,
    exception_type varchar(150) not null,
    title varchar(300) not null,
    status varchar(20) not null default 'open',
    occurrence_count integer not null default 0,
    first_seen timestamptz not null default now(),
    last_seen timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_issue_fingerprint unique (service_name, environment, fingerprint)
);

create index if not exists ix_error_issues_status on error_issues (status);
create index if not exists ix_error_issues_last_seen on error_issues (last_seen desc);

create table if not exists error_occurrences (
    id uuid primary key default gen_random_uuid(),
    issue_id uuid not null references error_issues (id) on delete cascade,
    message text not null,
    stack_trace text,
    context jsonb not null default '{}'::jsonb,
    external_user_id varchar(255),
    request_id varchar(100),
    created_at timestamptz not null default now()
);

create index if not exists ix_error_occurrences_issue on error_occurrences (issue_id, created_at desc);

-- Optional: automate log cleanup with Supabase's pg_cron extension
-- instead of an external scheduler hitting DELETE /logs/cleanup.
-- Uncomment after enabling pg_cron in Database > Extensions:
--
-- select cron.schedule(
--   'cleanup-old-logs',
--   '0 3 * * *',  -- daily at 03:00
--   $$ delete from log_entries where created_at < now() - interval '30 days' $$
-- );

-- Same RLS lockdown pattern as the other services.
alter table log_entries enable row level security;
alter table error_issues enable row level security;
alter table error_occurrences enable row level security;
