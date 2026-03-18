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
