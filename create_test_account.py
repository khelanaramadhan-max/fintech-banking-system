#!/usr/bin/env python3
"""
Fintech — Test Account Seeder
Creates demo users and accounts via the API for development and demo purposes.

Usage:
    python create_test_account.py
    python create_test_account.py --url http://localhost:8000 --verbose
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

BASE_URL = "http://localhost:8000"
VERBOSE = False

# ── ANSI colors ──────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def log(msg: str, color: str = RESET):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"{color}[{ts}] {msg}{RESET}")

def ok(msg):  log(f"✓  {msg}", GREEN)
def err(msg): log(f"✗  {msg}", RED); sys.exit(1)
def info(msg): log(f"→  {msg}", BLUE)
def warn(msg): log(f"⚠  {msg}", YELLOW)

# ── HTTP helpers ──────────────────────────────────────────────────────────────
def post(path: str, body: dict, token: str = None) -> dict:
    url = BASE_URL + path
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if VERBOSE:
                info(f"POST {path} → {resp.status}")
            return result
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        warn(f"POST {path} → {e.code}: {body.get('detail', body)}")
        return {"error": body}
    except urllib.error.URLError as e:
        err(f"Cannot connect to {BASE_URL} — is the server running? ({e.reason})")

def get(path: str, token: str) -> dict:
    url = BASE_URL + path
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())

# ── Seed data ─────────────────────────────────────────────────────────────────
DEMO_USERS = [
    {
        "full_name": "Ahmet Yılmaz",
        "email": "ahmet@demo.fintech",
        "phone": "+90 532 111 00 01",
        "national_id": "12345678901",
        "password": "Demo1234!",
        "opening_balance": 15000.00,
    },
    {
        "full_name": "Zeynep Kaya",
        "email": "zeynep@demo.fintech",
        "phone": "+90 532 111 00 02",
        "national_id": "98765432109",
        "password": "Demo1234!",
        "opening_balance": 42500.50,
    },
    {
        "full_name": "Mehmet Demir",
        "email": "mehmet@demo.fintech",
        "phone": "+90 532 111 00 03",
        "national_id": "11111111110",
        "password": "Demo1234!",
        "opening_balance": 7800.00,
    },
]

def check_server():
    """Verify API is reachable."""
    try:
        req = urllib.request.Request(BASE_URL + "/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            ok(f"API reachable — {data.get('status', 'ok')}")
    except Exception as e:
        err(f"API not reachable at {BASE_URL}: {e}\nRun: uvicorn main:app --reload")

def seed_user(user_data: dict) -> tuple[str, str]:
    """Register a user and return (token, customer_id). Skips if email exists."""
    info(f"Seeding user: {user_data['full_name']} ({user_data['email']})")

    result = post("/auth/register", {
        "full_name": user_data["full_name"],
        "email": user_data["email"],
        "phone": user_data["phone"],
        "national_id": user_data["national_id"],
        "password": user_data["password"],
    })

    if "error" in result:
        # Try login if already exists
        warn(f"  Already registered — attempting login...")
        result = post("/auth/login", {
            "email": user_data["email"],
            "password": user_data["password"],
        })
        if "error" in result:
            warn(f"  Could not login {user_data['email']} — skipping")
            return None, None

    token = result.get("token")
    customer_id = result.get("customer_id")
    ok(f"  Registered — customer_id: {customer_id}")
    return token, customer_id

def seed_account(token: str, customer_id: str, balance: float) -> str:
    """Open a bank account with opening balance."""
    result = post("/accounts", {
        "customer_id": customer_id,
        "opening_balance": balance,
    }, token=token)

    if "error" in result:
        warn(f"  Could not open account: {result['error']}")
        return None

    acc_id = result.get("account_id")
    acc_num = result.get("account_number")
    ok(f"  Account opened: {acc_num} — Balance: ₺{balance:,.2f}")
    return acc_id

def print_summary(created: list):
    print(f"\n{BOLD}{'─'*60}{RESET}")
    print(f"{BOLD}{GREEN}  ✓ Seeding complete — {len(created)} accounts created{RESET}")
    print(f"{BOLD}{'─'*60}{RESET}")
    for entry in created:
        print(f"  {BLUE}User:{RESET}    {entry['name']} ({entry['email']})")
        print(f"  {BLUE}Password:{RESET} Demo1234!")
        print(f"  {BLUE}Account:{RESET}  {entry['account']}")
        print(f"  {BLUE}Balance:{RESET}  ₺{entry['balance']:,.2f}")
        print()
    print(f"  {BLUE}Admin:{RESET}    admin@fintech.io / Admin123!")
    print(f"  {BLUE}Swagger:{RESET}  {BASE_URL}/docs")
    print(f"{BOLD}{'─'*60}{RESET}\n")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    global BASE_URL, VERBOSE

    parser = argparse.ArgumentParser(description="Fintech test account seeder")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--verbose", action="store_true", help="Verbose HTTP output")
    args = parser.parse_args()

    BASE_URL = args.url.rstrip("/")
    VERBOSE = args.verbose

    print(f"\n{BOLD}{BLUE}  Fintech — Test Account Seeder{RESET}")
    print(f"  Target: {BASE_URL}\n")

    check_server()
    time.sleep(0.3)

    created = []
    for user in DEMO_USERS:
        token, customer_id = seed_user(user)
        if not token:
            continue
        acc_id = seed_account(token, customer_id, user["opening_balance"])
        if acc_id:
            # Fetch account number
            try:
                accounts = get("/accounts", token)
                acc_num = accounts[0].get("account_number", acc_id) if accounts else acc_id
            except Exception:
                acc_num = acc_id
            created.append({
                "name": user["full_name"],
                "email": user["email"],
                "account": acc_num,
                "balance": user["opening_balance"],
            })
        time.sleep(0.1)

    print_summary(created)

if __name__ == "__main__":
    main()
