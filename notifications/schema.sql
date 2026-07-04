-- Run once in the host project's own Supabase project.
-- These tables live alongside the host app's own tables in one DB,
-- which is fine - they don't overlap with anything a typical FastAPI
-- app would already have.

create table if not exists notification_log (
    id uuid primary key default gen_random_uuid(),
    external_user_id varchar(255),
    recipient_email varchar(255) not null,
    template_name varchar(50) not null,
    subject varchar(255) not null,
    status varchar(20) not null default 'queued',
    provider_message_id varchar(100),
    idempotency_key varchar(100) unique,
    error_message varchar(500),
    variables jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists ix_notification_log_external_user_id on notification_log (external_user_id);
create index if not exists ix_notification_log_provider_message_id on notification_log (provider_message_id);

create table if not exists email_events (
    id uuid primary key default gen_random_uuid(),
    notification_id uuid not null references notification_log (id) on delete cascade,
    event_type varchar(30) not null,
    svix_id varchar(100) not null,
    raw_payload jsonb not null,
    created_at timestamptz not null default now()
);

create index if not exists ix_email_events_notification on email_events (notification_id);

-- RLS: notifications are private data, lock them out of Supabase's
-- auto-generated PostgREST API entirely.
alter table notification_log enable row level security;
alter table email_events enable row level security;
