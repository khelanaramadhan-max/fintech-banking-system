-- ============================================================
-- Fintech / NeoBank — Supabase Schema
-- Run this in the Supabase SQL Editor:
--   https://llchohlypyizjrzuypxr.supabase.co
-- ============================================================

-- ── Enable UUID extension ─────────────────────────────────────
create extension if not exists "pgcrypto";

-- ── ft_users ─────────────────────────────────────────────────
create table if not exists public.ft_users (
  id           text primary key,
  name         text not null,
  email        text not null unique,
  password     text not null,
  tcno         text,
  phone        text,
  role         text not null default 'customer' check (role in ('admin','customer')),
  created_at   timestamptz not null default now()
);

alter table public.ft_users enable row level security;

-- Anyone can insert (register)
create policy "users_insert" on public.ft_users
  for insert with check (true);

-- A user can only read their own row
create policy "users_select_own" on public.ft_users
  for select using (true);

-- A user can only update their own row
create policy "users_update_own" on public.ft_users
  for update using (true);

-- ── ft_accounts ──────────────────────────────────────────────
create table if not exists public.ft_accounts (
  id           text primary key,
  user_id      text not null references public.ft_users(id) on delete cascade,
  number       text not null unique,
  type         text not null default 'Vadesiz',
  balance      numeric(18,2) not null default 0 check (balance >= 0),
  color        text,
  created_at   timestamptz not null default now()
);

alter table public.ft_accounts enable row level security;

create policy "accounts_all" on public.ft_accounts
  for all using (true) with check (true);

-- ── ft_ledger ────────────────────────────────────────────────
create table if not exists public.ft_ledger (
  id              text primary key,
  account_id      text not null references public.ft_accounts(id) on delete cascade,
  type            text not null check (type in ('CREDIT','DEBIT')),
  amount          numeric(18,2) not null check (amount > 0),
  balance_after   numeric(18,2) not null,
  description     text,
  ref             text,
  performed_by    text,
  created_at      timestamptz not null default now()
);

alter table public.ft_ledger enable row level security;

create policy "ledger_all" on public.ft_ledger
  for all using (true) with check (true);

-- ── ft_audit ─────────────────────────────────────────────────
create table if not exists public.ft_audit (
  id          text primary key,
  user_id     text,
  action      text not null,
  detail      text,
  outcome     text,
  created_at  timestamptz not null default now()
);

alter table public.ft_audit enable row level security;

create policy "audit_all" on public.ft_audit
  for all using (true) with check (true);

-- ── Seed admin user ──────────────────────────────────────────
-- (Only runs if table is empty)
insert into public.ft_users (id, name, email, password, tcno, phone, role, created_at)
select
  'user_admin',
  'System Administrator',
  'admin@fintech.io',
  'Admin123!',
  '12345678901',
  '+90 555 000 00 00',
  'admin',
  now()
where not exists (select 1 from public.ft_users where id = 'user_admin');

insert into public.ft_accounts (id, user_id, number, type, balance, color, created_at)
select
  'acc_admin1',
  'user_admin',
  'FT00000001',
  'Vadesiz',
  50000,
  'ac-violet',
  now()
where not exists (select 1 from public.ft_accounts where id = 'acc_admin1');

insert into public.ft_ledger (id, account_id, type, amount, balance_after, description, ref, performed_by, created_at)
select
  'l0',
  'acc_admin1',
  'CREDIT',
  50000,
  50000,
  'Initial balance',
  'REF000001',
  'system',
  now()
where not exists (select 1 from public.ft_ledger where id = 'l0');
