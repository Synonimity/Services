-- Run once in the host project's Supabase project.

create table if not exists customers (
    id uuid primary key default gen_random_uuid(),
    external_user_id varchar(255) unique not null,
    email varchar(255) not null,
    name_first varchar(100),
    name_last varchar(100),
    created_at timestamptz not null default now()
);
create index if not exists ix_customers_external_user_id on customers (external_user_id);

create table if not exists plans (
    id uuid primary key default gen_random_uuid(),
    code varchar(50) unique not null,
    name varchar(100) not null,
    amount numeric(10, 2) not null,
    frequency smallint not null default 3,
    cycles smallint not null default 0,
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

create table if not exists subscriptions (
    id uuid primary key default gen_random_uuid(),
    customer_id uuid not null references customers (id) on delete cascade,
    plan_id uuid not null references plans (id),
    m_payment_id varchar(100) unique not null,
    payfast_token varchar(100) unique,
    status varchar(20) not null default 'pending',
    next_billing_date date,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists ix_subscriptions_customer on subscriptions (customer_id);
create index if not exists ix_subscriptions_m_payment_id on subscriptions (m_payment_id);

create table if not exists payments (
    id uuid primary key default gen_random_uuid(),
    subscription_id uuid references subscriptions (id) on delete set null,
    customer_id uuid not null references customers (id),
    pf_payment_id varchar(100) not null,
    m_payment_id varchar(100) not null,
    amount_gross numeric(10, 2) not null,
    amount_fee numeric(10, 2) not null,
    amount_net numeric(10, 2) not null,
    payment_status varchar(20) not null,
    raw_payload jsonb not null,
    created_at timestamptz not null default now()
);
create index if not exists ix_payments_subscription on payments (subscription_id);
create index if not exists ix_payments_m_payment_id on payments (m_payment_id);

-- Seed your plans here:
-- insert into plans (code, name, amount, frequency, cycles) values
--     ('starter_monthly', 'Starter', 99.00, 3, 0),
--     ('pro_monthly', 'Pro', 299.00, 3, 0);

alter table customers enable row level security;
alter table plans enable row level security;
alter table subscriptions enable row level security;
alter table payments enable row level security;
