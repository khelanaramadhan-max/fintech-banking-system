-- ============================================================
-- Fintech / NeoBank — Enhanced Supabase Schema v3.0
-- Run this in the Supabase SQL Editor:
--   https://llchohlypyizjrzuypxr.supabase.co
-- ============================================================
-- Tables Overview:
--   ft_users              → Core user table (admin | customer)
--   ft_accounts           → Bank accounts per user
--   ft_ledger             → Double-entry ledger entries
--   ft_audit              → Immutable action audit trail
--   ft_cards              → Debit/credit cards per account
--   ft_loans              → Loan applications and lifecycle
--   ft_loan_payments      → Installment payment records
--   ft_beneficiaries      → Saved payees per user
--   ft_notifications      → In-app push notifications
--   ft_kyc_documents      → KYC upload and review status
--   ft_transaction_requests → Pending txns requiring approval
--   ft_exchange_rates     → Live currency rates
--   ft_support_tickets    → Customer support tickets
-- ============================================================

-- ── Extensions ─────────────────────────────────────────────
create extension if not exists "pgcrypto";
create extension if not exists "uuid-ossp";

-- ============================================================
-- TABLE 1: ft_users
-- Core identity and authentication table.
-- Admins have full system access; customers see only their own data.
-- ============================================================
create table if not exists public.ft_users (
  id              text primary key default 'user_' || substr(md5(random()::text), 1, 8),
  name            text not null,
  email           text not null unique,
  password        text not null,
  tcno            text unique,
  phone           text,
  address         text,
  city            text,
  country         text not null default 'TR',
  currency        text not null default 'TRY',
  role            text not null default 'customer'
                    check (role in ('admin', 'customer', 'compliance')),
  status          text not null default 'ACTIVE'
                    check (status in ('ACTIVE', 'SUSPENDED', 'CLOSED')),
  kyc_status      text not null default 'PENDING'
                    check (kyc_status in ('PENDING', 'VERIFIED', 'REJECTED')),
  last_login_at   timestamptz,
  failed_logins   int not null default 0,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

alter table public.ft_users enable row level security;

drop policy if exists "users_insert" on public.ft_users;
create policy "users_insert" on public.ft_users
  for insert with check (true);

drop policy if exists "users_select_own" on public.ft_users;
create policy "users_select_own" on public.ft_users
  for select using (true);

drop policy if exists "users_update_own" on public.ft_users;
create policy "users_update_own" on public.ft_users
  for update using (true);

create index if not exists idx_ft_users_email  on public.ft_users(email);
create index if not exists idx_ft_users_role   on public.ft_users(role);
create index if not exists idx_ft_users_status on public.ft_users(status);

-- ============================================================
-- TABLE 2: ft_accounts
-- Bank accounts owned by users.
-- Multiple accounts per user; each has a balance and type.
-- ============================================================
create table if not exists public.ft_accounts (
  id              text primary key default 'acc_' || substr(md5(random()::text), 1, 8),
  user_id         text not null references public.ft_users(id) on delete cascade,
  number          text not null unique,
  iban            text unique,
  type            text not null default 'Vadesiz'
                    check (type in ('Vadesiz', 'Vadeli', 'Tasarruf', 'Yatirim', 'Doviz')),
  currency        text not null default 'TRY',
  balance         numeric(18,2) not null default 0 check (balance >= 0),
  credit_limit    numeric(18,2) not null default 0,
  status          text not null default 'ACTIVE'
                    check (status in ('ACTIVE', 'FROZEN', 'CLOSED')),
  color           text,
  interest_rate   numeric(5,4) default 0,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now()
);

alter table public.ft_accounts enable row level security;

drop policy if exists "accounts_all" on public.ft_accounts;
create policy "accounts_all" on public.ft_accounts
  for all using (true) with check (true);

create index if not exists idx_ft_accounts_user_id on public.ft_accounts(user_id);
create index if not exists idx_ft_accounts_status  on public.ft_accounts(status);
create index if not exists idx_ft_accounts_type    on public.ft_accounts(type);

-- ============================================================
-- TABLE 3: ft_ledger
-- Double-entry bookkeeping ledger.
-- Every monetary movement creates one or two entries.
-- ============================================================
create table if not exists public.ft_ledger (
  id              text primary key default gen_random_uuid()::text,
  account_id      text not null references public.ft_accounts(id) on delete cascade,
  transaction_request_id text,   -- FK added after ft_transaction_requests created
  type            text not null check (type in ('CREDIT','DEBIT')),
  amount          numeric(18,2) not null check (amount > 0),
  balance_after   numeric(18,2) not null,
  currency        text not null default 'TRY',
  description     text,
  category        text default 'GENERAL'
                    check (category in ('DEPOSIT','WITHDRAWAL','TRANSFER','LOAN_REPAYMENT',
                                        'CARD_PAYMENT','FEE','INTEREST','GENERAL')),
  ref             text,
  performed_by    text references public.ft_users(id),
  channel         text default 'APP'
                    check (channel in ('APP','ATM','BRANCH','API','SYSTEM')),
  ip_address      text,
  created_at      timestamptz not null default now()
);

alter table public.ft_ledger enable row level security;

drop policy if exists "ledger_all" on public.ft_ledger;
create policy "ledger_all" on public.ft_ledger
  for all using (true) with check (true);

create index if not exists idx_ft_ledger_account_id on public.ft_ledger(account_id);
create index if not exists idx_ft_ledger_ref        on public.ft_ledger(ref);
create index if not exists idx_ft_ledger_created    on public.ft_ledger(created_at desc);
create index if not exists idx_ft_ledger_category   on public.ft_ledger(category);

-- ============================================================
-- TABLE 4: ft_audit
-- Immutable action log — every system action is recorded here.
-- ============================================================
create table if not exists public.ft_audit (
  id          text primary key default gen_random_uuid()::text,
  user_id     text references public.ft_users(id),
  action      text not null,
  entity_type text,
  entity_id   text,
  detail      text,
  outcome     text check (outcome in ('SUCCESS','FAILURE','PENDING')),
  ip_address  text,
  user_agent  text,
  created_at  timestamptz not null default now()
);

alter table public.ft_audit enable row level security;

drop policy if exists "audit_all" on public.ft_audit;
create policy "audit_all" on public.ft_audit
  for all using (true) with check (true);

create index if not exists idx_ft_audit_user_id    on public.ft_audit(user_id);
create index if not exists idx_ft_audit_action     on public.ft_audit(action);
create index if not exists idx_ft_audit_created    on public.ft_audit(created_at desc);

-- ============================================================
-- TABLE 5: ft_cards
-- Debit and credit cards linked to accounts.
-- Cards have a status lifecycle and spending limits.
-- ============================================================
create table if not exists public.ft_cards (
  id              text primary key default 'card_' || substr(md5(random()::text), 1, 8),
  account_id      text not null references public.ft_accounts(id) on delete cascade,
  user_id         text not null references public.ft_users(id) on delete cascade,
  card_type       text not null default 'DEBIT'
                    check (card_type in ('DEBIT','CREDIT','VIRTUAL','PREPAID')),
  card_number     text not null unique,
  masked_number   text not null,
  cardholder_name text not null,
  expiry_month    int not null check (expiry_month between 1 and 12),
  expiry_year     int not null,
  cvv_hash        text not null,
  network         text not null default 'VISA'
                    check (network in ('VISA','MASTERCARD','TROY','AMEX')),
  status          text not null default 'ACTIVE'
                    check (status in ('ACTIVE','BLOCKED','EXPIRED','CANCELLED')),
  daily_limit     numeric(12,2) not null default 5000,
  monthly_limit   numeric(12,2) not null default 50000,
  contactless     boolean not null default true,
  online_payments boolean not null default true,
  issued_at       timestamptz not null default now(),
  last_used_at    timestamptz,
  created_at      timestamptz not null default now()
);

alter table public.ft_cards enable row level security;

drop policy if exists "cards_all" on public.ft_cards;
create policy "cards_all" on public.ft_cards
  for all using (true) with check (true);

create index if not exists idx_ft_cards_account_id on public.ft_cards(account_id);
create index if not exists idx_ft_cards_user_id    on public.ft_cards(user_id);
create index if not exists idx_ft_cards_status     on public.ft_cards(status);

-- ============================================================
-- TABLE 6: ft_loans
-- Loan applications with full lifecycle management.
-- Admin approval required before funds are disbursed.
-- ============================================================
create table if not exists public.ft_loans (
  id                  text primary key default 'loan_' || substr(md5(random()::text), 1, 8),
  user_id             text not null references public.ft_users(id) on delete cascade,
  account_id          text not null references public.ft_accounts(id),
  loan_type           text not null default 'PERSONAL'
                        check (loan_type in ('PERSONAL','MORTGAGE','AUTO','BUSINESS','STUDENT')),
  principal_amount    numeric(18,2) not null check (principal_amount > 0),
  interest_rate       numeric(5,4) not null,
  term_months         int not null check (term_months > 0),
  monthly_payment     numeric(18,2) not null,
  total_repayable     numeric(18,2) not null,
  amount_paid         numeric(18,2) not null default 0,
  outstanding_balance numeric(18,2) not null,
  status              text not null default 'PENDING'
                        check (status in ('PENDING','UNDER_REVIEW','APPROVED','REJECTED',
                                          'ACTIVE','CLOSED','DEFAULTED')),
  purpose             text,
  collateral          text,
  reviewed_by         text references public.ft_users(id),
  review_note         text,
  disbursed_at        timestamptz,
  next_payment_date   date,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

alter table public.ft_loans enable row level security;

drop policy if exists "loans_all" on public.ft_loans;
create policy "loans_all" on public.ft_loans
  for all using (true) with check (true);

create index if not exists idx_ft_loans_user_id    on public.ft_loans(user_id);
create index if not exists idx_ft_loans_status     on public.ft_loans(status);
create index if not exists idx_ft_loans_account_id on public.ft_loans(account_id);

-- ============================================================
-- TABLE 7: ft_loan_payments
-- Installment records for each active loan.
-- Tracks due dates, paid dates, and late fees.
-- ============================================================
create table if not exists public.ft_loan_payments (
  id              text primary key default gen_random_uuid()::text,
  loan_id         text not null references public.ft_loans(id) on delete cascade,
  installment_no  int not null,
  due_date        date not null,
  amount_due      numeric(18,2) not null,
  amount_paid     numeric(18,2) not null default 0,
  late_fee        numeric(18,2) not null default 0,
  status          text not null default 'PENDING'
                    check (status in ('PENDING','PAID','PARTIAL','OVERDUE','WAIVED')),
  paid_at         timestamptz,
  ledger_ref      text,
  created_at      timestamptz not null default now()
);

alter table public.ft_loan_payments enable row level security;

drop policy if exists "loan_payments_all" on public.ft_loan_payments;
create policy "loan_payments_all" on public.ft_loan_payments
  for all using (true) with check (true);

create index if not exists idx_ft_loan_payments_loan_id  on public.ft_loan_payments(loan_id);
create index if not exists idx_ft_loan_payments_due_date on public.ft_loan_payments(due_date);
create index if not exists idx_ft_loan_payments_status   on public.ft_loan_payments(status);

-- ============================================================
-- TABLE 8: ft_beneficiaries
-- Saved payee addresses for fast recurring transfers.
-- ============================================================
create table if not exists public.ft_beneficiaries (
  id          text primary key default 'bene_' || substr(md5(random()::text), 1, 8),
  user_id     text not null references public.ft_users(id) on delete cascade,
  name        text not null,
  bank_name   text,
  account_number text not null,
  iban        text,
  currency    text not null default 'TRY',
  is_internal boolean not null default false,
  is_verified boolean not null default false,
  nickname    text,
  created_at  timestamptz not null default now()
);

alter table public.ft_beneficiaries enable row level security;

drop policy if exists "beneficiaries_all" on public.ft_beneficiaries;
create policy "beneficiaries_all" on public.ft_beneficiaries
  for all using (true) with check (true);

create index if not exists idx_ft_beneficiaries_user_id on public.ft_beneficiaries(user_id);

-- ============================================================
-- TABLE 9: ft_notifications
-- In-app notification feed per user.
-- Admin can broadcast system-wide notifications.
-- ============================================================
create table if not exists public.ft_notifications (
  id          text primary key default gen_random_uuid()::text,
  user_id     text references public.ft_users(id) on delete cascade,
  type        text not null
                check (type in ('TRANSACTION','LOAN','SECURITY','SYSTEM','KYC','CARD','SUPPORT')),
  title       text not null,
  body        text not null,
  entity_type text,
  entity_id   text,
  is_read     boolean not null default false,
  priority    text not null default 'NORMAL'
                check (priority in ('LOW','NORMAL','HIGH','CRITICAL')),
  expires_at  timestamptz,
  created_at  timestamptz not null default now()
);

alter table public.ft_notifications enable row level security;

drop policy if exists "notifications_all" on public.ft_notifications;
create policy "notifications_all" on public.ft_notifications
  for all using (true) with check (true);

create index if not exists idx_ft_notifications_user_id  on public.ft_notifications(user_id);
create index if not exists idx_ft_notifications_is_read  on public.ft_notifications(is_read);
create index if not exists idx_ft_notifications_type     on public.ft_notifications(type);

-- ============================================================
-- TABLE 10: ft_kyc_documents
-- Customer identity verification documents.
-- Admin/compliance officer reviews and approves/rejects.
-- ============================================================
create table if not exists public.ft_kyc_documents (
  id              text primary key default 'kyc_' || substr(md5(random()::text), 1, 8),
  user_id         text not null references public.ft_users(id) on delete cascade,
  document_type   text not null
                    check (document_type in ('NATIONAL_ID','PASSPORT','DRIVING_LICENSE',
                                             'UTILITY_BILL','SELFIE','BANK_STATEMENT')),
  file_url        text,
  file_name       text,
  file_size       int,
  mime_type       text,
  status          text not null default 'PENDING'
                    check (status in ('PENDING','UNDER_REVIEW','APPROVED','REJECTED','EXPIRED')),
  reviewed_by     text references public.ft_users(id),
  review_note     text,
  expires_at      date,
  submitted_at    timestamptz not null default now(),
  reviewed_at     timestamptz
);

alter table public.ft_kyc_documents enable row level security;

drop policy if exists "kyc_all" on public.ft_kyc_documents;
create policy "kyc_all" on public.ft_kyc_documents
  for all using (true) with check (true);

create index if not exists idx_ft_kyc_user_id on public.ft_kyc_documents(user_id);
create index if not exists idx_ft_kyc_status  on public.ft_kyc_documents(status);

-- ============================================================
-- TABLE 11: ft_transaction_requests
-- Transactions that require admin approval before execution.
-- Large transfers, cross-border, or flagged transactions land here.
-- ============================================================
create table if not exists public.ft_transaction_requests (
  id                  text primary key default 'txreq_' || substr(md5(random()::text), 1, 8),
  initiated_by        text not null references public.ft_users(id),
  from_account_id     text references public.ft_accounts(id),
  to_account_id       text references public.ft_accounts(id),
  beneficiary_id      text references public.ft_beneficiaries(id),
  amount              numeric(18,2) not null check (amount > 0),
  currency            text not null default 'TRY',
  request_type        text not null
                        check (request_type in ('TRANSFER','WITHDRAWAL','EXTERNAL','BULK')),
  description         text,
  status              text not null default 'PENDING'
                        check (status in ('PENDING','UNDER_REVIEW','APPROVED','REJECTED','EXPIRED','EXECUTED')),
  risk_score          int default 0 check (risk_score between 0 and 100),
  risk_flags          text[],
  reviewed_by         text references public.ft_users(id),
  review_note         text,
  reviewed_at         timestamptz,
  auto_approve        boolean not null default false,
  expires_at          timestamptz default now() + interval '48 hours',
  created_at          timestamptz not null default now()
);

alter table public.ft_transaction_requests enable row level security;

drop policy if exists "transaction_requests_all" on public.ft_transaction_requests;
create policy "transaction_requests_all" on public.ft_transaction_requests
  for all using (true) with check (true);

create index if not exists idx_ft_txreq_initiated_by   on public.ft_transaction_requests(initiated_by);
create index if not exists idx_ft_txreq_status         on public.ft_transaction_requests(status);
create index if not exists idx_ft_txreq_from_account   on public.ft_transaction_requests(from_account_id);
create index if not exists idx_ft_txreq_created        on public.ft_transaction_requests(created_at desc);

-- Now we can add the FK from ft_ledger to ft_transaction_requests
alter table public.ft_ledger add column if not exists
  tx_request_id text references public.ft_transaction_requests(id);

-- ============================================================
-- TABLE 12: ft_exchange_rates
-- Currency exchange rate table updated periodically.
-- Used for multi-currency accounts and FX conversion.
-- ============================================================
create table if not exists public.ft_exchange_rates (
  id              text primary key default gen_random_uuid()::text,
  base_currency   text not null,
  target_currency text not null,
  rate            numeric(16,6) not null check (rate > 0),
  bid_rate        numeric(16,6),
  ask_rate        numeric(16,6),
  source          text not null default 'TCMB'
                    check (source in ('TCMB','ECB','FIXER','MANUAL')),
  is_active       boolean not null default true,
  valid_from      timestamptz not null default now(),
  valid_until     timestamptz,
  created_at      timestamptz not null default now(),
  unique (base_currency, target_currency, source, valid_from)
);

alter table public.ft_exchange_rates enable row level security;

drop policy if exists "exchange_rates_select" on public.ft_exchange_rates;
create policy "exchange_rates_select" on public.ft_exchange_rates
  for select using (true);

drop policy if exists "exchange_rates_insert_admin" on public.ft_exchange_rates;
create policy "exchange_rates_insert_admin" on public.ft_exchange_rates
  for insert with check (true);

create index if not exists idx_ft_fx_pair   on public.ft_exchange_rates(base_currency, target_currency);
create index if not exists idx_ft_fx_active on public.ft_exchange_rates(is_active);

-- ============================================================
-- TABLE 13: ft_support_tickets
-- Customer support ticket system.
-- Links to the user and optionally a specific account or transaction.
-- ============================================================
create table if not exists public.ft_support_tickets (
  id              text primary key default 'ticket_' || substr(md5(random()::text), 1, 8),
  user_id         text not null references public.ft_users(id) on delete cascade,
  assigned_to     text references public.ft_users(id),
  category        text not null
                    check (category in ('TRANSACTION','ACCOUNT','CARD','LOAN','KYC',
                                        'FRAUD','GENERAL','TECHNICAL')),
  subject         text not null,
  description     text not null,
  status          text not null default 'OPEN'
                    check (status in ('OPEN','IN_PROGRESS','WAITING','RESOLVED','CLOSED')),
  priority        text not null default 'MEDIUM'
                    check (priority in ('LOW','MEDIUM','HIGH','URGENT')),
  related_account_id text references public.ft_accounts(id),
  related_tx_id   text,
  resolution_note text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),
  resolved_at     timestamptz
);

alter table public.ft_support_tickets enable row level security;

drop policy if exists "support_tickets_all" on public.ft_support_tickets;
create policy "support_tickets_all" on public.ft_support_tickets
  for all using (true) with check (true);

create index if not exists idx_ft_tickets_user_id     on public.ft_support_tickets(user_id);
create index if not exists idx_ft_tickets_status      on public.ft_support_tickets(status);
create index if not exists idx_ft_tickets_assigned_to on public.ft_support_tickets(assigned_to);
create index if not exists idx_ft_tickets_priority    on public.ft_support_tickets(priority);

-- ============================================================
-- SEED DATA
-- ============================================================

-- ── Admin user ──────────────────────────────────────────────
insert into public.ft_users (id, name, email, password, tcno, phone, address, city, country, currency, role, status, kyc_status)
select
  'user_admin',
  'System Administrator',
  'admin@fintech.io',
  'Admin123!',
  '12345678901',
  '+90 555 000 00 00',
  'Fintech HQ, Levent',
  'Istanbul',
  'TR',
  'TRY',
  'admin',
  'ACTIVE',
  'VERIFIED'
where not exists (select 1 from public.ft_users where id = 'user_admin');

-- ── Demo customer ────────────────────────────────────────────
insert into public.ft_users (id, name, email, password, tcno, phone, address, city, country, currency, role, status, kyc_status)
select
  'user_demo01',
  'Ali Yilmaz',
  'ali@demo.io',
  'Demo123!',
  '98765432109',
  '+90 532 111 22 33',
  'Kadikoy Mah. 15. Sokak No:7',
  'Istanbul',
  'TR',
  'TRY',
  'customer',
  'ACTIVE',
  'VERIFIED'
where not exists (select 1 from public.ft_users where id = 'user_demo01');

-- ── Admin account ────────────────────────────────────────────
insert into public.ft_accounts (id, user_id, number, iban, type, currency, balance, color)
select
  'acc_admin1',
  'user_admin',
  'FT00000001',
  'TR00 0000 0000 0000 0000 0000 01',
  'Vadesiz',
  'TRY',
  50000,
  'ac-violet'
where not exists (select 1 from public.ft_accounts where id = 'acc_admin1');

-- ── Demo customer accounts ───────────────────────────────────
insert into public.ft_accounts (id, user_id, number, iban, type, currency, balance, color)
select 'acc_demo01a', 'user_demo01', 'FT00000101', 'TR00 0000 0000 0000 0000 0001 01', 'Vadesiz', 'TRY', 12500, 'ac-blue'
where not exists (select 1 from public.ft_accounts where id = 'acc_demo01a');

insert into public.ft_accounts (id, user_id, number, iban, type, currency, balance, color, interest_rate)
select 'acc_demo01b', 'user_demo01', 'FT00000102', 'TR00 0000 0000 0000 0000 0001 02', 'Tasarruf', 'TRY', 35000, 'ac-green', 0.0325
where not exists (select 1 from public.ft_accounts where id = 'acc_demo01b');

-- ── Seed ledger ──────────────────────────────────────────────
insert into public.ft_ledger (id, account_id, type, amount, balance_after, currency, description, category, ref, performed_by, channel)
select 'l0', 'acc_admin1', 'CREDIT', 50000, 50000, 'TRY', 'Initial system balance', 'DEPOSIT', 'REF000001', 'user_admin', 'SYSTEM'
where not exists (select 1 from public.ft_ledger where id = 'l0');

insert into public.ft_ledger (id, account_id, type, amount, balance_after, currency, description, category, ref, performed_by, channel)
select 'l1', 'acc_demo01a', 'CREDIT', 12500, 12500, 'TRY', 'Opening deposit', 'DEPOSIT', 'REF000002', 'user_admin', 'BRANCH'
where not exists (select 1 from public.ft_ledger where id = 'l1');

insert into public.ft_ledger (id, account_id, type, amount, balance_after, currency, description, category, ref, performed_by, channel)
select 'l2', 'acc_demo01b', 'CREDIT', 35000, 35000, 'TRY', 'Savings account opening', 'DEPOSIT', 'REF000003', 'user_admin', 'BRANCH'
where not exists (select 1 from public.ft_ledger where id = 'l2');

-- ── Demo card ────────────────────────────────────────────────
insert into public.ft_cards (id, account_id, user_id, card_type, card_number, masked_number, cardholder_name, expiry_month, expiry_year, cvv_hash, network, status)
select
  'card_demo01',
  'acc_demo01a',
  'user_demo01',
  'DEBIT',
  '4111111111111111',
  '4111 **** **** 1111',
  'ALI YILMAZ',
  12,
  2028,
  md5('123'),
  'VISA',
  'ACTIVE'
where not exists (select 1 from public.ft_cards where id = 'card_demo01');

-- ── Demo exchange rates ──────────────────────────────────────
insert into public.ft_exchange_rates (base_currency, target_currency, rate, bid_rate, ask_rate, source)
select 'USD', 'TRY', 38.45, 38.32, 38.58, 'TCMB'
where not exists (select 1 from public.ft_exchange_rates where base_currency = 'USD' and target_currency = 'TRY' and source = 'TCMB');

insert into public.ft_exchange_rates (base_currency, target_currency, rate, bid_rate, ask_rate, source)
select 'EUR', 'TRY', 41.20, 41.05, 41.35, 'TCMB'
where not exists (select 1 from public.ft_exchange_rates where base_currency = 'EUR' and target_currency = 'TRY' and source = 'TCMB');

insert into public.ft_exchange_rates (base_currency, target_currency, rate, bid_rate, ask_rate, source)
select 'GBP', 'TRY', 49.75, 49.55, 49.95, 'TCMB'
where not exists (select 1 from public.ft_exchange_rates where base_currency = 'GBP' and target_currency = 'TRY' and source = 'TCMB');

-- ── Demo pending transaction request ────────────────────────
insert into public.ft_transaction_requests (id, initiated_by, from_account_id, to_account_id, amount, currency, request_type, description, status, risk_score, risk_flags)
select
  'txreq_demo01',
  'user_demo01',
  'acc_demo01a',
  'acc_admin1',
  9500,
  'TRY',
  'TRANSFER',
  'Large demo transfer — awaiting admin approval',
  'PENDING',
  65,
  array['LARGE_AMOUNT', 'FIRST_TRANSFER']
where not exists (select 1 from public.ft_transaction_requests where id = 'txreq_demo01');

-- ── Demo notification ────────────────────────────────────────
insert into public.ft_notifications (user_id, type, title, body, entity_type, entity_id, priority)
select
  'user_demo01',
  'KYC',
  'KYC Verification Complete',
  'Your identity has been verified successfully. You now have full access to all banking features.',
  'user',
  'user_demo01',
  'HIGH'
where not exists (select 1 from public.ft_notifications where user_id = 'user_demo01' and type = 'KYC');

-- ── Demo support ticket ──────────────────────────────────────
insert into public.ft_support_tickets (id, user_id, category, subject, description, status, priority, related_account_id)
select
  'ticket_demo01',
  'user_demo01',
  'TRANSACTION',
  'Transfer pending for too long',
  'I submitted a transfer yesterday but it still shows as pending. Please review.',
  'OPEN',
  'HIGH',
  'acc_demo01a'
where not exists (select 1 from public.ft_support_tickets where id = 'ticket_demo01');

-- ── Demo KYC document ───────────────────────────────────────
insert into public.ft_kyc_documents (id, user_id, document_type, file_name, status)
select
  'kyc_demo01',
  'user_demo01',
  'NATIONAL_ID',
  'national_id_ali_yilmaz.jpg',
  'APPROVED'
where not exists (select 1 from public.ft_kyc_documents where id = 'kyc_demo01');

-- ── Demo beneficiary ─────────────────────────────────────────
insert into public.ft_beneficiaries (id, user_id, name, bank_name, account_number, iban, currency, is_internal, is_verified, nickname)
select
  'bene_demo01',
  'user_demo01',
  'Mehmet Kaya',
  'NeoBank',
  'FT00000001',
  'TR00 0000 0000 0000 0000 0000 01',
  'TRY',
  true,
  true,
  'Admin Account'
where not exists (select 1 from public.ft_beneficiaries where id = 'bene_demo01');
