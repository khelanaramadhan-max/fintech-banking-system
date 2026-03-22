# 🏦 Fintech — Mini Core Banking System

**Team 2 · Python + FastAPI + Vanilla JS + Docker**  
**Architecture: Modular Monolith**  
**Course: 2025-2026 FinTech — Department of International Trade and Business**

---

| 🔗 Link | URL |
|---|---|
| GitHub | https://github.com/your-username/fintech-core-banking |
| Live Frontend | https://69bfe4b059f45b815c1890c9--classy-taffy-e5537f.netlify.app/ |
| API Docs (Swagger) | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |

---

## 🏗️ Architecture

This project is a **Modular Monolith** — a single FastAPI application with clearly separated internal modules. All modules share one data layer (`BankStore`) and communicate directly, protected by a thread-safe `threading.RLock()`.

```
docker compose up --build
```

### System Architecture Diagram

```
┌─────────────────────────── USER BROWSER ────────────────────────────┐
│                                                                       │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │         FRONTEND  (fintech.html — Single File SPA)           │   │
│   │   HTML5 + CSS3 + Vanilla JavaScript · TR / EN / RU i18n     │   │
│   │                                                               │   │
│   │  Auth · Dashboard · Accounts · TopUp · Payment · Transfer    │   │
│   │  History · Profile · Admin Panel · Card Detection Engine     │   │
│   └──────────────────────────┬──────────────────────────────────┘   │
│                                │  HTTP REST + JSON                   │
│                                │  Authorization: Bearer <JWT>        │
│                                ▼                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │              BACKEND  (FastAPI · port 8000)                   │   │
│   │                                                               │   │
│   │   Rate Limiter → JWT Auth → RBAC → BankStore (RLock)        │   │
│   │                                                               │   │
│   │   auth · customers · accounts · transactions · ledger        │   │
│   │   transfers (EFT/SWIFT/FAST/HAVALE) · audit · events        │   │
│   └──────────────────────────┬──────────────────────────────────┘   │
│                                │  threading.RLock (Atomic)           │
│                                ▼                                     │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │           BankStore — In-Memory Data Layer                    │   │
│   │                                                               │   │
│   │   users{}  customers{}  accounts{}                            │   │
│   │   ledger[]  audit_logs[]  event_log[]   ← APPEND-ONLY        │   │
│   └─────────────────────────────────────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────┘
```

### Internal Modules

| Module | Responsibility |
|---|---|
| `auth` | JWT authentication (HS256), registration, login, token validation |
| `customers` | Customer creation, TC Kimlik validation, KYC verification |
| `accounts` | Account opening, balance inquiry (computed from ledger) |
| `ledger` | Append-only transaction log — single source of truth |
| `transactions` | Deposit, withdrawal, EFT, SWIFT, FAST, HAVALE transfers |
| `audit` | Admin-level audit trail — every action logged with IP + timestamp |
| `events` | Domain event system (TransferCreated, AccountCredited…) |
| `security` | Rate limiting (100 req/min), CORS, RBAC enforcement |

---

## 🗺️ How It Maps to Real Financial Standards

| Our System | Real-World Standard | Mapping |
|---|---|---|
| REST/JSON APIs | ISO 20022 | Each endpoint mirrors an ISO 20022 message — transfers follow `pacs.008`, ledger queries follow `camt.053` structure |
| JWT Bearer Auth | PSD2 / Open Banking | JWT simulates OAuth2 token exchange. Our RBAC (Admin/Customer) maps to PSD2 TPP consent scopes |
| Webhooks | SWIFT gpi push | Our `TransferCreated → TransferCompleted` events mirror SWIFT gpi Tracker API status updates |
| EFT / HAVALE | Turkish interbank | EFT (Elektronik Fon Transferi) for interbank, HAVALE for same-bank, FAST for 7/24 real-time |
| SWIFT | MT103 / ISO 20022 pacs.008 | International wire with BIC/SWIFT code, IBAN routing, correspondent bank |
| Ledger entries | Double-entry bookkeeping | Every transfer creates paired DEBIT + CREDIT — debit always equals credit |
| Account numbers | Turkish IBAN prefix | Generated numbers follow `FT` prefix + 8-digit account identifier |
| Audit logs | PCI DSS Req. 10 | Captures who/what/when/outcome/IP — mirrors PCI DSS compliance logging |
| Transfer limits | EMV authorization | Amount validation, balance checks mirror EMV card authorization flow |

---

## ✨ Features

### Core Banking
- **Append-Only Ledger** — transactions are never deleted or modified; balance is always computed, never stored
- **Double-Entry Bookkeeping** — every transfer creates a DEBIT + CREDIT pair; `|debit| always = credit`
- **Multi-Type Transfers** — EFT, SWIFT (international), FAST (instant 7/24), HAVALE (intrabank)
- **Top Up via Card** — deposit funds using Visa / Mastercard / Troy / Amex with real BIN-range detection
- **Bill Payments** — Electric, Gas, Internet, Phone, Water, Netflix quick-pay
- **Virtual Account Cards** — animated card UI with per-account color coding

### Security
- **JWT Authentication** — custom HS256 (no external library), 24-hour expiry
- **SHA-256 Password Hashing** — passwords never stored in plain text
- **Role-Based Access Control** — Admin vs Customer enforced on every endpoint
- **Rate Limiting** — 100 req/min per IP (sliding window, in-memory)
- **Audit Trail** — every login, transfer, and admin action logged with timestamp and IP
- **TC Kimlik Validation** — full 11-digit Turkish national ID checksum algorithm on registration
- **Password Policy** — min 6 chars + 1 uppercase + 1 digit enforced with real-time strength meter

### Frontend
- **Single-File SPA** — entire app in one `fintech.html` (pure vanilla JS, no framework)
- **Multilingual i18n** — TR / EN / RU, instant switching, persisted in `localStorage`
- **Card Network Detection** — real BIN-range logic: Troy, Visa, Mastercard, Amex, Diners
- **Transfer Type Selector** — EFT, SWIFT, FAST, HAVALE with fees, cut-off times, and limits
- **IBAN / Kolay Adres input** — accepts account number, IBAN, email, or phone number as recipient
- **Password Strength Meter** — 4-bar real-time strength indicator during registration
- **Responsive Design** — dark navy theme, CSS Grid/Flexbox, mobile-friendly

### DevOps
- **Docker Compose** — two containers: FastAPI backend + Nginx static frontend
- **Health Check** — `GET /health` monitored by Docker with auto-restart
- **Environment Variables** — `JWT_SECRET` and `ADMIN_PASSWORD` via `.env`

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.12+ (for local dev only)

### Run with Docker
```bash
# Clone the repository
git clone https://github.com/your-username/fintech-core-banking
cd fintech-core-banking

# Copy and configure environment
cp .env.example .env

# Start all services
docker compose -f infra/docker-compose.yml up --build
```

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Swagger Docs | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |

### Local Development (without Docker)
```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend — open directly in browser
open frontend/fintech.html
```

---

## 📁 Project Structure

```
fintech/
├── backend/
│   ├── main.py                # FastAPI application (~350 lines)
│   │   ├── BankStore          # Thread-safe in-memory data layer
│   │   ├── JWT helpers        # Custom HS256 — stdlib only, no external lib
│   │   ├── Pydantic models    # Request/response validation with Decimal
│   │   └── 16 REST endpoints  # Auth, Accounts, Transfers, Ledger, Audit
│   ├── requirements.txt       # fastapi==0.115, uvicorn==0.30, pydantic==2.9
│   └── Dockerfile             # python:3.12-slim
│
├── frontend/
│   └── fintech.html           # Complete SPA (~1100 lines)
│       ├── Auth Screen        # Login + Register with TC Kimlik validation
│       ├── Dashboard          # Balance stats + recent transactions
│       ├── Accounts           # View accounts + open new account
│       ├── Top Up             # Card deposit with live network detection
│       ├── Payment            # Bill payments + merchant payments
│       ├── Transfer           # EFT / SWIFT / FAST / HAVALE selector
│       ├── History            # Filterable transaction log
│       ├── Profile            # Personal info + change password
│       └── Admin Panel        # User list + full audit trail
│
├── infra/
│   └── docker-compose.yml     # backend (FastAPI) + frontend (Nginx)
│
├── docs/
│   ├── architecture.png       # System architecture diagram
│   └── security_notes.md      # Security implementation notes
│
├── .env.example               # JWT_SECRET, ADMIN_PASSWORD placeholders
└── README.md                  # This file
```

---

## 🔐 Security

| Layer | Implementation |
|---|---|
| Authentication | Custom JWT HS256 — `create_token()` / `decode_token()` using Python stdlib only |
| Password storage | `hashlib.sha256(pw.encode()).hexdigest()` — never stored plain |
| RBAC | `require_admin()` FastAPI dependency on admin endpoints |
| Rate limiting | In-memory sliding window — 100 requests/minute per IP; returns HTTP 429 |
| CORS | `CORSMiddleware` — configurable origin whitelist |
| Audit logging | Logs: `user_id`, `action`, `resource`, `outcome`, `ip_address`, `timestamp` |
| Input validation | Pydantic `Field(gt=0)`, `min_length`, `max_length` on all request bodies |
| Token expiry | JWT `exp` claim — expires after 24 hours |
| TC Kimlik | Rule 1: sum mod 10 = 11th digit · Rule 2: (odd×7 − even) mod 10 = 10th digit |
| Secrets | `.env` for `JWT_SECRET` + `ADMIN_PASSWORD` — never hardcoded in source |

---

## 💸 Transfer Types

| Type | Full Name | Timing | Max Amount | Use Case |
|---|---|---|---|---|
| **FAST** | Fonların Anlık ve Sürekli Transferi | 7/24 instant | ₺100,000 | Real-time small transfers between banks |
| **EFT** | Elektronik Fon Transferi | Weekdays 08:00–17:00 | Unlimited | Large interbank transfers, business payments |
| **HAVALE** | Havale | Instant (same bank) | Unlimited | Transfers within the same bank |
| **SWIFT** | Society for Worldwide Interbank Financial Telecommunication | 1–5 business days | Unlimited | International wire transfers with IBAN + BIC |

> **Note:** FAST transfers are limited to ₺100,000 per transaction per TCMB regulations. EFT is only processed during CBRT business hours. SWIFT requires a valid BIC/SWIFT code for the recipient bank.

---

## 📒 Ledger Consistency

Since we use an in-memory store, ledger integrity is enforced through:

- **Append-only design** — no UPDATE or DELETE ever touches `ledger[]`
- **Thread-safe writes** — `threading.RLock()` wraps all balance mutations
- **Computed balances** — balance is NEVER stored; always computed as `Σ CREDIT − Σ DEBIT`
- **Double-entry bookkeeping** — every transfer creates paired DEBIT + CREDIT entries
- **Atomic transfers** — debit and credit happen inside the same `with self._lock:` block; no partial states
- **Unique reference IDs** — every transaction carries a UUID `ref` for full traceability
- **Decimal arithmetic** — `decimal.Decimal` used throughout (not `float`) to prevent rounding errors

---

## 🔔 Webhook Events

Domain events emitted on every financial operation (stored in `event_log[]`, available at `GET /events`):

| Event | Trigger | Required |
|---|---|---|
| `TransferCreated` | Transfer initiated | ✅ |
| `TransferCompleted` | Transfer committed to ledger | ✅ |
| `AccountDebited` | Amount deducted from source | ✅ |
| `AccountCredited` | Amount added to target | ✅ |
| `DepositCompleted` | Deposit processed via card | Bonus |
| `WithdrawalCompleted` | Withdrawal / payment processed | Bonus |
| `AccountCreated` | New account opened | Bonus |

Webhook payloads include: `event_type`, `payload` (account IDs, amount, reference), and `timestamp`.

---

## 🧪 API Endpoints

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/auth/register` | — | Register user, returns JWT |
| POST | `/auth/login` | — | Login, returns JWT |
| GET | `/auth/me` | JWT | Current user profile |
| GET | `/customers` | Admin | List all registered customers |
| GET | `/customers/{id}` | JWT | Get customer profile |
| POST | `/accounts` | JWT | Open new bank account |
| GET | `/accounts` | JWT | List my accounts (admin sees all) |
| GET | `/accounts/{id}` | JWT | Get single account |
| POST | `/accounts/{id}/deposit` | JWT | Deposit / Top Up |
| POST | `/accounts/{id}/withdraw` | JWT | Withdraw / Pay |
| POST | `/transfers` | JWT | Transfer (EFT / SWIFT / FAST / HAVALE) |
| GET | `/accounts/{id}/ledger` | JWT | Account transaction history |
| GET | `/ledger` | Admin | Full system ledger |
| GET | `/audit` | Admin | Security audit trail |
| GET | `/events` | Admin | Domain event stream |
| GET | `/health` | — | Health check (used by Docker) |

---

## 🎓 End-to-End Banking Flow

```bash
1. POST /auth/register           → Create user (TC Kimlik validated on frontend)
2. POST /auth/login              → Get JWT token (24-hour expiry)
3. POST /accounts                → Open bank account (FT-prefixed number generated)
4. POST /accounts/{id}/deposit   → Fund via card (Visa/Mastercard/Troy detected)
5. POST /transfers               → Send money
   ├── type: "FAST"              → Instant, max ₺100,000
   ├── type: "EFT"               → Interbank, weekday business hours
   ├── type: "HAVALE"            → Same-bank, instant
   └── type: "SWIFT"             → International, 1-5 days, requires BIC
   └── Events: TransferCreated → AccountDebited → AccountCredited → TransferCompleted
6. GET  /accounts/{id}/ledger    → Verify DEBIT + CREDIT paired entries
7. GET  /accounts/{id}           → Confirm computed balance
8. GET  /audit                   → Review audit trail (Admin only)
9. GET  /events                  → Verify domain event log (Admin only)
```

---

## 🌍 Multilingual Support

| Language | Code | Coverage |
|---|---|---|
| 🇹🇷 Türkçe | `tr` | ✅ Default — all labels, errors, transfer type descriptions |
| 🇬🇧 English | `en` | ✅ Full translation |
| 🇷🇺 Русский | `ru` | ✅ Full translation |

Switching is instant with no page reload. Choice persisted in `localStorage`. Implemented via `data-i18n` HTML attributes + a `T[LANG][key]` dictionary.

---

## 🛠️ Technology Stack

| Layer | Technology | Version | Why |
|---|---|---|---|
| Backend | Python + FastAPI | 3.12 / 0.115 | Fastest Python framework; auto Swagger; async; Pydantic |
| Validation | Pydantic | 2.9 | Type-safe models; `Decimal` field validators |
| Server | Uvicorn | 0.30 | ASGI server; production-ready |
| Auth | Custom JWT (stdlib) | HS256 | Zero external dependencies; full control |
| Frontend | HTML5 + CSS3 + JS | Vanilla | No framework; demonstrates fundamentals |
| Fonts | Plus Jakarta Sans + Space Mono | Google Fonts | Modern fintech aesthetic |
| Containerization | Docker + Compose | Latest | One-command startup; reproducible builds |
| Web Server | Nginx Alpine | Latest | Lightweight static file serving |

---

## 📊 Grading Rubric

| Category | Points | What We Built |
|---|---|---|
| **Architecture** | 20 pts | 3-tier architecture, REST API design, Domain Events, Append-Only Ledger, BankStore singleton |
| **Backend** | 20 pts | FastAPI, Pydantic, 16 endpoints, `decimal.Decimal` math, thread-safe store, structured logging |
| **Security** | 20 pts | JWT HS256 (custom), SHA-256 hashing, RBAC, rate limiting (100/min), audit log, CORS |
| **UI / Mobile** | 15 pts | Responsive SPA, 9 pages, virtual card preview, BIN detection, 3 languages, EFT/SWIFT/FAST/HAVALE |
| **DevOps** | 15 pts | Docker, Compose, Dockerfile, `.env`, healthcheck, Nginx static serving |
| **Documentation** | 10 pts | This README, Swagger at `/docs`, architecture diagram, API reference table |
| **Total** | **100 pts** | |

---

## 📜 License

Course Assignment — 2025-2026 FinTech  
Department of International Trade and Business
