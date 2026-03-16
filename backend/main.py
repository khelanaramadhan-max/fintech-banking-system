"""
NeoBank — Core Banking API
FastAPI · Append-Only Ledger · JWT Auth · RBAC · Audit Logging
"""

from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, EmailStr, field_validator
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import uuid4
from enum import Enum
import threading
import hashlib
import hmac
import base64
import json
import time
import logging
import os

# ---------------------------------------------------------------------------
# Structured Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}'
)
logger = logging.getLogger("neobank")

SECRET_KEY = os.getenv("JWT_SECRET", "super-secret-change-in-production")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
TOKEN_EXPIRE_HOURS = 24

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TransactionType(str, Enum):
    CREDIT = "CREDIT"
    DEBIT = "DEBIT"

class AccountStatus(str, Enum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"

class CustomerStatus(str, Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"

class UserRole(str, Enum):
    CUSTOMER = "customer"
    ADMIN = "admin"

class EventType(str, Enum):
    TRANSFER_CREATED = "TransferCreated"
    TRANSFER_COMPLETED = "TransferCompleted"
    ACCOUNT_DEBITED = "AccountDebited"
    ACCOUNT_CREDITED = "AccountCredited"

# ---------------------------------------------------------------------------
# Domain Models
# ---------------------------------------------------------------------------

class LedgerEntry(BaseModel):
    entry_id: str
    account_id: str
    transaction_type: TransactionType
    amount: Decimal
    balance_after: Decimal
    reference_id: str
    description: str
    timestamp: datetime
    performed_by: str

class AuditLog(BaseModel):
    log_id: str
    user_id: str
    action: str
    resource: str
    outcome: str
    timestamp: datetime
    ip_address: Optional[str] = None

class EventLog(BaseModel):
    event_id: str
    event_type: EventType
    payload: dict
    timestamp: datetime

class Customer(BaseModel):
    customer_id: str
    full_name: str
    email: str
    phone: str
    national_id: str
    status: CustomerStatus
    created_at: datetime

class Account(BaseModel):
    account_id: str
    customer_id: str
    account_number: str
    balance: Decimal
    status: AccountStatus
    created_at: datetime

class User(BaseModel):
    user_id: str
    email: str
    password_hash: str
    role: UserRole
    customer_id: Optional[str] = None

# ---------------------------------------------------------------------------
# JWT Helpers
# ---------------------------------------------------------------------------

def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def _b64decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)

def create_token(payload: dict) -> str:
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload["exp"] = int(time.time()) + TOKEN_EXPIRE_HOURS * 3600
    body = _b64encode(json.dumps(payload).encode())
    sig = hmac.new(SECRET_KEY.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64encode(sig)}"

def decode_token(token: str) -> dict:
    try:
        header, body, sig = token.split(".")
        expected = hmac.new(SECRET_KEY.encode(), f"{header}.{body}".encode(), hashlib.sha256).digest()
        if not hmac.compare_digest(_b64encode(expected), sig):
            raise ValueError("bad signature")
        data = json.loads(_b64decode(body))
        if data.get("exp", 0) < time.time():
            raise ValueError("expired")
        return data
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

# ---------------------------------------------------------------------------
# In-Memory Store (Thread-Safe)
# ---------------------------------------------------------------------------

class BankStore:
    def __init__(self):
        self._lock = threading.RLock()
        self.users: dict[str, User] = {}
        self.customers: dict[str, Customer] = {}
        self.accounts: dict[str, Account] = {}
        self.ledger: list[LedgerEntry] = []
        self.audit_logs: list[AuditLog] = []
        self.event_log: list[EventLog] = []
        self._seed_admin()

    def _seed_admin(self):
        uid = "user_admin"
        self.users[uid] = User(
            user_id=uid, email="admin@neobank.io",
            password_hash=hash_password(ADMIN_PASSWORD),
            role=UserRole.ADMIN
        )

    # -- Auth --
    def authenticate(self, email: str, password: str) -> Optional[User]:
        with self._lock:
            for u in self.users.values():
                if u.email == email and u.password_hash == hash_password(password):
                    return u
            return None

    def get_user(self, user_id: str) -> Optional[User]:
        return self.users.get(user_id)

    # -- Customers --
    def create_customer(self, full_name, email, phone, national_id, password) -> tuple[Customer, User]:
        with self._lock:
            for u in self.users.values():
                if u.email == email:
                    raise ValueError("Email already registered")
            cid = f"cust_{uuid4().hex[:8]}"
            uid = f"user_{uuid4().hex[:8]}"
            customer = Customer(
                customer_id=cid, full_name=full_name, email=email,
                phone=phone, national_id=national_id,
                status=CustomerStatus.VERIFIED,
                created_at=datetime.now(timezone.utc)
            )
            user = User(
                user_id=uid, email=email,
                password_hash=hash_password(password),
                role=UserRole.CUSTOMER, customer_id=cid
            )
            self.customers[cid] = customer
            self.users[uid] = user
            return customer, user

    def list_customers(self) -> list[Customer]:
        return list(self.customers.values())

    def get_customer(self, cid: str) -> Optional[Customer]:
        return self.customers.get(cid)

    # -- Accounts --
    def create_account(self, customer_id: str, opening_balance: Decimal, performed_by: str) -> Account:
        with self._lock:
            if customer_id not in self.customers:
                raise KeyError(f"Customer {customer_id} not found")
            acc_num = f"NB{str(int(time.time()))[-8:]}{uuid4().hex[:4].upper()}"
            aid = f"acc_{uuid4().hex[:8]}"
            acc = Account(
                account_id=aid, customer_id=customer_id,
                account_number=acc_num, balance=opening_balance,
                status=AccountStatus.ACTIVE,
                created_at=datetime.now(timezone.utc)
            )
            self.accounts[aid] = acc
            if opening_balance > 0:
                self._append_ledger(aid, TransactionType.CREDIT, opening_balance,
                                    opening_balance, str(uuid4()), "Opening deposit", performed_by)
            return acc

    def get_account(self, aid: str) -> Optional[Account]:
        return self.accounts.get(aid)

    def list_accounts(self, customer_id: Optional[str] = None) -> list[Account]:
        with self._lock:
            accs = list(self.accounts.values())
            if customer_id:
                accs = [a for a in accs if a.customer_id == customer_id]
            return accs

    # -- Deposits / Withdrawals --
    def deposit(self, account_id: str, amount: Decimal, performed_by: str) -> Account:
        with self._lock:
            acc = self._get_active_account(account_id)
            acc.balance += amount
            ref = str(uuid4())
            self._append_ledger(account_id, TransactionType.CREDIT, amount, acc.balance, ref, "Deposit", performed_by)
            self._emit_event(EventType.ACCOUNT_CREDITED, {"account_id": account_id, "amount": str(amount), "ref": ref})
            return acc

    def withdraw(self, account_id: str, amount: Decimal, performed_by: str) -> Account:
        with self._lock:
            acc = self._get_active_account(account_id)
            if acc.balance < amount:
                raise ValueError("Insufficient funds")
            acc.balance -= amount
            ref = str(uuid4())
            self._append_ledger(account_id, TransactionType.DEBIT, amount, acc.balance, ref, "Withdrawal", performed_by)
            self._emit_event(EventType.ACCOUNT_DEBITED, {"account_id": account_id, "amount": str(amount), "ref": ref})
            return acc

    # -- Transfers --
    def transfer(self, from_id: str, to_id: str, amount: Decimal, description: str, performed_by: str) -> str:
        with self._lock:
            from_acc = self._get_active_account(from_id)
            to_acc = self._get_active_account(to_id)
            if from_acc.balance < amount:
                raise ValueError("Insufficient funds")
            ref = str(uuid4())
            self._emit_event(EventType.TRANSFER_CREATED, {"from": from_id, "to": to_id, "amount": str(amount), "ref": ref})
            from_acc.balance -= amount
            self._append_ledger(from_id, TransactionType.DEBIT, amount, from_acc.balance, ref, description or f"Transfer to {to_id}", performed_by)
            self._emit_event(EventType.ACCOUNT_DEBITED, {"account_id": from_id, "amount": str(amount), "ref": ref})
            to_acc.balance += amount
            self._append_ledger(to_id, TransactionType.CREDIT, amount, to_acc.balance, ref, description or f"Transfer from {from_id}", performed_by)
            self._emit_event(EventType.ACCOUNT_CREDITED, {"account_id": to_id, "amount": str(amount), "ref": ref})
            self._emit_event(EventType.TRANSFER_COMPLETED, {"from": from_id, "to": to_id, "amount": str(amount), "ref": ref})
            return ref

    # -- Ledger --
    def get_ledger(self, account_id: Optional[str] = None) -> list[LedgerEntry]:
        with self._lock:
            if account_id:
                return [e for e in self.ledger if e.account_id == account_id]
            return list(self.ledger)

    # -- Audit --
    def add_audit(self, user_id: str, action: str, resource: str, outcome: str, ip: Optional[str] = None):
        with self._lock:
            self.audit_logs.append(AuditLog(
                log_id=str(uuid4()), user_id=user_id, action=action,
                resource=resource, outcome=outcome,
                timestamp=datetime.now(timezone.utc), ip_address=ip
            ))

    def get_audit_logs(self) -> list[AuditLog]:
        return list(self.audit_logs)

    def get_events(self) -> list[EventLog]:
        return list(self.event_log)

    # -- Private --
    def _get_active_account(self, aid: str) -> Account:
        acc = self.accounts.get(aid)
        if not acc:
            raise KeyError(f"Account {aid} not found")
        if acc.status != AccountStatus.ACTIVE:
            raise ValueError(f"Account {aid} is {acc.status}")
        return acc

    def _append_ledger(self, account_id, tx_type, amount, balance_after, ref, desc, performed_by):
        self.ledger.append(LedgerEntry(
            entry_id=str(uuid4()), account_id=account_id,
            transaction_type=tx_type, amount=amount,
            balance_after=balance_after, reference_id=ref,
            description=desc, timestamp=datetime.now(timezone.utc),
            performed_by=performed_by
        ))

    def _emit_event(self, event_type: EventType, payload: dict):
        self.event_log.append(EventLog(
            event_id=str(uuid4()), event_type=event_type,
            payload=payload, timestamp=datetime.now(timezone.utc)
        ))

store = BankStore()

# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    full_name: str = Field(..., min_length=2)
    email: str
    phone: str
    national_id: str
    password: str = Field(..., min_length=6)

class LoginRequest(BaseModel):
    email: str
    password: str

class CreateAccountRequest(BaseModel):
    customer_id: str
    opening_balance: Decimal = Field(default=Decimal("0"), ge=0)

    @field_validator("opening_balance", mode="before")
    @classmethod
    def two_dp(cls, v): return round(Decimal(str(v)), 2)

class DepositRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)

    @field_validator("amount", mode="before")
    @classmethod
    def two_dp(cls, v): return round(Decimal(str(v)), 2)

class WithdrawRequest(BaseModel):
    amount: Decimal = Field(..., gt=0)

    @field_validator("amount", mode="before")
    @classmethod
    def two_dp(cls, v): return round(Decimal(str(v)), 2)

class TransferRequest(BaseModel):
    from_account_id: str
    to_account_id: str
    amount: Decimal = Field(..., gt=0)
    description: str = Field(default="", max_length=256)

    @field_validator("amount", mode="before")
    @classmethod
    def two_dp(cls, v): return round(Decimal(str(v)), 2)

# ---------------------------------------------------------------------------
# Auth Dependency
# ---------------------------------------------------------------------------

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> User:
    data = decode_token(credentials.credentials)
    user = store.get_user(data["user_id"])
    if not user:
        raise HTTPException(401, "User not found")
    return user

def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(403, "Admin access required")
    return user

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="NeoBank API",
    description="Core Banking System — Append-Only Ledger with JWT Auth & RBAC",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting (simple in-memory)
_rate: dict[str, list] = {}
_rate_lock = threading.Lock()

@app.middleware("http")
async def rate_limit(request: Request, call_next):
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    with _rate_lock:
        hits = [t for t in _rate.get(ip, []) if now - t < 60]
        if len(hits) >= 100:
            return JSONResponse({"detail": "Rate limit exceeded"}, status_code=429)
        hits.append(now)
        _rate[ip] = hits
    return await call_next(request)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["System"])
def health(): return {"status": "ok", "timestamp": datetime.now(timezone.utc)}


# -- Auth --
@app.post("/auth/register", tags=["Auth"], status_code=201)
def register(body: RegisterRequest, request: Request):
    try:
        customer, user = store.create_customer(
            body.full_name, body.email, body.phone, body.national_id, body.password
        )
        token = create_token({"user_id": user.user_id, "role": user.role, "customer_id": user.customer_id})
        store.add_audit(user.user_id, "REGISTER", f"customer:{customer.customer_id}", "SUCCESS", request.client.host if request.client else None)
        logger.info(f"New customer registered: {customer.customer_id}")
        return {"token": token, "user_id": user.user_id, "customer_id": customer.customer_id, "role": user.role}
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/auth/login", tags=["Auth"])
def login(body: LoginRequest, request: Request):
    user = store.authenticate(body.email, body.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    token = create_token({"user_id": user.user_id, "role": user.role, "customer_id": user.customer_id})
    store.add_audit(user.user_id, "LOGIN", "auth", "SUCCESS", request.client.host if request.client else None)
    logger.info(f"User logged in: {user.user_id}")
    return {"token": token, "user_id": user.user_id, "role": user.role, "customer_id": user.customer_id}


@app.get("/auth/me", tags=["Auth"])
def me(user: User = Depends(get_current_user)):
    return {"user_id": user.user_id, "email": user.email, "role": user.role, "customer_id": user.customer_id}


# -- Customers --
@app.get("/customers", tags=["Customers"])
def list_customers(user: User = Depends(require_admin)):
    return store.list_customers()


@app.get("/customers/{customer_id}", tags=["Customers"])
def get_customer(customer_id: str, user: User = Depends(get_current_user)):
    if user.role != UserRole.ADMIN and user.customer_id != customer_id:
        raise HTTPException(403, "Access denied")
    c = store.get_customer(customer_id)
    if not c: raise HTTPException(404, "Customer not found")
    return c


# -- Accounts --
@app.post("/accounts", tags=["Accounts"], status_code=201)
def create_account(body: CreateAccountRequest, request: Request, user: User = Depends(get_current_user)):
    if user.role != UserRole.ADMIN and user.customer_id != body.customer_id:
        raise HTTPException(403, "Access denied")
    try:
        acc = store.create_account(body.customer_id, body.opening_balance, user.user_id)
        store.add_audit(user.user_id, "CREATE_ACCOUNT", f"account:{acc.account_id}", "SUCCESS", request.client.host if request.client else None)
        return acc
    except KeyError as e:
        raise HTTPException(404, str(e))


@app.get("/accounts", tags=["Accounts"])
def list_accounts(customer_id: Optional[str] = None, user: User = Depends(get_current_user)):
    if user.role == UserRole.CUSTOMER:
        customer_id = user.customer_id
    return store.list_accounts(customer_id)


@app.get("/accounts/{account_id}", tags=["Accounts"])
def get_account(account_id: str, user: User = Depends(get_current_user)):
    acc = store.get_account(account_id)
    if not acc: raise HTTPException(404, "Account not found")
    if user.role == UserRole.CUSTOMER and acc.customer_id != user.customer_id:
        raise HTTPException(403, "Access denied")
    return acc


@app.post("/accounts/{account_id}/deposit", tags=["Accounts"])
def deposit(account_id: str, body: DepositRequest, request: Request, user: User = Depends(get_current_user)):
    acc = store.get_account(account_id)
    if not acc: raise HTTPException(404, "Account not found")
    if user.role == UserRole.CUSTOMER and acc.customer_id != user.customer_id:
        raise HTTPException(403, "Access denied")
    try:
        updated = store.deposit(account_id, body.amount, user.user_id)
        store.add_audit(user.user_id, "DEPOSIT", f"account:{account_id}", "SUCCESS", request.client.host if request.client else None)
        return updated
    except Exception as e:
        raise HTTPException(422, str(e))


@app.post("/accounts/{account_id}/withdraw", tags=["Accounts"])
def withdraw(account_id: str, body: WithdrawRequest, request: Request, user: User = Depends(get_current_user)):
    acc = store.get_account(account_id)
    if not acc: raise HTTPException(404, "Account not found")
    if user.role == UserRole.CUSTOMER and acc.customer_id != user.customer_id:
        raise HTTPException(403, "Access denied")
    try:
        updated = store.withdraw(account_id, body.amount, user.user_id)
        store.add_audit(user.user_id, "WITHDRAW", f"account:{account_id}", "SUCCESS", request.client.host if request.client else None)
        return updated
    except ValueError as e:
        raise HTTPException(422, str(e))


# -- Transfers --
@app.post("/transfers", tags=["Transfers"], status_code=201)
def transfer(body: TransferRequest, request: Request, user: User = Depends(get_current_user)):
    if body.from_account_id == body.to_account_id:
        raise HTTPException(422, "Source and destination must differ")
    from_acc = store.get_account(body.from_account_id)
    if not from_acc: raise HTTPException(404, f"Account {body.from_account_id} not found")
    if user.role == UserRole.CUSTOMER and from_acc.customer_id != user.customer_id:
        raise HTTPException(403, "Access denied")
    try:
        ref = store.transfer(body.from_account_id, body.to_account_id, body.amount, body.description, user.user_id)
        store.add_audit(user.user_id, "TRANSFER", f"{body.from_account_id}->{body.to_account_id}", "SUCCESS", request.client.host if request.client else None)
        logger.info(f"Transfer {ref}: {body.from_account_id} -> {body.to_account_id} ${body.amount}")
        return {"reference_id": ref, "from_account_id": body.from_account_id, "to_account_id": body.to_account_id, "amount": body.amount, "timestamp": datetime.now(timezone.utc)}
    except (KeyError, ValueError) as e:
        status_code = 404 if isinstance(e, KeyError) else 422
        raise HTTPException(status_code, str(e))


# -- Ledger --
@app.get("/accounts/{account_id}/ledger", tags=["Ledger"])
def get_account_ledger(account_id: str, user: User = Depends(get_current_user)):
    acc = store.get_account(account_id)
    if not acc: raise HTTPException(404, "Account not found")
    if user.role == UserRole.CUSTOMER and acc.customer_id != user.customer_id:
        raise HTTPException(403, "Access denied")
    return store.get_ledger(account_id)


@app.get("/ledger", tags=["Ledger"])
def full_ledger(user: User = Depends(require_admin)):
    return store.get_ledger()


# -- Audit --
@app.get("/audit", tags=["Admin"])
def audit_logs(user: User = Depends(require_admin)):
    return store.get_audit_logs()


@app.get("/events", tags=["Admin"])
def event_stream(user: User = Depends(require_admin)):
    return store.get_events()
