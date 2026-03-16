#!/usr/bin/env python3
"""
Fintech — Layout Variable Updater
Batch-updates CSS custom property values across all HTML/CSS files.

Usage:
    python update_layouts.py                    # Preview changes (dry run)
    python update_layouts.py --apply            # Apply changes
    python update_layouts.py --preset dark      # Switch to dark preset
    python update_layouts.py --preset light     # Switch to light preset
    python update_layouts.py --var --bg #04070e # Update one variable
"""

import argparse
import re
import sys
from pathlib import Path
from datetime import datetime

# ── ANSI ──────────────────────────────────────────────────────────────────────
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; X = "\033[0m"; BOLD = "\033[1m"

# ── CSS Variable Presets ──────────────────────────────────────────────────────
PRESETS = {
    "dark": {
        "--bg": "#04070e",
        "--s1": "#080d1a",
        "--s2": "#0b1322",
        "--s3": "#0f1a2e",
        "--s4": "#14223c",
        "--blue": "#2563eb",
        "--blue2": "#3b82f6",
        "--blue3": "#60a5fa",
        "--text": "#e8eeff",
        "--text2": "#7a90b8",
        "--text3": "#3d5275",
        "--text4": "#1e3050",
        "--bd": "rgba(255,255,255,.06)",
        "--bd2": "rgba(255,255,255,.11)",
    },
    "light": {
        "--bg": "#f8faff",
        "--s1": "#ffffff",
        "--s2": "#f0f4ff",
        "--s3": "#e8eeff",
        "--s4": "#dce6ff",
        "--blue": "#1d4ed8",
        "--blue2": "#2563eb",
        "--blue3": "#3b82f6",
        "--text": "#0f172a",
        "--text2": "#475569",
        "--text3": "#94a3b8",
        "--text4": "#cbd5e1",
        "--bd": "rgba(0,0,0,.08)",
        "--bd2": "rgba(0,0,0,.14)",
    },
    "midnight": {
        "--bg": "#000000",
        "--s1": "#0a0a0f",
        "--s2": "#0f0f1a",
        "--s3": "#151525",
        "--s4": "#1c1c35",
        "--blue": "#6366f1",
        "--blue2": "#818cf8",
        "--blue3": "#a5b4fc",
        "--text": "#f0f0ff",
        "--text2": "#8080aa",
        "--text3": "#404070",
        "--text4": "#1a1a40",
        "--bd": "rgba(255,255,255,.04)",
        "--bd2": "rgba(255,255,255,.08)",
    },
}

TARGET_FILES = [
    "frontend/fintech.html",
    "frontend/index.html",
]

def ts(): return datetime.now().strftime("%H:%M:%S")
def ok(m):  print(f"{G}[{ts()}] ✓  {m}{X}")
def info(m):print(f"{B}[{ts()}] →  {m}{X}")
def warn(m):print(f"{Y}[{ts()}] ⚠  {m}{X}")
def preview(m): print(f"  {Y}~  {m}{X}")

def parse_existing_vars(content: str) -> dict:
    """Extract existing :root CSS variables from file."""
    pattern = r'(--[\w-]+)\s*:\s*([^;]+);'
    return {m.group(1): m.group(2).strip() for m in re.finditer(pattern, content)}

def apply_vars(content: str, updates: dict) -> tuple[str, list]:
    """Replace CSS variable values. Returns (new_content, list_of_changes)."""
    changes = []
    for var, new_val in updates.items():
        pattern = rf'({re.escape(var)}\s*:\s*)([^;]+)(;)'
        def replacer(m, v=new_val, vn=var):
            old = m.group(2).strip()
            if old != v:
                changes.append((vn, old, v))
                return m.group(1) + v + m.group(3)
            return m.group(0)
        content = re.sub(pattern, replacer, content)
    return content, changes

def process_file(path: Path, updates: dict, dry_run: bool) -> int:
    """Process one file. Returns number of changes made."""
    if not path.exists():
        warn(f"File not found: {path} — skipping")
        return 0

    content = path.read_text(encoding="utf-8")
    new_content, changes = apply_vars(content, updates)

    if not changes:
        info(f"{path} — no changes needed")
        return 0

    print(f"\n{BOLD}  {path}{X}")
    for var, old, new in changes:
        preview(f"{var}: {old}  →  {new}")

    if not dry_run:
        # Backup
        backup = path.with_suffix(path.suffix + ".bak")
        backup.write_bytes(path.read_bytes())
        # Write
        path.write_text(new_content, encoding="utf-8")
        ok(f"Updated {path} ({len(changes)} changes) — backup: {backup.name}")
    else:
        warn(f"DRY RUN — {len(changes)} changes would be made (use --apply to write)")

    return len(changes)

def main():
    parser = argparse.ArgumentParser(description="Fintech CSS layout updater")
    parser.add_argument("--apply",  action="store_true", help="Apply changes (default: dry run)")
    parser.add_argument("--preset", choices=list(PRESETS.keys()), help="Apply a color preset")
    parser.add_argument("--var",    nargs=2, metavar=("VARNAME", "VALUE"), help="Update single variable")
    parser.add_argument("--file",   help="Target specific file instead of all")
    args = parser.parse_args()

    print(f"\n{BOLD}{B}  Fintech — Layout Variable Updater{X}")
    print(f"  Mode: {'APPLY' if args.apply else 'DRY RUN'}\n")

    updates = {}
    if args.preset:
        updates = PRESETS[args.preset]
        info(f"Using preset: {args.preset} ({len(updates)} variables)")
    elif args.var:
        updates = {args.var[0]: args.var[1]}
        info(f"Single update: {args.var[0]} = {args.var[1]}")
    else:
        print(f"  Usage examples:")
        print(f"    python update_layouts.py --preset dark --apply")
        print(f"    python update_layouts.py --preset light")
        print(f"    python update_layouts.py --var --bg #000000 --apply")
        print()
        # Default: show current vars
        for fp in TARGET_FILES:
            p = Path(fp)
            if p.exists():
                vars_ = parse_existing_vars(p.read_text(encoding="utf-8"))
                print(f"  {BOLD}{p}{X}")
                for k, v in list(vars_.items())[:12]:
                    print(f"    {B}{k}{X}: {v}")
                print(f"    ... ({len(vars_)} total variables)")
        return

    files = [Path(args.file)] if args.file else [Path(f) for f in TARGET_FILES]
    total = 0
    for f in files:
        total += process_file(f, updates, dry_run=not args.apply)

    print(f"\n{BOLD}  Total: {total} change(s) {'applied' if args.apply else 'found (dry run)'}{X}\n")

if __name__ == "__main__":
    main()
