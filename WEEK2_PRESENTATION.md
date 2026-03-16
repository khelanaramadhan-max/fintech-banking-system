# 📊 Week 2 Presentation — Fintech Banking System
**Course: 2025-2026 FinTech · Department of International Trade and Business**  
**Team 2 · Presentation Date: Week 2**

---

## ✅ What We Built in Week 1 (Recap)

| Deliverable | Status | Notes |
|---|---|---|
| FastAPI backend (`main.py`) | ✅ Done | 16 endpoints, ~350 lines |
| JWT Authentication (custom HS256) | ✅ Done | No external library |
| RBAC — Admin / Customer roles | ✅ Done | `require_admin()` dependency |
| Append-Only Ledger | ✅ Done | Immutable `ledger[]` list |
| Thread-safe BankStore | ✅ Done | `threading.RLock()` |
| Domain Event System | ✅ Done | TransferCreated, AccountCredited… |
| Audit Trail | ✅ Done | Logs IP, action, outcome, timestamp |
| Rate Limiting | ✅ Done | 100 req/min in-memory sliding window |
| Frontend SPA (`fintech.html`) | ✅ Done | 9 pages, ~1100 lines vanilla JS |
| Card Network Detection (BIN) | ✅ Done | Troy, Visa, MC, Amex, Diners |
| TC Kimlik Validation | ✅ Done | Official 11-digit algorithm |
| Transfer Types (EFT/SWIFT/FAST/HAVALE) | ✅ Done | Rules, fees, limits, SWIFT extra fields |
| Multilingual i18n (TR/EN/RU) | ✅ Done | 100+ translation keys |
| Docker Compose | ✅ Done | backend + nginx frontend |
| README.md | ✅ Done | Full documentation |

---

## 🚀 Week 2 Additions

### 1. Transfer System Upgrade — EFT / SWIFT / FAST / HAVALE

The transfer page was completely rebuilt with 4 real Turkish banking transfer types:

| Type | Full Name | Timing | Limit | Real-World Basis |
|---|---|---|---|---|
| **FAST** | Fonların Anlık ve Sürekli Transferi | 7/24 instant | ₺100,000 | TCMB-regulated instant payment system (live since 2021) |
| **EFT** | Elektronik Fon Transferi | Weekdays 08:00–17:00 | Unlimited | Turkish interbank settlement system via CBRT |
| **HAVALE** | Havale | Instant (same bank) | Unlimited | Intrabank — no central clearing needed |
| **SWIFT** | SWIFT MT103 | 1–5 business days | Unlimited | International wires — BIC + IBAN + currency + beneficiary |

**New UI features:**
- 4-type selector with timing shown on each tile
- Live information banner — shows timing, fee, and description of selected type
- Rules card — explains the selected transfer type's legal/technical constraints
- SWIFT-only extra fields: BIC code, currency (USD/EUR/GBP/CHF/JPY/CAD/AED), beneficiary name + bank
- FAST limit validation — blocks transactions over ₺100,000 with real TCMB regulation message
- Smart recipient field — detects IBAN, account number, phone, or email as input type

### 2. Project Configuration Files Added

Added the full set of professional project configuration files:

```
.env.example          # All environment variables documented
.gitignore            # Python, Node, Docker, IDE, secrets ignored
.node-version / .nvmrc # Node.js 18.19.0 pinned
render.yaml           # One-click Render.com deployment config
docker-compose.yml    # Updated with webhook receiver service
package-lock.json     # Frontend dependency lock
```

### 3. Deployment Scripts

```
start-dev.bat         # Windows: starts backend + opens browser
stop-dev.bat          # Windows: kills uvicorn processes
push-to-github.bat    # Windows: git add . && commit && push
```

### 4. Utility Scripts

```
create_test_account.py   # Seeds test users + accounts for demo
trigger_sync.py          # Syncs frontend changes to Docker volume
update_layouts.py        # Batch-updates CSS layout variables
fix_css.py               # Validates and fixes broken CSS variables
```

### 5. CI/CD Pipeline (`.github/workflows/ci.yml`)

- Runs on every push to `main` and `dev`
- Steps: lint (ruff) → type check (mypy) → unit tests (pytest) → Docker build

---

## 🎯 Live Demo Script

```
1.  Open http://localhost:3000
2.  Register new user (show TC Kimlik validation)
3.  Login → Dashboard (show balance stats)
4.  Open a new account
5.  Top Up via card (show card detection: type 4→Visa, 9792→Troy)
6.  Transfer → FAST (show ₺100k limit warning if amount > 100000)
7.  Transfer → SWIFT (show extra fields: BIC, currency, beneficiary)
8.  Transfer → EFT (show business hours note)
9.  Transaction History (show DEBIT + CREDIT paired entries)
10. Switch language (TR → EN → RU, everything translates instantly)
11. Admin panel → Audit Trail (show every action logged)
12. API → http://localhost:8000/docs (show Swagger UI)
13. GET /events (show TransferCreated, AccountDebited, AccountCredited)
```

---

## 📐 Architecture Decisions (Explained to Professor)

### Why Modular Monolith instead of Microservices?

Financial consistency is critical. With microservices, a transfer between two services requires a **saga pattern** — if service B fails after service A already debited the account, you need a compensating transaction to reverse it. This adds enormous complexity.

With a monolith + `threading.RLock()`, the entire transfer is atomic — **both debit and credit happen inside one lock, one function, in one process.** No distributed transaction needed.

> *"The best architecture is the one that solves the problem with the least accidental complexity."*

### Why `decimal.Decimal` instead of `float`?

```python
>>> 0.1 + 0.2
0.30000000000000004   # float — WRONG for banking
>>> Decimal("0.1") + Decimal("0.2")
Decimal("0.3")        # exact — correct
```

Every financial system uses exact decimal arithmetic. ISO 20022 and accounting standards mandate this.

### Why Custom JWT instead of a library?

1. No external dependency = smaller attack surface
2. Demonstrates understanding of how JWT works internally (header, payload, HMAC signature)
3. Full control over token claims and expiry logic

---

## 🏦 Banking Standards We Implemented

| Standard | How We Implement It |
|---|---|
| **ISO 20022** | Transfer endpoint structure mirrors `pacs.008` (payment initiation) — debtor, creditor, amount, currency, reference |
| **PSD2 / Open Banking** | JWT Bearer token flow mirrors OAuth2 access token. RBAC maps to PSD2 TPP consent scopes |
| **SWIFT MT103** | SWIFT transfer requires BIC code, IBAN, beneficiary name, currency — exactly MT103 mandatory fields |
| **TCMB FAST Regulation** | ₺100,000 per transaction limit enforced with real error message citing TCMB regulation |
| **Double-Entry Bookkeeping** | Every transfer: DEBIT sender + CREDIT receiver. `|DEBIT| = |CREDIT|` always |
| **PCI DSS Req. 10** | Audit log captures: `user_id`, `action`, `resource`, `outcome`, `ip_address`, `timestamp` |
| **EMV Authorization** | Balance check, account ownership check, and amount validation before any debit |

---

## 📅 Week 3 Plan

| Task | Owner | Due |
|---|---|---|
| MongoDB migration (replace in-memory store with `motor`) | Backend | Week 3 |
| Webhook HTTP delivery with retry (httpx + tenacity) | Backend | Week 3 |
| GitHub Actions CI/CD pipeline activation | DevOps | Week 3 |
| Final presentation slides (12–15 min) | All | Week 3 |
| End-to-end demo recording | All | Week 3 |

---

*Fintech Banking System · Team 2 · 2025-2026 FinTech Course*
