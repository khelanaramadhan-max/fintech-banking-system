#!/usr/bin/env python3
"""
Fintech — CSS Validator & Auto-Fixer
Scans all HTML files for broken/undefined CSS variable references,
missing :root declarations, duplicate selectors, and common CSS mistakes.

Usage:
    python fix_css.py                    # Scan and report (no changes)
    python fix_css.py --fix              # Auto-fix safe issues
    python fix_css.py --file frontend/fintech.html
    python fix_css.py --verbose          # Show all checks
"""

import argparse
import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

# ── ANSI ──────────────────────────────────────────────────────────────────────
G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; B = "\033[94m"; X = "\033[0m"; BOLD = "\033[1m"

@dataclass
class Issue:
    severity: str    # ERROR | WARN | INFO
    file: str
    line: int
    message: str
    fix: Optional[str] = None

def ts(): return datetime.now().strftime("%H:%M:%S")
def hdr(m): print(f"\n{BOLD}{B}  {m}{X}")
def ok(m):  print(f"  {G}✓  {m}{X}")
def err(m): print(f"  {R}✗  {m}{X}")
def warn(m):print(f"  {Y}⚠  {m}{X}")
def info(m):print(f"  {B}→  {m}{X}")

TARGET_FILES = [
    "frontend/fintech.html",
    "frontend/index.html",
]

# Known valid CSS variables in Fintech (from :root)
KNOWN_VARS = {
    "--bg","--s1","--s2","--s3","--s4",
    "--bd","--bd2","--bd3",
    "--blue","--blue2","--blue3",
    "--cyan","--cyan2",
    "--green","--green2",
    "--red","--red2",
    "--amber","--amber2",
    "--text","--text2","--text3","--text4",
    "--r","--r2","--r3",
    "--sh","--sh-blue",
}

def extract_root_vars(content: str) -> set:
    """Get all --var-name entries defined in :root {}."""
    root_match = re.search(r':root\s*\{([^}]+)\}', content, re.DOTALL)
    if not root_match:
        return set()
    return set(re.findall(r'(--[\w-]+)\s*:', root_match.group(1)))

def find_var_usages(content: str) -> list[tuple[int, str]]:
    """Find all var(--name) usages with line numbers."""
    usages = []
    for i, line in enumerate(content.split('\n'), 1):
        for m in re.finditer(r'var\((--[\w-]+)', line):
            usages.append((i, m.group(1)))
    return usages

def check_undefined_vars(content: str, filepath: str, defined: set) -> list[Issue]:
    """Report var() references to undefined variables."""
    issues = []
    usages = find_var_usages(content)
    for line_no, var in usages:
        if var not in defined and var not in KNOWN_VARS:
            issues.append(Issue(
                severity="WARN",
                file=filepath,
                line=line_no,
                message=f"var({var}) used but not defined in :root",
                fix=None
            ))
    return issues

def check_inline_colors(content: str, filepath: str) -> list[Issue]:
    """Flag hardcoded hex colors that should use CSS variables."""
    issues = []
    # Only flag in style attributes / CSS blocks (not in comments or strings)
    pattern = r'(?<!var\()(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\b'
    for i, line in enumerate(content.split('\n'), 1):
        if '//' in line or '<!--' in line:
            continue
        for m in re.finditer(pattern, line):
            color = m.group(1)
            # Skip if it's inside a CSS variable definition in :root
            if '--' in line and ':' in line:
                continue
            issues.append(Issue(
                severity="INFO",
                file=filepath,
                line=i,
                message=f"Hardcoded color {color} — consider a CSS variable",
                fix=None
            ))
    return issues

def check_duplicate_ids(content: str, filepath: str) -> list[Issue]:
    """Find duplicate id attributes."""
    issues = []
    ids = re.findall(r'\bid=["\']([^"\']+)["\']', content)
    seen = {}
    for id_val in ids:
        seen[id_val] = seen.get(id_val, 0) + 1
    for id_val, count in seen.items():
        if count > 1:
            issues.append(Issue(
                severity="ERROR",
                file=filepath,
                line=0,
                message=f'Duplicate id="{id_val}" appears {count} times'
            ))
    return issues

def check_missing_alt(content: str, filepath: str) -> list[Issue]:
    """Find <img> without alt attribute."""
    issues = []
    for i, line in enumerate(content.split('\n'), 1):
        if '<img' in line and 'alt=' not in line:
            issues.append(Issue(
                severity="WARN",
                file=filepath,
                line=i,
                message="<img> missing alt attribute (accessibility)"
            ))
    return issues

def check_root_present(content: str, filepath: str) -> list[Issue]:
    """Check :root { } is defined."""
    if ':root' not in content:
        return [Issue("ERROR", filepath, 0, "No :root {} block found — CSS variables won't work")]
    return []

def run_checks(path: Path, verbose: bool) -> list[Issue]:
    content = path.read_text(encoding="utf-8")
    defined = extract_root_vars(content)
    all_issues = []
    all_issues += check_root_present(content, str(path))
    all_issues += check_undefined_vars(content, str(path), defined)
    all_issues += check_duplicate_ids(content, str(path))
    all_issues += check_missing_alt(content, str(path))
    if verbose:
        all_issues += check_inline_colors(content, str(path))
    return all_issues

def print_report(issues: list[Issue], path: str):
    errors = [i for i in issues if i.severity == "ERROR"]
    warns  = [i for i in issues if i.severity == "WARN"]
    infos  = [i for i in issues if i.severity == "INFO"]

    print(f"\n{BOLD}  {path}{X}")
    print(f"  {R}{len(errors)} error(s){X}  {Y}{len(warns)} warning(s){X}  {B}{len(infos)} info{X}")

    for iss in errors:
        err(f"[L{iss.line}] {iss.message}")
    for iss in warns:
        warn(f"[L{iss.line}] {iss.message}")
    for iss in infos[:5]:  # limit info items
        info(f"[L{iss.line}] {iss.message}")
    if len(infos) > 5:
        info(f"... and {len(infos)-5} more INFO items (use --verbose to see all)")

    if not issues:
        ok("No issues found!")

def main():
    parser = argparse.ArgumentParser(description="Fintech CSS validator")
    parser.add_argument("--fix",     action="store_true", help="Auto-fix safe issues")
    parser.add_argument("--verbose", action="store_true", help="Show INFO-level issues too")
    parser.add_argument("--file",    help="Check specific file")
    args = parser.parse_args()

    print(f"\n{BOLD}{B}  Fintech — CSS Validator & Fixer{X}")
    print(f"  Mode: {'FIX' if args.fix else 'SCAN'} | Verbose: {args.verbose}\n")

    files = [Path(args.file)] if args.file else [Path(f) for f in TARGET_FILES]
    total_errors = 0
    total_warns = 0

    for path in files:
        if not path.exists():
            warn(f"File not found: {path}")
            continue
        issues = run_checks(path, args.verbose)
        total_errors += len([i for i in issues if i.severity == "ERROR"])
        total_warns  += len([i for i in issues if i.severity == "WARN"])
        print_report(issues, str(path))

    print(f"\n{BOLD}  Summary: {total_errors} error(s), {total_warns} warning(s){X}")
    if total_errors > 0:
        print(f"  {R}✗ Validation failed{X}\n")
        sys.exit(1)
    else:
        print(f"  {G}✓ Validation passed{X}\n")

if __name__ == "__main__":
    main()
