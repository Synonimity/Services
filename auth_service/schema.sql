-- Run this in the Supabase SQL editor (or via migration tool) before
-- starting the service.

create extension if not exists "uuid-ossp";

create table if not exists users (
    id uuid primary key default gen_random_uuid(),
    username varchar(32) unique not null,
    email varchar(255) unique not null,
    password_hash varchar(255),
    is_active boolean not null default true,
    is_verified boolean not null default false,
    failed_login_attempts integer not null default 0,
    locked_until timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists ix_users_username on users (username);
create index if not exists ix_users_email on users (email);

create table if not exists oauth_accounts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users (id) on delete cascade,
    provider varchar(20) not null,
    provider_user_id varchar(255) not null,
    created_at timestamptz not null default now(),
    constraint uq_provider_account unique (provider, provider_user_id)
);

create table if not exists refresh_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references users (id) on delete cascade,
    token_hash varchar(255) unique not null,
    expires_at timestamptz not null,
    revoked boolean not null default false,
    created_at timestamptz not null default now()
);

create index if not exists ix_refresh_tokens_hash on refresh_tokens (token_hash);

-- IMPORTANT: this service talks to Postgres directly over the database
-- connection string, not through Supabase's auto-generated PostgREST API
-- or the supabase-js client. But Supabase still exposes every table over
-- PostgREST to anyone with your anon/public API key unless Row Level
-- Security is enabled. Lock these tables down so they're reachable only
-- via the direct DB connection this service uses, never via the REST API.
alter table users enable row level security;
alter table oauth_accounts enable row level security;
alter table refresh_tokens enable row level security;
-- No policies are created, which means: zero access via PostgREST/anon/
-- authenticated roles. Only a Postgres role with BYPASSRLS (e.g. the
-- 'postgres' role this service connects as) can read/write these tables.
