-- Run this in the Supabase SQL editor before starting the service.

create extension if not exists "uuid-ossp";

create table if not exists projects (
    id uuid primary key default gen_random_uuid(),
    slug varchar(50) unique not null,
    name varchar(150) not null,
    description text not null default '',
    template_keys jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists project_api_keys (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects (id) on delete cascade,
    label varchar(100) not null,
    key_hash varchar(64) unique not null,
    can_write boolean not null default false,
    created_at timestamptz not null default now(),
    last_used_at timestamptz,
    revoked_at timestamptz
);

create index if not exists ix_project_api_keys_project on project_api_keys (project_id);

create table if not exists secrets (
    id uuid primary key default gen_random_uuid(),
    project_id uuid not null references projects (id) on delete cascade,
    environment varchar(30) not null,
    key varchar(150) not null,
    encrypted_value text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint uq_secret_scope unique (project_id, environment, key)
);

create index if not exists ix_secrets_project_env on secrets (project_id, environment);

create table if not exists audit_log (
    id uuid primary key default gen_random_uuid(),
    project_id uuid,
    actor varchar(100) not null,
    action varchar(50) not null,
    environment varchar(30),
    key_name varchar(150),
    created_at timestamptz not null default now()
);

create index if not exists ix_audit_log_project on audit_log (project_id, created_at desc);

-- Same RLS lockdown pattern as the other services - and arguably more
-- important here than anywhere else, since this table holds encrypted
-- secrets for every other project. Lock it out of Supabase's PostgREST
-- API entirely; only this service's direct DB connection can reach it.
alter table projects enable row level security;
alter table project_api_keys enable row level security;
alter table secrets enable row level security;
alter table audit_log enable row level security;
