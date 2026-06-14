#!/usr/bin/env python3
"""Deterministic regex pre-pass for skill-publisher's Step-4 security check.

security-checks.md lists 14 categories. Several are pure pattern-matches a script
can find reliably every ship; the rest need adversarial human/model reading. This
script runs the GREP-ABLE subset across a skill's files and emits SEC* candidate
findings, so the orchestrator's security pass starts from a deterministic baseline
instead of re-improvising the regexes each time. It does NOT replace the judgment
categories — it's a first pass that catches the mechanical ones loudly.

Scripted here (deterministic — categories from security-checks.md):
  cat 1  hardcoded credentials/tokens/keys     SEC-CRED
  cat 3  unsafe deserialization                SEC-DESER
  cat 7  insecure cryptographic choices        SEC-CRYPTO
  cat 8  path traversal (unguarded Path(input)) SEC-PATH    (heuristic — verify)  # security-scan: ignore-line
  cat 13 default-on telemetry/external report  SEC-TELEMETRY (heuristic — verify)
  cat 14 deprecated security APIs              SEC-DEPRECATED

Left to the orchestrator's prose pass (judgment — NOT scripted):
  cat 2 injection · 4 weak authz · 5 sensitive-data-in-logs · 6 broken access
  control · 9 SSRF · 10 TOCTOU · 11 timing/error-message leak · 12 cross-agent trust.
These need to know what's user-supplied / sensitive / privileged — semantic, not regex.

Pure-stdlib. Scans .py / .md / .sh / .js / .ts / .json / .yaml / .yml (+ no-extension executables) under
the skill, skipping .bak*, hidden files, and eval/workspace dirs.

Usage:  security_scan.py <skill-path>
Output JSON: {"findings":[{flag,category,file,line,match,note}], "scanned_files":N, "judgment_categories_not_scanned":[...]}
Exit: 0 no scripted findings; 1 finding(s) present (review + address per ship-checklist); 2 usage.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# (compiled_regex, flag, category, note). Patterns are deliberately specific to
# limit false positives; SEC-PATH and SEC-TELEMETRY are flagged as heuristic.
CHECKS = [
    # cat 1 — hardcoded credentials/tokens (specific high-confidence shapes)
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "SEC-CRED", "1 hardcoded-credential", "AWS access key id"),  # security-scan: ignore-line
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "SEC-CRED", "1 hardcoded-credential", "GitHub personal token"),  # security-scan: ignore-line
    (re.compile(r"\bgh[ours]_[A-Za-z0-9]{36}\b"), "SEC-CRED", "1 hardcoded-credential", "GitHub token"),  # security-scan: ignore-line
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "SEC-CRED", "1 hardcoded-credential", "OpenAI-style secret key"),  # security-scan: ignore-line
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"), "SEC-CRED", "1 hardcoded-credential", "Slack token"),  # security-scan: ignore-line
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "SEC-CRED", "1 hardcoded-credential", "private key block"),  # security-scan: ignore-line
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"), "SEC-CRED", "1 hardcoded-credential", "JWT"),  # security-scan: ignore-line
    (re.compile(r"""(?i)\b(?:password|passwd|secret|api[_-]?key|token)\s*[:=]\s*['"][^'"\s]{6,}['"]"""), "SEC-CRED", "1 hardcoded-credential", "assigned secret literal"),  # security-scan: ignore-line
    # cat 3 — unsafe deserialization
    (re.compile(r"\bpickle\.loads?\b"), "SEC-DESER", "3 unsafe-deserialization", "pickle load"),  # security-scan: ignore-line
    # Negative-lookahead matches literal `Loader=yaml.SafeLoader` only; bare-import
    # `yaml.load(x, Loader=SafeLoader)` is falsely flagged (safe but no yaml. prefix).  # security-scan: ignore-line
    # `yaml.load(x, Loader=yaml.FullLoader)` is correctly flagged (unsafe, no match).  # security-scan: ignore-line
    # Confirm each hit: "use yaml.safe_load" is the correct fix for most cases.
    (re.compile(r"\byaml\.load\s*\((?![^)]*Loader\s*=\s*yaml\.SafeLoader)"), "SEC-DESER", "3 unsafe-deserialization", "yaml.load without SafeLoader (use yaml.safe_load)"),  # security-scan: ignore-line
    (re.compile(r"(?<![A-Za-z_])\beval\s*\("), "SEC-DESER", "3 unsafe-deserialization", "eval()"),  # security-scan: ignore-line
    (re.compile(r"(?<![A-Za-z_])\bexec\s*\("), "SEC-DESER", "3 unsafe-deserialization", "exec()"),  # security-scan: ignore-line
    # cat 7 — insecure crypto
    (re.compile(r"\bhashlib\.(?:md5|sha1)\b"), "SEC-CRYPTO", "7 insecure-crypto", "MD5/SHA1 (weak if security-purpose)"),  # security-scan: ignore-line
    (re.compile(r"\bDES\b|\b3DES\b|\bMODE_ECB\b"), "SEC-CRYPTO", "7 insecure-crypto", "DES/3DES/ECB"),  # security-scan: ignore-line
    (re.compile(r"(?<![A-Za-z_.])\brandom\.(?:random|randint|choice|getrandbits)\b"), "SEC-CRYPTO", "7 insecure-crypto", "random for security token? (use secrets) — verify purpose"),  # security-scan: ignore-line
    # cat 8 — path traversal (heuristic)
    (re.compile(r"\bPath\(\s*[a-z_]*(?:input|arg|param|user|request|payload)[a-z_]*\s*\)"), "SEC-PATH", "8 path-traversal", "Path() from input-looking var — verify it's base-restricted"),  # security-scan: ignore-line
    # cat 14 — deprecated security APIs
    (re.compile(r"\bcgi\.escape\b"), "SEC-DEPRECATED", "14 deprecated-security-api", "cgi.escape (use html.escape)"),  # security-scan: ignore-line
    (re.compile(r"\bcrypto\.createCipher\b(?!iv)"), "SEC-DEPRECATED", "14 deprecated-security-api", "Node crypto.createCipher (use createCipheriv)"),  # security-scan: ignore-line
    # cat 13 — default-on telemetry / external reporting (heuristic)
    (re.compile(r"(?i)\b(?:requests|urllib|httpx|fetch|axios)\b.*(?:telemetry|analytics|track|report|metrics|beacon)"), "SEC-TELEMETRY", "13 default-on-telemetry", "outbound call to telemetry/analytics endpoint — verify opt-in"),  # security-scan: ignore-line
]

JUDGMENT_CATEGORIES = [
    "2 injection-vector", "4 weak-authn/authz", "5 sensitive-data-in-logs",
    "6 broken-access-control", "9 SSRF", "10 TOCTOU",
    "11 timing/error-message-leak", "12 cross-agent-trust",
]

SCAN_EXTS = {".py", ".md", ".sh", ".js", ".ts", ".json", ".yaml", ".yml"}
SKIP_NAME = re.compile(r"\.bak|^\.")
SKIP_PATH = ("/evals/iteration-", "-workspace/", "/__pycache__/")


def scan_file(path: Path, rel: str, prose: bool):
    """Return (findings, prose_matches, error_str_or_None). The third element is None
    on success or an OSError string if the file could not be read (surfaced to the
    caller so it is not silently counted as a clean scan). For prose files (.md) a hit is almost
    always documentation (a reference explaining `pickle.loads` is not a vuln), so  # security-scan: ignore-line
    matches there go to a separate 'prose_matches' bucket — surfaced for awareness
    but NOT counted as findings or failing the exit code. Executable files
    (.py/.sh/.js/.ts + executables) produce real findings."""
    findings, prose_matches = [], []
    try:
        text = path.read_text(errors="replace")
    except OSError as e:
        # Signal unreadability to the caller so it is surfaced, not silently
        # counted as a clean scan (the file was already tallied in `scanned`).
        return findings, prose_matches, str(e)
    for i, line in enumerate(text.splitlines(), start=1):
        # Honor an explicit per-line opt-out (e.g. this scanner's own pattern
        # definitions, or a reviewed false positive): a line containing the marker
        # `security-scan: ignore-line` is skipped. Keeps a pattern-defining file
        # (like this one) from flagging its own regex literals.
        if "security-scan: ignore-line" in line:
            continue
        # In .md, skip fenced/inline code is overkill; instead route ALL md hits to prose bucket.
        for rx, flag, cat, note in CHECKS:
            m = rx.search(line)
            if m:
                snippet = m.group(0)
                if len(snippet) > 60:
                    snippet = snippet[:57] + "..."
                rec = {"flag": flag, "category": cat, "file": rel, "line": i,
                       "match": snippet, "note": note}
                (prose_matches if prose else findings).append(rec)
    return findings, prose_matches, None


def main() -> int:
    ap = argparse.ArgumentParser(description="Deterministic security regex pre-pass (publisher Step 4)")
    ap.add_argument("skill_path")
    args = ap.parse_args()
    root = Path(args.skill_path).expanduser()
    if not root.is_dir():
        print(f"ERROR: not a directory: {root}", file=sys.stderr)
        return 2

    findings = []
    prose_matches = []
    unreadable = []
    scanned = 0
    try:
        all_paths = sorted(root.rglob("*"))
    except OSError as e:
        print(f"ERROR: could not walk {root}: {e}", file=sys.stderr)
        return 2
    for p in all_paths:
        if not p.is_file():
            continue
        rel = str(p.relative_to(root))
        if SKIP_NAME.search(p.name) or any(s in f"/{rel}" for s in SKIP_PATH):
            continue
        is_exec = p.stat().st_mode & 0o111
        if p.suffix.lower() not in SCAN_EXTS and not (p.suffix == "" and is_exec):
            continue
        scanned += 1
        # .md is prose/documentation; everything else is executable-ish code.
        f, pm, err = scan_file(p, rel, prose=(p.suffix.lower() == ".md"))
        if err is not None:
            unreadable.append({"file": rel, "error": err})
            continue
        findings.extend(f)
        prose_matches.extend(pm)

    result = {
        "skill": str(root),
        "scanned_files": scanned,
        "unreadable_files": unreadable,             # counted in scanned_files but could NOT be read — review manually
        "findings": findings,                       # in CODE files — real candidates
        "prose_matches": prose_matches,             # in .md — almost always documentation; review-only, do NOT fail on these
        "judgment_categories_not_scanned": JUDGMENT_CATEGORIES,
        "note": "findings[] are candidates in executable files — confirm each (some heuristic) and address per ship-checklist.md. "
                "prose_matches[] are pattern hits in .md docs (e.g. a reference explaining `pickle.loads`) — surfaced for awareness, "  # security-scan: ignore-line
                "NOT counted as findings and NOT failing the exit code. The judgment categories still need the orchestrator's "
                "adversarial read; this script does not cover them.",
    }
    print(json.dumps(result, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
