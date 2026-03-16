#!/usr/bin/env python3
"""
Fintech — Frontend Sync Trigger
Watches frontend/fintech.html for changes and syncs to:
  1. Docker volume (running container)
  2. Render.com deployment (via curl deploy hook)
  3. GitHub Pages / Cloudflare Pages (via git push)

Usage:
    python trigger_sync.py                 # Watch mode
    python trigger_sync.py --once          # Sync once and exit
    python trigger_sync.py --target docker # Only sync to Docker
"""

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
WATCH_FILE  = Path("frontend/fintech.html")
DOCKER_DEST = Path("frontend")          # Nginx volume source
OUTPUTS_DIR = Path(".")
POLL_INTERVAL = 1.5                     # seconds between checks
RENDER_DEPLOY_HOOK = os.environ.get("RENDER_DEPLOY_HOOK", "")

# ── ANSI ──────────────────────────────────────────────────────────────────────
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; X = "\033[0m"; BOLD = "\033[1m"

def ts():   return datetime.now().strftime("%H:%M:%S")
def ok(m):  print(f"{G}[{ts()}] ✓  {m}{X}")
def err(m): print(f"{R}[{ts()}] ✗  {m}{X}")
def info(m):print(f"{B}[{ts()}] →  {m}{X}")
def warn(m):print(f"{Y}[{ts()}] ⚠  {m}{X}")

def file_hash(path: Path) -> str:
    """MD5 hash of file contents."""
    if not path.exists():
        return ""
    return hashlib.md5(path.read_bytes()).hexdigest()

def sync_to_docker(src: Path):
    """Copy changed file into Docker container via docker cp."""
    result = subprocess.run(
        ["docker", "ps", "-q", "--filter", "name=fintech_frontend"],
        capture_output=True, text=True
    )
    cid = result.stdout.strip()
    if not cid:
        warn("Docker container 'fintech_frontend' not running — skipping docker sync")
        return False
    subprocess.run(
        ["docker", "cp", str(src), f"{cid}:/usr/share/nginx/html/{src.name}"],
        check=True, capture_output=True
    )
    ok(f"Synced to Docker container {cid[:12]}")
    return True

def sync_to_render():
    """Trigger Render.com deploy hook."""
    if not RENDER_DEPLOY_HOOK:
        warn("RENDER_DEPLOY_HOOK not set — skipping Render sync")
        return False
    try:
        import urllib.request
        urllib.request.urlopen(RENDER_DEPLOY_HOOK, timeout=5)
        ok("Render deploy hook triggered")
        return True
    except Exception as e:
        err(f"Render deploy hook failed: {e}")
        return False

def sync_to_git(message: str):
    """Git add + commit + push for Cloudflare Pages / GitHub Pages."""
    try:
        subprocess.run(["git", "add", "frontend/"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", message], check=True, capture_output=True)
        subprocess.run(["git", "push"], check=True, capture_output=True)
        ok("Pushed to git — Cloudflare Pages will auto-deploy")
        return True
    except subprocess.CalledProcessError as e:
        warn(f"Git sync skipped: {e.stderr.decode()[:80] if e.stderr else 'nothing to commit'}")
        return False

def do_sync(path: Path, target: str):
    """Run all configured sync targets."""
    info(f"Change detected in {path.name} — syncing...")
    msg = f"chore: auto-sync frontend {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    if target in ("docker", "all"):
        sync_to_docker(path)
    if target in ("render", "all"):
        sync_to_render()
    if target in ("git", "all"):
        sync_to_git(msg)

def watch(path: Path, target: str):
    """Watch a file for changes and sync on modification."""
    if not path.exists():
        err(f"File not found: {path}")
        sys.exit(1)

    print(f"\n{BOLD}{B}  Fintech — Frontend Sync Watcher{X}")
    print(f"  Watching: {path}")
    print(f"  Target:   {target}")
    print(f"  Interval: {POLL_INTERVAL}s")
    print(f"  Press Ctrl+C to stop\n")

    last_hash = file_hash(path)
    last_size = path.stat().st_size
    info(f"Initial: {path.name} ({last_size:,} bytes)")

    try:
        while True:
            time.sleep(POLL_INTERVAL)
            current_hash = file_hash(path)
            if current_hash != last_hash:
                size = path.stat().st_size
                diff = size - last_size
                sign = "+" if diff >= 0 else ""
                info(f"Modified: {path.name} ({size:,} bytes, {sign}{diff:,})")
                do_sync(path, target)
                last_hash = current_hash
                last_size = size
    except KeyboardInterrupt:
        print(f"\n{Y}  Watcher stopped.{X}\n")

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Fintech frontend sync trigger")
    parser.add_argument("--file", default=str(WATCH_FILE), help="File to watch")
    parser.add_argument("--target", default="docker", choices=["docker", "git", "render", "all"],
                        help="Sync target (default: docker)")
    parser.add_argument("--once", action="store_true", help="Sync once and exit")
    args = parser.parse_args()

    path = Path(args.file)
    if args.once:
        if not path.exists():
            err(f"File not found: {path}")
            sys.exit(1)
        do_sync(path, args.target)
    else:
        watch(path, args.target)

if __name__ == "__main__":
    main()
