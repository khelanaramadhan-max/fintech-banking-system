"""
NeoBank — Core Banking API
FastAPI · Supabase Postgres · JWT Auth · RBAC · Audit Logging
"""

from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, EmailStr, field_validator
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Optional, List
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

from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# Supabase Client
# ---------------------------------------------------------------------------
from supabase import create_client, Client

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://llchohlypyizjrzuypxr.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxsY2hvaGx5cHlpempyenV5cHhyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzM2NjkwNjEsImV4cCI6MjA4OTI0NTA2MX0.THTxZkZ7Rc1pPvH1V3WGmLz4lGtfhyRYBbEBKlIHoPU")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ---------------------------------------------------------------------------
# Structured Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","msg":"%(message)s"}'
)
logger = logging.getLogger("neobank")

SECRET_KEY    = os.getenv("JWT_SECRET", "super-secret-change-in-production")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Admin123!")
TOKEN_EXPIRE_HOURS = 24

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TransactionType(str, Enum):
    CREDIT = "CREDIT"
    DEBIT  = "DEBIT"

class AccountStatus(str, Enum):
    ACTIVE    = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED    = "CLOSED"

class CustomerStatus(str, Enum):
    PENDING  = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"

class UserRole(str, Enum):
    CUSTOMER = "customer"
    ADMIN    = "admin"

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
# Supabase helpers
# ---------------------------------------------------------------------------

def _sb_user_to_dict(row: dict) -> dict:
    """Normalise a ft_users row into our internal user shape."""
    return {
        "user_id":     row["id"],
        "email":       row["email"],
        "password_hash": hash_password(row["password"]),  # kept hashed for JWT
        "role":        row["role"],
        "customer_id": row.get("id"),   # in our model user_id == customer_id
        # pass-through for auth check
        "_password":   row["password"],
    }

def authenticate_user(email: str, password: str) -> Optional[dict]:
    try:
        res = supabase.table("ft_users").select("*").eq("email", email).execute()
        if res.data and res.data[0]["password"] == password:
            return _sb_user_to_dict(res.data[0])
        return None
    except Exception as e:
        logger.error(f"authenticate error: {e}")
        return None

def get_user_by_id(user_id: str) -> Optional[dict]:
    try:
        res = supabase.table("ft_users").select("*").eq("id", user_id).execute()
        if res.data:
            return _sb_user_to_dict(res.data[0])
        return None
    except Exception as e:
        logger.error(f"get_user error: {e}")
        return None

def create_user_in_db(name: str, email: str, phone: str, national_id: str, password: str) -> dict:
    """Insert to ft_users and return the new user dict."""
    uid = f"user_{uuid4().hex[:8]}"
    row = {
        "id":       uid,
        "name":     name,
        "email":    email,
        "password": password,
        "tcno":     national_id,
        "phone":    phone,
        "role":     "customer",
    }
    res = supabase.table("ft_users").insert(row).execute()
    if not res.data:
        raise ValueError("Failed to create user in database")
    # Create a default account
    create_account_in_db(uid, Decimal("0"), uid, account_type="Vadesiz")
    return _sb_user_to_dict(res.data[0])

def list_customers_from_db() -> List[dict]:
    try:
        res = supabase.table("ft_users").select("*").eq("role", "customer").execute()
        return res.data or []
    except Exception:
        return []

def get_customer_from_db(customer_id: str) -> Optional[dict]:
    try:
        res = supabase.table("ft_users").select("*").eq("id", customer_id).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None

def create_account_in_db(user_id: str, opening_balance: Decimal, performed_by: str, account_type: str = "Vadesiz") -> dict:
    acc_num = f"FT{str(int(time.time()))[-8:]}{uuid4().hex[:4].upper()}"
    aid = f"acc_{uuid4().hex[:8]}"
    row = {
        "id":      aid,
        "user_id": user_id,
        "number":  acc_num,
        "type":    account_type,
        "balance": float(opening_balance),
        "color":   "ac-blue",
    }
    res = supabase.table("ft_accounts").insert(row).execute()
    if not res.data:
        raise ValueError("Failed to create account")
    acc = res.data[0]
    if opening_balance > 0:
        _append_ledger_db(aid, "CREDIT", opening_balance, opening_balance,
                          str(uuid4()), "Opening deposit", performed_by)
    return acc

def get_account_from_db(account_id: str) -> Optional[dict]:
    try:
        res = supabase.table("ft_accounts").select("*").eq("id", account_id).execute()
        return res.data[0] if res.data else None
    except Exception:
        return None

def list_accounts_from_db(user_id: Optional[str] = None) -> List[dict]:
    try:
        q = supabase.table("ft_accounts").select("*")
        if user_id:
            q = q.eq("user_id", user_id)
        return q.execute().data or []
    except Exception:
        return []

def deposit_in_db(account_id: str, amount: Decimal, performed_by: str) -> dict:
    acc = get_account_from_db(account_id)
    if not acc:
        raise KeyError(f"Account {account_id} not found")
    new_bal = Decimal(str(acc["balance"])) + amount
    supabase.table("ft_accounts").update({"balance": float(new_bal)}).eq("id", account_id).execute()
    ref = str(uuid4())
    _append_ledger_db(account_id, "CREDIT", amount, new_bal, ref, "Deposit", performed_by)
    acc["balance"] = float(new_bal)
    return acc

def withdraw_in_db(account_id: str, amount: Decimal, performed_by: str) -> dict:
    acc = get_account_from_db(account_id)
    if not acc:
        raise KeyError(f"Account {account_id} not found")
    bal = Decimal(str(acc["balance"]))
    if bal < amount:
        raise ValueError("Insufficient funds")
    new_bal = bal - amount
    supabase.table("ft_accounts").update({"balance": float(new_bal)}).eq("id", account_id).execute()
    ref = str(uuid4())
    _append_ledger_db(account_id, "DEBIT", amount, new_bal, ref, "Withdrawal", performed_by)
    acc["balance"] = float(new_bal)
    return acc

def transfer_in_db(from_id: str, to_id: str, amount: Decimal, description: str, performed_by: str) -> str:
    from_acc = get_account_from_db(from_id)
    to_acc   = get_account_from_db(to_id)
    if not from_acc:
        raise KeyError(f"Account {from_id} not found")
    if not to_acc:
        raise KeyError(f"Account {to_id} not found")
    from_bal = Decimal(str(from_acc["balance"]))
    if from_bal < amount:
        raise ValueError("Insufficient funds")
    to_bal   = Decimal(str(to_acc["balance"]))
    ref = str(uuid4())
    new_from = from_bal - amount
    new_to   = to_bal + amount
    supabase.table("ft_accounts").update({"balance": float(new_from)}).eq("id", from_id).execute()
    supabase.table("ft_accounts").update({"balance": float(new_to)}).eq("id", to_id).execute()
    _append_ledger_db(from_id, "DEBIT",  amount, new_from, ref, description or f"Transfer to {to_id}",   performed_by)
    _append_ledger_db(to_id,   "CREDIT", amount, new_to,   ref, description or f"Transfer from {from_id}", performed_by)
    return ref

def _append_ledger_db(account_id: str, tx_type: str, amount: Decimal,
                       balance_after: Decimal, ref: str, desc: str, performed_by: str):
    row = {
        "id":            str(uuid4()),
        "account_id":    account_id,
        "type":          tx_type,
        "amount":        float(amount),
        "balance_after": float(balance_after),
        "description":   desc,
        "ref":           ref,
        "performed_by":  performed_by,
    }
    supabase.table("ft_ledger").insert(row).execute()

def get_ledger_from_db(account_id: Optional[str] = None) -> List[dict]:
    try:
        q = supabase.table("ft_ledger").select("*").order("created_at", desc=True)
        if account_id:
            q = q.eq("account_id", account_id)
        return q.execute().data or []
    except Exception:
        return []

def add_audit_to_db(user_id: str, action: str, detail: str, outcome: str, ip: Optional[str] = None):
    row = {
        "id":       str(uuid4()),
        "user_id":  user_id,
        "action":   action,
        "detail":   detail,
        "outcome":  outcome,
    }
    try:
        supabase.table("ft_audit").insert(row).execute()
    except Exception as e:
        logger.warning(f"Audit log failed: {e}")

def get_audit_from_db() -> List[dict]:
    try:
        return supabase.table("ft_audit").select("*").order("created_at", desc=True).limit(500).execute().data or []
    except Exception:
        return []

# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    full_name:   str = Field(..., min_length=2)
    email:       EmailStr
    phone:       str
    national_id: str
    password:    str = Field(..., min_length=6)
    security_question_id: Optional[int] = None
    security_answer: Optional[str] = None

class LoginRequest(BaseModel):
    email:    EmailStr
    password: str

class CreateAccountRequest(BaseModel):
    customer_id:     str
    opening_balance: Decimal = Field(default=Decimal("0"), ge=0)
    account_type:    str = Field(default="Vadesiz")

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
    to_account_id:   str
    amount:          Decimal = Field(..., gt=0)
    description:     str = Field(default="", max_length=256)

    @field_validator("amount", mode="before")
    @classmethod
    def two_dp(cls, v): return round(Decimal(str(v)), 2)

# ---------------------------------------------------------------------------
# Auth Dependency
# ---------------------------------------------------------------------------

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    data = decode_token(credentials.credentials)
    user = get_user_by_id(data["user_id"])
    if not user:
        raise HTTPException(401, "User not found")
    return user

def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != UserRole.ADMIN:
        raise HTTPException(403, "Admin access required")
    return user

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="NeoBank API",
    description="Core Banking System — Supabase Postgres · JWT Auth · RBAC",
    version="2.0.0",
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
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc), "db": "supabase"}


# -- Auth --
@app.post("/auth/register", tags=["Auth"], status_code=201)
def register(body: RegisterRequest, request: Request):
    # Check duplicate email
    existing = supabase.table("ft_users").select("id").eq("email", str(body.email)).execute()
    if existing.data:
        raise HTTPException(409, "Email already registered")
    try:
        user = create_user_in_db(body.full_name, str(body.email), body.phone, body.national_id, body.password)
        if body.security_question_id and body.security_answer:
            ans_hash = hashlib.sha256(body.security_answer.strip().lower().encode()).hexdigest()
            supabase.table("ft_security_answers").insert({
                "user_id": user["user_id"],
                "question_id": body.security_question_id,
                "answer_hash": ans_hash
            }).execute()
        token = create_token({"user_id": user["user_id"], "role": user["role"], "customer_id": user["customer_id"]})
        add_audit_to_db(user["user_id"], "REGISTER", f"user:{user['user_id']}", "SUCCESS",
                        request.client.host if request.client else None)
        logger.info(f"New customer registered: {user['user_id']}")
        return {"token": token, "user_id": user["user_id"], "customer_id": user["customer_id"], "role": user["role"]}
    except Exception as e:
        raise HTTPException(422, str(e))


@app.post("/auth/login", tags=["Auth"])
def login(body: LoginRequest, request: Request):
    user = authenticate_user(str(body.email), body.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    token = create_token({"user_id": user["user_id"], "role": user["role"], "customer_id": user["customer_id"]})
    add_audit_to_db(user["user_id"], "LOGIN", "auth", "SUCCESS",
                    request.client.host if request.client else None)
    logger.info(f"User logged in: {user['user_id']}")
    return {"token": token, "user_id": user["user_id"], "role": user["role"], "customer_id": user["customer_id"]}


@app.get("/auth/me", tags=["Auth"])
def me(user: dict = Depends(get_current_user)):
    return {"user_id": user["user_id"], "email": user["email"], "role": user["role"], "customer_id": user["customer_id"]}


# -- Customers --
@app.get("/customers", tags=["Customers"])
def list_customers(user: dict = Depends(require_admin)):
    return list_customers_from_db()


@app.get("/customers/{customer_id}", tags=["Customers"])
def get_customer(customer_id: str, user: dict = Depends(get_current_user)):
    if user["role"] != UserRole.ADMIN and user["customer_id"] != customer_id:
        raise HTTPException(403, "Access denied")
    c = get_customer_from_db(customer_id)
    if not c:
        raise HTTPException(404, "Customer not found")
    return c


# -- Accounts --
@app.post("/accounts", tags=["Accounts"], status_code=201)
def create_account(body: CreateAccountRequest, request: Request, user: dict = Depends(get_current_user)):
    if user["role"] != UserRole.ADMIN and user["customer_id"] != body.customer_id:
        raise HTTPException(403, "Access denied")
    try:
        acc = create_account_in_db(body.customer_id, body.opening_balance, user["user_id"], body.account_type)
        add_audit_to_db(user["user_id"], "CREATE_ACCOUNT", f"account:{acc['id']}", "SUCCESS",
                        request.client.host if request.client else None)
        return acc
    except (KeyError, ValueError) as e:
        raise HTTPException(422, str(e))


@app.get("/accounts", tags=["Accounts"])
def list_accounts(customer_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    uid = customer_id if user["role"] == UserRole.ADMIN else user["customer_id"]
    return list_accounts_from_db(uid)


@app.get("/accounts/{account_id}", tags=["Accounts"])
def get_account(account_id: str, user: dict = Depends(get_current_user)):
    acc = get_account_from_db(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if user["role"] == UserRole.CUSTOMER and acc["user_id"] != user["customer_id"]:
        raise HTTPException(403, "Access denied")
    return acc


@app.post("/accounts/{account_id}/deposit", tags=["Accounts"])
def deposit(account_id: str, body: DepositRequest, request: Request, user: dict = Depends(get_current_user)):
    acc = get_account_from_db(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if user["role"] == UserRole.CUSTOMER and acc["user_id"] != user["customer_id"]:
        raise HTTPException(403, "Access denied")
    try:
        updated = deposit_in_db(account_id, body.amount, user["user_id"])
        add_audit_to_db(user["user_id"], "DEPOSIT", f"account:{account_id}", "SUCCESS",
                        request.client.host if request.client else None)
        return updated
    except Exception as e:
        raise HTTPException(422, str(e))


@app.post("/accounts/{account_id}/withdraw", tags=["Accounts"])
def withdraw(account_id: str, body: WithdrawRequest, request: Request, user: dict = Depends(get_current_user)):
    acc = get_account_from_db(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if user["role"] == UserRole.CUSTOMER and acc["user_id"] != user["customer_id"]:
        raise HTTPException(403, "Access denied")
    try:
        updated = withdraw_in_db(account_id, body.amount, user["user_id"])
        add_audit_to_db(user["user_id"], "WITHDRAW", f"account:{account_id}", "SUCCESS",
                        request.client.host if request.client else None)
        return updated
    except ValueError as e:
        raise HTTPException(422, str(e))


# -- Transfers --
@app.post("/transfers", tags=["Transfers"], status_code=201)
def transfer(body: TransferRequest, request: Request, user: dict = Depends(get_current_user)):
    if body.from_account_id == body.to_account_id:
        raise HTTPException(422, "Source and destination must differ")
    from_acc = get_account_from_db(body.from_account_id)
    if not from_acc:
        raise HTTPException(404, f"Account {body.from_account_id} not found")
    if user["role"] == UserRole.CUSTOMER and from_acc["user_id"] != user["customer_id"]:
        raise HTTPException(403, "Access denied")
    try:
        ref = transfer_in_db(body.from_account_id, body.to_account_id, body.amount, body.description, user["user_id"])
        add_audit_to_db(user["user_id"], "TRANSFER", f"{body.from_account_id}->{body.to_account_id}", "SUCCESS",
                        request.client.host if request.client else None)
        logger.info(f"Transfer {ref}: {body.from_account_id} -> {body.to_account_id} ${body.amount}")
        return {"reference_id": ref, "from_account_id": body.from_account_id,
                "to_account_id": body.to_account_id, "amount": body.amount,
                "timestamp": datetime.now(timezone.utc)}
    except (KeyError, ValueError) as e:
        code = 404 if isinstance(e, KeyError) else 422
        raise HTTPException(code, str(e))


# -- Ledger --
@app.get("/accounts/{account_id}/ledger", tags=["Ledger"])
def get_account_ledger(account_id: str, user: dict = Depends(get_current_user)):
    acc = get_account_from_db(account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if user["role"] == UserRole.CUSTOMER and acc["user_id"] != user["customer_id"]:
        raise HTTPException(403, "Access denied")
    return get_ledger_from_db(account_id)


@app.get("/ledger", tags=["Ledger"])
def full_ledger(user: dict = Depends(require_admin)):
    return get_ledger_from_db()


# -- Audit --
@app.get("/audit", tags=["Admin"])
def audit_logs(user: dict = Depends(require_admin)):
    return get_audit_from_db()


# ===========================================================================
# NEW REQUEST SCHEMAS
# ===========================================================================

class TransactionRequestBody(BaseModel):
    from_account_id: str
    to_account_id:   str
    amount:          Decimal = Field(..., gt=0)
    description:     str = Field(default="", max_length=256)
    @field_validator("amount", mode="before")
    @classmethod
    def two_dp(cls, v): return round(Decimal(str(v)), 2)

class ReviewDecision(BaseModel):
    note: str = Field(default="")

class LoanApplicationBody(BaseModel):
    account_id:      str
    loan_type:       str = Field(default="PERSONAL")
    principal_amount: Decimal = Field(..., gt=0)
    term_months:     int = Field(..., gt=0)
    purpose:         str = Field(default="")

class CardRequestBody(BaseModel):
    account_id:  str
    card_type:   str = Field(default="DEBIT")
    network:     str = Field(default="VISA")

class BeneficiaryBody(BaseModel):
    name:           str
    bank_name:      Optional[str] = None
    account_number: str
    iban:           Optional[str] = None
    currency:       str = Field(default="TRY")
    nickname:       Optional[str] = None

class SupportTicketBody(BaseModel):
    category:    str
    subject:     str
    description: str
    priority:    str = Field(default="MEDIUM")
    related_account_id: Optional[str] = None


# ===========================================================================
# TRANSACTION REQUESTS — requires admin approval for large/flagged transfers
# ===========================================================================

APPROVAL_THRESHOLD = Decimal("5000")  # Transfers above this need admin approval


def _risk_score(amount: Decimal, from_id: str, to_id: str) -> tuple[int, list]:
    flags = []
    score = 0
    if amount >= APPROVAL_THRESHOLD:
        flags.append("LARGE_AMOUNT"); score += 40
    if amount >= Decimal("20000"):
        flags.append("VERY_LARGE"); score += 30
    return min(score, 100), flags


@app.post("/transfers/request", tags=["Transfers"], status_code=201)
def request_transfer(body: TransactionRequestBody, request: Request,
                     user: dict = Depends(get_current_user)):
    """Submit a transfer. Large amounts go to admin approval queue."""
    from_acc = get_account_from_db(body.from_account_id)
    if not from_acc:
        raise HTTPException(404, "Source account not found")
    if user["role"] == UserRole.CUSTOMER and from_acc["user_id"] != user["customer_id"]:
        raise HTTPException(403, "Access denied")
    risk, flags = _risk_score(body.amount, body.from_account_id, body.to_account_id)
    needs_approval = risk >= 40 or user["role"] == UserRole.CUSTOMER

    if not needs_approval:
        # Execute immediately for admins on small amounts
        ref = transfer_in_db(body.from_account_id, body.to_account_id, body.amount,
                              body.description, user["user_id"])
        add_audit_to_db(user["user_id"], "TRANSFER_IMMEDIATE", body.from_account_id, "SUCCESS")
        return {"status": "EXECUTED", "reference_id": ref}

    txreq_id = f"txreq_{uuid4().hex[:8]}"
    row = {
        "id": txreq_id,
        "initiated_by": user["user_id"],
        "from_account_id": body.from_account_id,
        "to_account_id": body.to_account_id,
        "amount": float(body.amount),
        "currency": "TRY",
        "request_type": "TRANSFER",
        "description": body.description,
        "status": "PENDING",
        "risk_score": risk,
        "risk_flags": flags,
    }
    try:
        supabase.table("ft_transaction_requests").insert(row).execute()
        add_audit_to_db(user["user_id"], "TRANSFER_REQUEST", txreq_id, "PENDING")
        # Notify user
        supabase.table("ft_notifications").insert({
            "user_id": user["user_id"],
            "type": "TRANSACTION",
            "title": "Transfer Pending Approval",
            "body": f"Your transfer of {body.amount} TRY is awaiting admin approval.",
            "entity_type": "transaction_request",
            "entity_id": txreq_id,
            "priority": "HIGH",
        }).execute()
        return {"status": "PENDING", "request_id": txreq_id, "risk_score": risk}
    except Exception as e:
        raise HTTPException(422, str(e))


@app.get("/admin/transactions/pending", tags=["Admin"])
def pending_transactions(user: dict = Depends(require_admin)):
    """Admin: list all PENDING transaction requests."""
    try:
        data = (supabase.table("ft_transaction_requests")
                .select("*, ft_users!ft_transaction_requests_initiated_by_fkey(name,email)")
                .eq("status", "PENDING")
                .order("created_at", desc=True)
                .execute().data or [])
        return data
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/admin/transactions/all", tags=["Admin"])
def all_transaction_requests(user: dict = Depends(require_admin)):
    """Admin: list all transaction requests of any status."""
    try:
        return supabase.table("ft_transaction_requests").select("*").order("created_at", desc=True).execute().data or []
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/admin/transactions/{req_id}/approve", tags=["Admin"])
def approve_transaction(req_id: str, body: ReviewDecision, request: Request,
                        user: dict = Depends(require_admin)):
    """Admin: approve and execute a pending transaction."""
    res = supabase.table("ft_transaction_requests").select("*").eq("id", req_id).execute()
    if not res.data:
        raise HTTPException(404, "Request not found")
    txreq = res.data[0]
    if txreq["status"] != "PENDING":
        raise HTTPException(422, f"Cannot approve — status is {txreq['status']}")
    try:
        ref = transfer_in_db(txreq["from_account_id"], txreq["to_account_id"],
                              Decimal(str(txreq["amount"])), txreq.get("description",""),
                              user["user_id"])
        supabase.table("ft_transaction_requests").update({
            "status": "EXECUTED", "reviewed_by": user["user_id"],
            "review_note": body.note, "reviewed_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", req_id).execute()
        supabase.table("ft_notifications").insert({
            "user_id": txreq["initiated_by"],
            "type": "TRANSACTION",
            "title": "Transfer Approved ✅",
            "body": f"Your transfer of {txreq['amount']} TRY has been approved and executed.",
            "entity_type": "transaction_request", "entity_id": req_id, "priority": "HIGH",
        }).execute()
        add_audit_to_db(user["user_id"], "APPROVE_TRANSACTION", req_id, "SUCCESS")
        return {"status": "EXECUTED", "reference_id": ref}
    except Exception as e:
        raise HTTPException(422, str(e))


@app.post("/admin/transactions/{req_id}/reject", tags=["Admin"])
def reject_transaction(req_id: str, body: ReviewDecision, user: dict = Depends(require_admin)):
    """Admin: reject a pending transaction."""
    res = supabase.table("ft_transaction_requests").select("*").eq("id", req_id).execute()
    if not res.data:
        raise HTTPException(404, "Request not found")
    txreq = res.data[0]
    if txreq["status"] != "PENDING":
        raise HTTPException(422, f"Cannot reject — status is {txreq['status']}")
    supabase.table("ft_transaction_requests").update({
        "status": "REJECTED", "reviewed_by": user["user_id"],
        "review_note": body.note, "reviewed_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", req_id).execute()
    supabase.table("ft_notifications").insert({
        "user_id": txreq["initiated_by"],
        "type": "TRANSACTION",
        "title": "Transfer Rejected ❌",
        "body": f"Your transfer of {txreq['amount']} TRY was rejected. Reason: {body.note or 'No reason given.'}",
        "entity_type": "transaction_request", "entity_id": req_id, "priority": "HIGH",
    }).execute()
    add_audit_to_db(user["user_id"], "REJECT_TRANSACTION", req_id, "SUCCESS")
    return {"status": "REJECTED", "request_id": req_id}


# ===========================================================================
# LOANS
# ===========================================================================

INTEREST_RATES = {"PERSONAL": 0.0285, "MORTGAGE": 0.0195, "AUTO": 0.0245,
                   "BUSINESS": 0.0320, "STUDENT": 0.0150}

@app.post("/loans/apply", tags=["Loans"], status_code=201)
def apply_loan(body: LoanApplicationBody, user: dict = Depends(get_current_user)):
    acc = get_account_from_db(body.account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if user["role"] == UserRole.CUSTOMER and acc["user_id"] != user["customer_id"]:
        raise HTTPException(403, "Access denied")
    rate = INTEREST_RATES.get(body.loan_type, 0.0285)
    monthly = float(body.principal_amount) * rate / (1 - (1 + rate) ** (-body.term_months))
    total = monthly * body.term_months
    loan_id = f"loan_{uuid4().hex[:8]}"
    row = {
        "id": loan_id, "user_id": user["customer_id"], "account_id": body.account_id,
        "loan_type": body.loan_type, "principal_amount": float(body.principal_amount),
        "interest_rate": rate, "term_months": body.term_months,
        "monthly_payment": round(monthly, 2), "total_repayable": round(total, 2),
        "outstanding_balance": float(body.principal_amount),
        "status": "PENDING", "purpose": body.purpose,
    }
    try:
        supabase.table("ft_loans").insert(row).execute()
        add_audit_to_db(user["user_id"], "LOAN_APPLY", loan_id, "SUCCESS")
        return row
    except Exception as e:
        raise HTTPException(422, str(e))


@app.get("/loans", tags=["Loans"])
def list_loans(user: dict = Depends(get_current_user)):
    uid = None if user["role"] == UserRole.ADMIN else user["customer_id"]
    q = supabase.table("ft_loans").select("*").order("created_at", desc=True)
    if uid:
        q = q.eq("user_id", uid)
    return q.execute().data or []


@app.get("/admin/loans", tags=["Admin"])
def admin_list_loans(user: dict = Depends(require_admin)):
    return supabase.table("ft_loans").select("*").order("created_at", desc=True).execute().data or []


@app.post("/admin/loans/{loan_id}/approve", tags=["Admin"])
def approve_loan(loan_id: str, body: ReviewDecision, user: dict = Depends(require_admin)):
    res = supabase.table("ft_loans").select("*").eq("id", loan_id).execute()
    if not res.data:
        raise HTTPException(404, "Loan not found")
    loan = res.data[0]
    if loan["status"] not in ("PENDING", "UNDER_REVIEW"):
        raise HTTPException(422, f"Cannot approve — status is {loan['status']}")
    # Disburse: credit the account
    deposit_in_db(loan["account_id"], Decimal(str(loan["principal_amount"])), user["user_id"])
    supabase.table("ft_loans").update({
        "status": "ACTIVE", "reviewed_by": user["user_id"],
        "review_note": body.note, "disbursed_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", loan_id).execute()
    supabase.table("ft_notifications").insert({
        "user_id": loan["user_id"], "type": "LOAN",
        "title": "Loan Approved ✅",
        "body": f"Your {loan['loan_type']} loan of {loan['principal_amount']} TRY has been approved and disbursed.",
        "entity_type": "loan", "entity_id": loan_id, "priority": "HIGH",
    }).execute()
    add_audit_to_db(user["user_id"], "LOAN_APPROVE", loan_id, "SUCCESS")
    return {"status": "ACTIVE", "loan_id": loan_id}


@app.post("/admin/loans/{loan_id}/reject", tags=["Admin"])
def reject_loan(loan_id: str, body: ReviewDecision, user: dict = Depends(require_admin)):
    res = supabase.table("ft_loans").select("*").eq("id", loan_id).execute()
    if not res.data:
        raise HTTPException(404, "Loan not found")
    loan = res.data[0]
    supabase.table("ft_loans").update({
        "status": "REJECTED", "reviewed_by": user["user_id"], "review_note": body.note
    }).eq("id", loan_id).execute()
    supabase.table("ft_notifications").insert({
        "user_id": loan["user_id"], "type": "LOAN",
        "title": "Loan Rejected ❌",
        "body": f"Your loan application was rejected. Reason: {body.note or 'No reason given.'}",
        "entity_type": "loan", "entity_id": loan_id, "priority": "HIGH",
    }).execute()
    add_audit_to_db(user["user_id"], "LOAN_REJECT", loan_id, "SUCCESS")
    return {"status": "REJECTED", "loan_id": loan_id}


# ===========================================================================
# KYC
# ===========================================================================

@app.get("/kyc", tags=["KYC"])
def list_kyc(user: dict = Depends(get_current_user)):
    uid = None if user["role"] == UserRole.ADMIN else user["customer_id"]
    q = supabase.table("ft_kyc_documents").select("*").order("submitted_at", desc=True)
    if uid:
        q = q.eq("user_id", uid)
    return q.execute().data or []


@app.post("/kyc/submit", tags=["KYC"], status_code=201)
def submit_kyc(document_type: str, file_name: str, user: dict = Depends(get_current_user)):
    row = {
        "id": f"kyc_{uuid4().hex[:8]}",
        "user_id": user["customer_id"],
        "document_type": document_type,
        "file_name": file_name,
        "status": "PENDING",
    }
    try:
        supabase.table("ft_kyc_documents").insert(row).execute()
        add_audit_to_db(user["user_id"], "KYC_SUBMIT", row["id"], "SUCCESS")
        return row
    except Exception as e:
        raise HTTPException(422, str(e))


@app.post("/admin/kyc/{kyc_id}/approve", tags=["Admin"])
def approve_kyc(kyc_id: str, body: ReviewDecision, user: dict = Depends(require_admin)):
    res = supabase.table("ft_kyc_documents").select("*").eq("id", kyc_id).execute()
    if not res.data:
        raise HTTPException(404, "KYC doc not found")
    doc = res.data[0]
    supabase.table("ft_kyc_documents").update({
        "status": "APPROVED", "reviewed_by": user["user_id"],
        "review_note": body.note, "reviewed_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", kyc_id).execute()
    supabase.table("ft_users").update({"kyc_status": "VERIFIED"}).eq("id", doc["user_id"]).execute()
    supabase.table("ft_notifications").insert({
        "user_id": doc["user_id"], "type": "KYC",
        "title": "KYC Approved ✅",
        "body": "Your identity document has been verified successfully.",
        "entity_type": "kyc", "entity_id": kyc_id, "priority": "HIGH",
    }).execute()
    add_audit_to_db(user["user_id"], "KYC_APPROVE", kyc_id, "SUCCESS")
    return {"status": "APPROVED"}


@app.post("/admin/kyc/{kyc_id}/reject", tags=["Admin"])
def reject_kyc(kyc_id: str, body: ReviewDecision, user: dict = Depends(require_admin)):
    res = supabase.table("ft_kyc_documents").select("*").eq("id", kyc_id).execute()
    if not res.data:
        raise HTTPException(404, "KYC doc not found")
    doc = res.data[0]
    supabase.table("ft_kyc_documents").update({
        "status": "REJECTED", "reviewed_by": user["user_id"],
        "review_note": body.note, "reviewed_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", kyc_id).execute()
    supabase.table("ft_users").update({"kyc_status": "REJECTED"}).eq("id", doc["user_id"]).execute()
    supabase.table("ft_notifications").insert({
        "user_id": doc["user_id"], "type": "KYC",
        "title": "KYC Rejected ❌",
        "body": f"Your identity document was rejected. Reason: {body.note or 'Please resubmit.'}",
        "entity_type": "kyc", "entity_id": kyc_id, "priority": "CRITICAL",
    }).execute()
    add_audit_to_db(user["user_id"], "KYC_REJECT", kyc_id, "SUCCESS")
    return {"status": "REJECTED"}


# ===========================================================================
# CARDS
# ===========================================================================

@app.get("/cards", tags=["Cards"])
def list_cards(user: dict = Depends(get_current_user)):
    uid = None if user["role"] == UserRole.ADMIN else user["customer_id"]
    q = supabase.table("ft_cards").select("*").order("created_at", desc=True)
    if uid:
        q = q.eq("user_id", uid)
    return q.execute().data or []


@app.post("/cards", tags=["Cards"], status_code=201)
def request_card(body: CardRequestBody, user: dict = Depends(get_current_user)):
    acc = get_account_from_db(body.account_id)
    if not acc:
        raise HTTPException(404, "Account not found")
    if user["role"] == UserRole.CUSTOMER and acc["user_id"] != user["customer_id"]:
        raise HTTPException(403, "Access denied")
    u_res = supabase.table("ft_users").select("name").eq("id", user["customer_id"]).execute()
    holder = u_res.data[0]["name"].upper() if u_res.data else "CARDHOLDER"
    import random
    pan = "4" + "".join([str(random.randint(0,9)) for _ in range(15)])
    masked = pan[:4] + " **** **** " + pan[-4:]
    now = datetime.now()
    card_id = f"card_{uuid4().hex[:8]}"
    row = {
        "id": card_id, "account_id": body.account_id, "user_id": user["customer_id"],
        "card_type": body.card_type, "card_number": pan, "masked_number": masked,
        "cardholder_name": holder, "expiry_month": now.month,
        "expiry_year": now.year + 3, "cvv_hash": hashlib.md5(str(uuid4()).encode()).hexdigest(),
        "network": body.network, "status": "ACTIVE",
    }
    try:
        supabase.table("ft_cards").insert(row).execute()
        add_audit_to_db(user["user_id"], "CARD_ISSUED", card_id, "SUCCESS")
        return row
    except Exception as e:
        raise HTTPException(422, str(e))


@app.patch("/cards/{card_id}/block", tags=["Cards"])
def block_card(card_id: str, user: dict = Depends(get_current_user)):
    supabase.table("ft_cards").update({"status": "BLOCKED"}).eq("id", card_id).execute()
    add_audit_to_db(user["user_id"], "CARD_BLOCK", card_id, "SUCCESS")
    return {"status": "BLOCKED"}


# ===========================================================================
# BENEFICIARIES
# ===========================================================================

@app.get("/beneficiaries", tags=["Beneficiaries"])
def list_beneficiaries(user: dict = Depends(get_current_user)):
    uid = None if user["role"] == UserRole.ADMIN else user["customer_id"]
    q = supabase.table("ft_beneficiaries").select("*")
    if uid:
        q = q.eq("user_id", uid)
    return q.execute().data or []


@app.post("/beneficiaries", tags=["Beneficiaries"], status_code=201)
def add_beneficiary(body: BeneficiaryBody, user: dict = Depends(get_current_user)):
    row = {
        "id": f"bene_{uuid4().hex[:8]}", "user_id": user["customer_id"],
        "name": body.name, "bank_name": body.bank_name,
        "account_number": body.account_number, "iban": body.iban,
        "currency": body.currency, "nickname": body.nickname,
    }
    try:
        supabase.table("ft_beneficiaries").insert(row).execute()
        return row
    except Exception as e:
        raise HTTPException(422, str(e))


@app.delete("/beneficiaries/{bene_id}", tags=["Beneficiaries"])
def delete_beneficiary(bene_id: str, user: dict = Depends(get_current_user)):
    supabase.table("ft_beneficiaries").delete().eq("id", bene_id).eq("user_id", user["customer_id"]).execute()
    return {"deleted": bene_id}


# ===========================================================================
# NOTIFICATIONS
# ===========================================================================

@app.get("/notifications", tags=["Notifications"])
def list_notifications(user: dict = Depends(get_current_user)):
    return (supabase.table("ft_notifications").select("*")
            .eq("user_id", user["customer_id"])
            .order("created_at", desc=True).limit(50)
            .execute().data or [])


@app.patch("/notifications/{notif_id}/read", tags=["Notifications"])
def mark_read(notif_id: str, user: dict = Depends(get_current_user)):
    supabase.table("ft_notifications").update({"is_read": True}).eq("id", notif_id).execute()
    return {"read": True}


@app.patch("/notifications/read-all", tags=["Notifications"])
def mark_all_read(user: dict = Depends(get_current_user)):
    supabase.table("ft_notifications").update({"is_read": True}).eq("user_id", user["customer_id"]).execute()
    return {"read_all": True}


@app.post("/admin/notifications/broadcast", tags=["Admin"], status_code=201)
def broadcast_notification(title: str, body: str, user: dict = Depends(require_admin)):
    """Admin: send a notification to every customer."""
    users = supabase.table("ft_users").select("id").eq("role", "customer").execute().data or []
    rows = [{"user_id": u["id"], "type": "SYSTEM", "title": title, "body": body, "priority": "NORMAL"} for u in users]
    if rows:
        supabase.table("ft_notifications").insert(rows).execute()
    add_audit_to_db(user["user_id"], "BROADCAST_NOTIFICATION", f"sent to {len(rows)} users", "SUCCESS")
    return {"sent_count": len(rows)}


# ===========================================================================
# EXCHANGE RATES
# ===========================================================================

@app.get("/rates", tags=["Exchange Rates"])
def exchange_rates():
    return supabase.table("ft_exchange_rates").select("*").eq("is_active", True).execute().data or []


# ===========================================================================
# SUPPORT TICKETS
# ===========================================================================

@app.get("/support/tickets", tags=["Support"])
def list_tickets(user: dict = Depends(get_current_user)):
    uid = None if user["role"] == UserRole.ADMIN else user["customer_id"]
    q = supabase.table("ft_support_tickets").select("*").order("created_at", desc=True)
    if uid:
        q = q.eq("user_id", uid)
    return q.execute().data or []


@app.post("/support/tickets", tags=["Support"], status_code=201)
def create_ticket(body: SupportTicketBody, user: dict = Depends(get_current_user)):
    row = {
        "id": f"ticket_{uuid4().hex[:8]}", "user_id": user["customer_id"],
        "category": body.category, "subject": body.subject,
        "description": body.description, "priority": body.priority,
        "related_account_id": body.related_account_id, "status": "OPEN",
    }
    try:
        supabase.table("ft_support_tickets").insert(row).execute()
        return row
    except Exception as e:
        raise HTTPException(422, str(e))


@app.patch("/admin/support/tickets/{ticket_id}/resolve", tags=["Admin"])
def resolve_ticket(ticket_id: str, resolution_note: str, user: dict = Depends(require_admin)):
    supabase.table("ft_support_tickets").update({
        "status": "RESOLVED", "assigned_to": user["user_id"],
        "resolution_note": resolution_note,
        "resolved_at": datetime.now(timezone.utc).isoformat()
    }).eq("id", ticket_id).execute()
    add_audit_to_db(user["user_id"], "TICKET_RESOLVE", ticket_id, "SUCCESS")
    return {"status": "RESOLVED"}


# ===========================================================================
# ADMIN DASHBOARD SUMMARY
# ===========================================================================

@app.get("/admin/dashboard", tags=["Admin"])
def admin_dashboard(user: dict = Depends(require_admin)):
    """Single endpoint returning key stats for the admin dashboard."""
    try:
        users   = supabase.table("ft_users").select("id,role,status,kyc_status").execute().data or []
        accs    = supabase.table("ft_accounts").select("id,balance,status").execute().data or []
        pending = supabase.table("ft_transaction_requests").select("id,amount").eq("status","PENDING").execute().data or []
        loans   = supabase.table("ft_loans").select("id,status,principal_amount").execute().data or []
        tickets = supabase.table("ft_support_tickets").select("id,status,priority").eq("status","OPEN").execute().data or []
        kyc_q   = supabase.table("ft_kyc_documents").select("id,status").eq("status","PENDING").execute().data or []
        total_bal = sum(float(a["balance"]) for a in accs)
        return {
            "total_users":    len(users),
            "active_accounts": len([a for a in accs if a["status"]=="ACTIVE"]),
            "total_balance":  round(total_bal, 2),
            "pending_approvals": len(pending),
            "pending_amount": round(sum(float(p["amount"]) for p in pending), 2),
            "active_loans":   len([l for l in loans if l["status"]=="ACTIVE"]),
            "open_tickets":   len(tickets),
            "pending_kyc":    len(kyc_q),
            "customers":      len([u for u in users if u["role"]=="customer"]),
            "verified_kyc":   len([u for u in users if u["kyc_status"]=="VERIFIED"]),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ===========================================================================
# PASSWORD RECOVERY VIA SECURITY QUESTIONS
# ===========================================================================

class SecurityAnswerSetup(BaseModel):
    question_id: int = Field(..., gt=0)
    answer: str = Field(..., min_length=1)

class SecurityAnswersSetupRequest(BaseModel):
    answers: List[SecurityAnswerSetup]

class PasswordRecoverRequest(BaseModel):
    email: EmailStr
    question_id: int
    answer: str
    new_password: str = Field(..., min_length=6)

@app.post("/auth/security-questions", tags=["Auth"], status_code=201)
def setup_security_questions(body: SecurityAnswersSetupRequest, user: dict = Depends(get_current_user)):
    """User sets or updates their security questions."""
    rows = []
    for a in body.answers:
        ans_hash = hashlib.sha256(a.answer.strip().lower().encode()).hexdigest()
        rows.append({
            "user_id": user["user_id"],
            "question_id": a.question_id,
            "answer_hash": ans_hash
        })
    try:
        # Delete existing ones to allow updates
        supabase.table("ft_security_answers").delete().eq("user_id", user["user_id"]).execute()
        if rows:
            supabase.table("ft_security_answers").insert(rows).execute()
        add_audit_to_db(user["user_id"], "SET_SECURITY_QUESTIONS", f"Set {len(rows)} questions", "SUCCESS")
        return {"status": "SUCCESS"}
    except Exception as e:
        raise HTTPException(422, str(e))

@app.get("/auth/security-questions/challenge", tags=["Auth"])
def get_security_challenge(email: str):
    """Get the list of question IDs a user has set up for recovery."""
    user_res = supabase.table("ft_users").select("id").eq("email", email).execute()
    if not user_res.data:
        raise HTTPException(404, "User not found")
    user_id = user_res.data[0]["id"]
    ans_res = supabase.table("ft_security_answers").select("question_id").eq("user_id", user_id).execute()
    q_ids = [row["question_id"] for row in ans_res.data] if ans_res.data else []
    if not q_ids:
        raise HTTPException(404, "No security questions set for this user")
    return {"question_ids": q_ids}

@app.post("/auth/recover-password", tags=["Auth"])
def recover_password(body: PasswordRecoverRequest, request: Request):
    """Recover password using a security question answer."""
    user_res = supabase.table("ft_users").select("id").eq("email", body.email).execute()
    if not user_res.data:
        raise HTTPException(404, "User not found")
    user_id = user_res.data[0]["id"]
    
    ans_res = supabase.table("ft_security_answers").select("answer_hash").eq("user_id", user_id).eq("question_id", body.question_id).execute()
    if not ans_res.data:
        raise HTTPException(401, "Security question not found or not set")
    
    stored_hash = ans_res.data[0]["answer_hash"]
    given_hash = hashlib.sha256(body.answer.strip().lower().encode()).hexdigest()
    
    if not hmac.compare_digest(stored_hash, given_hash):
        add_audit_to_db(user_id, "RECOVER_PASSWORD", "Invalid security answer", "FAILURE", request.client.host if request.client else None)
        raise HTTPException(401, "Incorrect answer")
    
    try:
        supabase.table("ft_users").update({"password": body.new_password}).eq("id", user_id).execute()
        add_audit_to_db(user_id, "RECOVER_PASSWORD", "Successfully recovered via security question", "SUCCESS", request.client.host if request.client else None)
        return {"status": "SUCCESS", "message": "Password updated successfully"}
    except Exception as e:
        raise HTTPException(422, str(e))
