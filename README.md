# NeoBank — Core Banking System

> Python · FastAPI · Append-Only Ledger · JWT Auth · RBAC · Docker

---

## Quick Start

```bash
# 1. Clone & enter
git clone <repo> && cd banking

# 2. Copy env
cp .env.example .env   # edit values

# 3. Start everything
docker compose -f infra/docker-compose.yml up --build

# Backend API:   http://localhost:8000/docs
# Frontend UI:   http://localhost:3000
```

Default admin credentials: `admin@neobank.io` / `admin123`

---

## Architecture

```
┌─────────────┐     REST/JSON     ┌──────────────────────────┐
│  Frontend   │ ◄────────────────► │  FastAPI Backend         │
│  (HTML/JS)  │                   │  ├── Auth (JWT + RBAC)    │
└─────────────┘                   │  ├── Customers (KYC)      │
                                  │  ├── Accounts             │
                                  │  ├── Ledger (append-only) │
                                  │  ├── Transfers            │
                                  │  ├── Audit Logs           │
                                  │  └── Event Stream         │
                                  └──────────────────────────┘
```

Architectural pattern: **Modular Monolith** — single process, internally separated concerns.

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | — | Register new customer |
| POST | `/auth/login` | — | Login, get JWT |
| GET | `/auth/me` | User | Current user info |
| GET | `/customers` | Admin | List all customers |
| POST | `/accounts` | User/Admin | Open account |
| GET | `/accounts` | User | List accounts |
| POST | `/accounts/{id}/deposit` | User | Deposit funds |
| POST | `/accounts/{id}/withdraw` | User | Withdraw funds |
| POST | `/transfers` | User | Transfer between accounts |
| GET | `/accounts/{id}/ledger` | User | Account ledger |
| GET | `/ledger` | Admin | Full ledger |
| GET | `/audit` | Admin | Audit logs |
| GET | `/events` | Admin | Domain events |

Full Swagger: `http://localhost:8000/docs`

---

## Security Checklist

- [x] JWT-based authentication (HS256, 24h expiry)
- [x] Role-Based Access Control (Admin / Customer)
- [x] Input validation via Pydantic
- [x] Rate limiting (100 req/min per IP)
- [x] CORS middleware
- [x] Secure error responses (no stack traces in production)
- [x] Audit logging (user, action, timestamp, outcome)
- [x] `.env.example` — no secrets committed

---

## Financial Standards Mapping

This system uses REST/JSON APIs. Real-world financial systems use:

| Standard | Purpose | Our Mapping |
|----------|---------|-------------|
| **ISO 20022** | Universal financial messaging | Our transfer JSON schemas mirror ISO 20022 message structures (debtor, creditor, amount, reference) |
| **SWIFT** | Interbank messaging | Our `reference_id` corresponds to SWIFT's UETR (unique end-to-end transaction reference) |
| **Open Banking (PSD2)** | Regulated API access | Our JWT+RBAC auth model mirrors OAuth2 flows used in Open Banking |
| **EMV** | Card transaction security | Our ledger's immutability principle mirrors EMV's tamper-evident transaction records |

---

## Event System (Domain Events)

Every financial movement emits events, following the **outbox pattern** conceptually:

- `TransferCreated` — transfer initiated
- `TransferCompleted` — both legs settled
- `AccountDebited` — debit recorded
- `AccountCredited` — credit recorded

---

## Repository Structure

```
/backend          FastAPI application
/frontend         HTML + CSS + JS UI
/infra            docker-compose.yml
/docs             Architecture diagrams, API spec
.env.example      Environment variable template
README.md
```

---

## 3-Week Delivery Plan

| Week | Focus | Deliverables |
|------|-------|-------------|
| 1 | Architecture + Core APIs | Docker up, Swagger v0.1, account/transfer APIs |
| 2 | Security + Integration | JWT, RBAC, audit logs, full UI, CI pipeline |
| 3 | End-to-End Demo | Register → deposit → transfer → ledger → audit |
