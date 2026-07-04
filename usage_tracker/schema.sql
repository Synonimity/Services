-- synon_usage_tracker schema
-- Only needed if you're using SupabaseBackend. InMemoryBackend needs nothing.

create table if not exists usage_events (
    id              bigint generated always as identity primary key,
    user_id         text not null,
    session_id      text,
    model           text not null,
    input_tokens    integer not null default 0,
    output_tokens   integer not null default 0,
    cost            numeric(12, 6) not null default 0,
    created_at      timestamptz not null default now()
);

create index if not exists idx_usage_events_user_created
    on usage_events (user_id, created_at);

-- RLS: locked down by default. All access should go through your server
-- using the service_role key (adminClient pattern), never anon/authenticated
-- direct access - consistent with the rest of KerfSuite's RLS posture.
alter table usage_events enable row level security;
