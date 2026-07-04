-- synon_context_assembler schema
-- Only needed if you're using SupabaseBackend. InMemoryBackend needs nothing.

create table if not exists context_facts (
    user_id     text not null,
    key         text not null,
    value       text not null,
    updated_at  timestamptz not null default now(),
    primary key (user_id, key)
);

create table if not exists context_history (
    id          bigint generated always as identity primary key,
    session_id  text not null,
    role        text not null check (role in ('user', 'assistant', 'system')),
    content     text not null,
    created_at  timestamptz not null default now()
);

create index if not exists idx_context_history_session
    on context_history (session_id, created_at);

-- RLS: locked down by default. All access should go through your server
-- using the service_role key (adminClient pattern), never anon/authenticated
-- direct access, consistent with the rest of KerfSuite's RLS posture.
alter table context_facts enable row level security;
alter table context_history enable row level security;
