#!/usr/bin/env python3
"""Readiness report for skill-publisher --readiness mode.

Runs all cheap deterministic gates (no cold Agent, no ledger writes) and prints a
human-readable green/yellow/red verdict. See references/readiness-gates.md for the
gate spec and classification rules.

Gates (all tiers unless noted):
  frontmatter     quick_validate.py              RED on failure
  portability     portability_lint.py --tier T   RED if target tier in would_fail_at_tiers
  links           link_check.py                  RED on broken link; YELLOW on dead script
  license         spdx_check.py                  YELLOW if absent/unrecognized
  history         HISTORY.md presence            YELLOW if absent (degraded mode)
  upstream_url    author.history[].source        YELLOW if absent (no PR will open)
  attribution     attribution_lint.py            YELLOW if incomplete  (claude-users+)
  mcp_deps        mcp_deps.py                    YELLOW if undeclared  (claude-users+)

Usage:
    readiness_report.py <skill-path> [--tier personal|claude-users|model-agnostic] [--json]
    --tier: override auto-detected tier from SKILL.md frontmatter
    --json: emit JSON (default: human-readable report)

Exit: 0 = green or yellow; 1 = red (blockers present); 2 = usage/path error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

VALID_TIERS = ("personal", "claude-users", "model-agnostic")
SCRIPTS = Path(__file__).parent

# Frontmatter parsing lives in one place (frontmatter_util) so this gate and
# package_skill cannot drift on BOM/CRLF/trailing-newline edge cases.
sys.path.insert(0, str(SCRIPTS))
from frontmatter_util import block as _fm_block, field as _fm_field
# Description-triggering heuristic lives in triggering_eval (the same module the
# opt-in Step-3 eval uses) so readiness and ship report one confidence signal.
# Pure-Python + no subprocess, so import it in-process rather than spawning it.
from triggering_eval import description_quality as _description_quality


def detect_tier(fm: str) -> str | None:
    """Tier from a pre-extracted SKILL.md frontmatter block (read once by main()
    and shared with _gate_description, rather than re-reading SKILL.md per gate)."""
    return _fm_field(fm, "intended-audience") or _fm_field(fm, "tier")


# ── subprocess helper ─────────────────────────────────────────────────────────

def _run(cmd: list[str]) -> tuple[int, str, str]:
    # encoding="utf-8" pins decoding — text=True alone uses the locale default,
    # which raises UnicodeDecodeError on a non-UTF-8 locale (the sub-gates emit
    # UTF-8 report text). The call is unguarded, so that would crash the report.
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return r.returncode, r.stdout.strip(), r.stderr.strip()


# ── per-gate runners ──────────────────────────────────────────────────────────

def _gate_frontmatter(target: str) -> dict:
    rc, out, err = _run([sys.executable, str(SCRIPTS / "quick_validate.py"), target])
    if rc == 0:
        return {"exit": rc, "cls": "pass", "detail": ""}
    msg = out or err or "frontmatter invalid"
    return {"exit": rc, "cls": "blocker", "detail": msg}


def _gate_portability(target: str, tier: str) -> dict:
    rc, out, err = _run([sys.executable, str(SCRIPTS / "portability_lint.py"), target, "--tier", tier])
    if rc == 0:
        return {"exit": rc, "cls": "pass", "detail": ""}
    if not out:
        return {"exit": rc, "cls": "error", "detail": err or "no output"}
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return {"exit": rc, "cls": "error", "detail": "non-JSON output from portability_lint"}
    if "error" in data:
        return {"exit": rc, "cls": "error", "detail": str(data["error"])}
    would_fail = data.get("would_fail_at_tiers", [])
    if not isinstance(would_fail, list):
        would_fail = []
    if tier in would_fail:
        violations = data.get("tier_violations", [])
        # Split the violations blocking THIS tier into hard blockers vs soft
        # warnings. A `blocks_tier` ending "(warning)" (e.g. a body-level Claude
        # pattern at claude-users — dynamic injection, mcp__* mention) is ALLOWED
        # at this tier: it collapses to a bare tier name in `would_fail_at_tiers`
        # but is a soft warning, not a ship-blocker (tier-transition-checks.md
        # "Interpreting portability_lint.py output"). Only a HARD violation makes
        # this gate RED; if every blocking violation is a (warning), it's YELLOW.
        hard_parts, warn_parts = [], []
        # Classify over ALL violations, not a prefix slice: a hard blocker can sit
        # after any number of (warning) entries, and missing it would mis-report the
        # gate as YELLOW when it must be RED. The slice is applied ONLY to the detail
        # message below (display cap), never to the classification.
        for v in violations:
            if isinstance(v, dict):
                blk = v.get("blocks_tier", "")
                # Match the tier as the FIRST whitespace-token of blocks_tier
                # ("claude-users (warning)" → "claude-users"), not a substring —
                # `tier in blk` would let "personal" match inside "impersonal…".
                head = blk.split()[0] if blk else ""
                if head == tier or head == "all":
                    desc = v.get("message") or str(v)
                    (warn_parts if "(warning)" in blk else hard_parts).append(desc)
            else:
                hard_parts.append(str(v))
        if hard_parts:
            return {"exit": rc, "cls": "blocker", "detail": "; ".join(hard_parts[:5])}
        if warn_parts:
            return {"exit": rc, "cls": "warning",
                    "detail": "; ".join(warn_parts[:5]) + " (soft — allowed at this tier)"}
        return {"exit": rc, "cls": "blocker", "detail": "portability violation at target tier"}
    if would_fail:
        return {"exit": rc, "cls": "pass",
                "detail": f"informational (blocks at: {', '.join(would_fail)})"}
    # Non-zero exit but no would_fail_at_tiers and no error key — an anomalous
    # portability_lint result. Do NOT silently report it as a clean pass: surface
    # it as a gate error so the fault is visible rather than swallowed.
    return {"exit": rc, "cls": "error",
            "detail": "portability_lint exited non-zero with no classifiable findings"}


def _gate_license(target: str) -> dict:
    rc, out, err = _run([sys.executable, str(SCRIPTS / "spdx_check.py"), target])
    if rc == 0:
        return {"exit": rc, "cls": "pass", "detail": ""}
    if rc == 1:
        try:
            reason = json.loads(out).get("reason", "unrecognized or missing license")
        except Exception:
            reason = out or "unrecognized or missing license"
        return {"exit": rc, "cls": "warning", "detail": reason[:120]}
    return {"exit": rc, "cls": "error", "detail": out or err}


def _gate_history(skill_root: Path) -> tuple[dict, dict]:
    """Returns (history_gate, upstream_url_gate)."""
    h = skill_root / "HISTORY.md"
    if not h.is_file():
        return ({"exit": 1, "cls": "warning", "detail": "absent — degraded mode will apply"},
                {"exit": 1, "cls": "warning", "detail": "absent (no HISTORY.md)"})
    try:
        text = h.read_text(encoding="utf-8")
    except OSError:
        return ({"exit": 1, "cls": "error", "detail": "HISTORY.md unreadable"},
                {"exit": 1, "cls": "warning", "detail": "unreadable"})
    # Search the FRONTMATTER block only — author.history[].source lives there. A raw
    # whole-text search would false-match a `source:` URL written in the changelog
    # body prose, reporting "a PR will open" when no upstream is actually recorded.
    m = re.search(r"source\s*:\s*(https?://\S+)", _fm_block(text))
    upstream = m.group(1).strip() if m else None
    hgate = {"exit": 0, "cls": "pass", "detail": ""}
    ugate = ({"exit": 0, "cls": "pass", "detail": upstream}
             if upstream
             else {"exit": 1, "cls": "warning",
                   "detail": "no author.history[].source URL — no PR will be opened"})
    return hgate, ugate


def _gate_attribution(target: str) -> dict:
    rc, out, err = _run([sys.executable, str(SCRIPTS / "attribution_lint.py"), target])
    if rc == 0:
        return {"exit": rc, "cls": "pass", "detail": ""}
    if rc == 1:
        try:
            d = json.loads(out)
            # Branch on output shape: "error" key = HISTORY.md absent (degraded mode);
            # "violations" key = actual attribution failure. The two cases both exit 1
            # but require distinct messaging.
            if "error" in d:
                reason = d["error"]
            elif d.get("violations"):
                # attribution_lint exits 1 only when a BLOCKING violation exists, but
                # violations[] can also carry advisory entries. Report a blocking one's
                # message, not violations[0] — which could be an advisory that happens
                # to sort first (nothing guarantees blocking-first ordering).
                vs = d["violations"]
                v = next((x for x in vs if x.get("severity") == "blocking"), vs[0])
                reason = v.get("message") or v.get("type") or "attribution violation"
            else:
                reason = "attribution incomplete"
        except Exception:
            reason = out or "attribution incomplete"
        return {"exit": rc, "cls": "warning", "detail": reason[:120]}
    return {"exit": rc, "cls": "error", "detail": out or err}


def _gate_links(target: str) -> dict:
    rc, out, err = _run([sys.executable, str(SCRIPTS / "link_check.py"), target, "--json"])
    if rc == 0:
        return {"exit": rc, "cls": "pass", "detail": ""}
    if rc == 1:
        try:
            d = json.loads(out)
        except Exception:
            return {"exit": rc, "cls": "blocker", "detail": out or "link check failed"}
        broken = d.get("broken_links", [])
        dead = d.get("dead_scripts", [])
        unreadable = d.get("unreadable", [])
        # Broken internal link = blocker (the executor would load a missing file);
        # an unreadable file = blocker too (the scan is incomplete — a YELLOW/clean
        # verdict would be a false negative); dead script = advisory warning.
        if broken:
            first = broken[0]
            detail = f"{len(broken)} broken link(s); e.g. {first['source']} -> {first['cited']}"
            return {"exit": rc, "cls": "blocker", "detail": detail}
        if unreadable:
            return {"exit": rc, "cls": "blocker",
                    "detail": f"{len(unreadable)} unreadable file(s) — link scan incomplete"}
        if dead:
            return {"exit": rc, "cls": "warning",
                    "detail": f"{len(dead)} dead script(s): {', '.join(dead)}"}
        # rc==1 with no broken/unreadable/dead is anomalous (link_check exits 1 only
        # with findings) — surface as an error, not a soft warning that hides it.
        return {"exit": rc, "cls": "error", "detail": "link_check exited 1 with no parsed findings"}
    return {"exit": rc, "cls": "error", "detail": out or err}


def _gate_description(fm: str) -> dict:
    """Advisory description-triggering confidence (the P3-3b confidence field).
    Cheap heuristic only — no claude -p; the full opt-in eval runs at Step 3, not
    here, so readiness stays fast. **Advisory, never changes the ship verdict
    color**: this is a coarse regex signal (a perfectly good description may carry
    no literal 'Do NOT use' boundary), so the real enforcement is the cold audit
    (Step 3) + the opt-in measured eval — here LOW and MEDIUM both surface as a
    NOTE, HIGH as a pass. The gradient lives in `confidence` / the detail string.
    Takes the SKILL.md frontmatter block main() already read (no per-gate re-read)."""
    desc = _fm_field(fm, "description") or ""
    dq = _description_quality(desc)
    conf = dq["confidence"]
    cls = {"high": "pass", "medium": "note", "low": "note"}[conf]
    detail = "" if conf == "high" else (f"confidence {conf}"
             + (" — " + "; ".join(dq["notes"]) if dq["notes"] else ""))
    return {"exit": 0, "cls": cls, "detail": detail, "confidence": conf}


def _gate_mcp_deps(target: str) -> dict:
    rc, out, err = _run([sys.executable, str(SCRIPTS / "mcp_deps.py"), target])
    if rc == 0:
        try:
            note = json.loads(out).get("note", "")
        except Exception:
            note = ""
        return {"exit": rc, "cls": "pass", "detail": note if "N/A" in note else ""}
    if rc == 1:
        try:
            d = json.loads(out)
            undeclared = d.get("undeclared", [])
            detail = f"undeclared: {', '.join(undeclared)}" if undeclared else "undeclared MCP server(s)"
        except Exception:
            detail = out or "undeclared MCP server(s)"
        return {"exit": rc, "cls": "warning", "detail": detail}
    return {"exit": rc, "cls": "error", "detail": out or err}


# ── orchestrate ───────────────────────────────────────────────────────────────

def run_gates(skill_root: Path, tier: str, skill_fm: str) -> dict:
    target = str(skill_root)
    g: dict[str, dict] = {}

    g["frontmatter"] = _gate_frontmatter(target)
    g["description"] = _gate_description(skill_fm)
    g["portability"] = _gate_portability(target, tier)
    g["links"] = _gate_links(target)
    g["license"] = _gate_license(target)

    hg, ug = _gate_history(skill_root)
    g["history"] = hg
    g["upstream_url"] = ug

    if tier in ("claude-users", "model-agnostic"):
        g["attribution"] = _gate_attribution(target)
        g["mcp_deps"] = _gate_mcp_deps(target)

    return g


def verdict(gates: dict, tier: str) -> tuple[str, list[str], list[str]]:
    blockers, warnings = [], []
    for name, g in gates.items():
        cls = g["cls"]
        detail = g.get("detail", "")
        label = f"{name}: {detail}" if detail else name
        if cls == "blocker":
            blockers.append(label)
        elif cls == "warning":
            warnings.append(label)
        elif cls == "error":
            blockers.append(f"{name}: gate error — {detail}")
    return ("red" if blockers else "yellow" if warnings else "green"), blockers, warnings


# ── formatting ────────────────────────────────────────────────────────────────

_ICONS = {"pass": "✓", "blocker": "✗", "warning": "⚠", "note": "·", "error": "✗"}
_LABELS = {
    "frontmatter": "frontmatter (quick_validate)",
    "description": "description triggering",
    "portability": "portability",
    "links": "internal links",
    "license": "license (SPDX)",
    "history": "HISTORY.md",
    "upstream_url": "upstream URL",
    "attribution": "attribution",
    "mcp_deps": "MCP dependencies",
}
_W = 32  # label column width


def format_report(skill_root: Path, tier: str, gates: dict,
                  overall: str, blockers: list[str], warnings: list[str]) -> str:
    lines = [
        f"Readiness check: {skill_root.name}  (tier: {tier})",
        "─" * 72,
        f"{'gate':<{_W}} {'result':<11} detail",
        "─" * 72,
    ]
    for name, g in gates.items():
        cls = g["cls"]
        icon = _ICONS.get(cls, "?")
        label = _LABELS.get(name, name)
        if name == "portability":
            label = f"portability ({tier})"
        result_tag = cls.upper() if cls not in ("pass", "note") else ("PASS" if cls == "pass" else "note")
        detail = g.get("detail", "")
        if detail and len(detail) > 55:
            detail = detail[:52] + "..."
        lines.append(f"{label:<{_W}} {icon} {result_tag:<10} {detail}")
    lines.append("─" * 72)

    color = {"green": "GREEN", "yellow": "YELLOW", "red": "RED"}[overall]
    if overall == "green":
        verdict_line = f"Will complete at {tier}."
    elif overall == "yellow":
        verdict_line = (f"Will proceed with {len(warnings)} warning(s) at {tier}. "
                        f"Attention needed before ship.")
    else:
        bl = "; ".join(b.split(": ", 1)[-1][:60] for b in blockers[:2])
        if len(blockers) > 2:
            bl += f" (+ {len(blockers) - 2} more)"
        verdict_line = f"Will NOT complete at {tier}: {bl}"

    lines.append(f"Overall: {color} — {verdict_line}")
    return "\n".join(lines)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="skill-publisher readiness check")
    ap.add_argument("skill_path", help="skill directory or path to SKILL.md")
    ap.add_argument("--tier", choices=VALID_TIERS, default=None,
                    help="override tier (default: auto-detect from SKILL.md frontmatter)")
    ap.add_argument("--json", dest="json_out", action="store_true",
                    help="emit JSON instead of human-readable report")
    args = ap.parse_args()

    p = Path(args.skill_path).expanduser()
    skill_md = p if p.name == "SKILL.md" else p / "SKILL.md"
    if not skill_md.is_file():
        print(f"ERROR: SKILL.md not found at {skill_md}", file=sys.stderr)
        return 2
    skill_root = skill_md.parent

    # Read SKILL.md ONCE; share its frontmatter block with both tier-detection and
    # the description gate instead of each re-reading the file from disk.
    try:
        skill_fm = _fm_block(skill_md.read_text(encoding="utf-8"))
    except OSError as e:
        print(f"ERROR: cannot read {skill_md}: {e}", file=sys.stderr)
        return 2

    tier = args.tier or detect_tier(skill_fm)
    if tier not in VALID_TIERS:
        print(
            f"ERROR: could not determine tier from frontmatter (got {tier!r}); "
            "pass --tier explicitly",
            file=sys.stderr,
        )
        return 2

    gates = run_gates(skill_root, tier, skill_fm)
    overall, blockers, warnings = verdict(gates, tier)

    if args.json_out:
        print(json.dumps({
            "skill": str(skill_root),
            "tier": tier,
            "overall": overall,
            "description_confidence": gates.get("description", {}).get("confidence", "unknown"),
            "blockers": blockers,
            "warnings": warnings,
            "gates": gates,
            "verdict_line": (
                f"Will complete at {tier}." if overall == "green"
                else f"Will proceed with {len(warnings)} warning(s) at {tier}; attention needed before ship."
                if overall == "yellow"
                else f"Will NOT complete at {tier}: {'; '.join(blockers[:2])}"
            ),
        }, indent=2))
    else:
        print(format_report(skill_root, tier, gates, overall, blockers, warnings))

    return 1 if overall == "red" else 0


if __name__ == "__main__":
    sys.exit(main())
