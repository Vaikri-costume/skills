# Readiness Gates

The cheap deterministic gate set run by `scripts/readiness_report.py` in `readiness` mode (Step 1 shortcut) and reused inline by Step 4 in `full` mode. Aggregating these gates in one place means `--readiness` shows what Step 4 will find before any polish or cold-audit cost is incurred.

---

## Gate list

| Gate | Script | Tier scope | Classification on failure |
|------|--------|------------|--------------------------|
| frontmatter | `quick_validate.py <target>` | all (informational at personal) | **RED** (frontmatter malformed or violates hard rule) |
| description triggering | `triggering_eval.py <target>` (heuristic only) | all | **NOTE** (advisory — confidence low/medium surfaced, never changes verdict color) |
| portability | `portability_lint.py <target> --tier <tier>` | all (informational at personal) | **RED** if target tier in `would_fail_at_tiers` |
| internal links | `link_check.py <target>` | all | **RED** on a broken link; **YELLOW** on a dead script |
| license | `spdx_check.py <target>` | all | **YELLOW** (absent or unrecognized SPDX id) |
| HISTORY.md | file presence check | all | **YELLOW** (absent → degraded mode) |
| upstream URL | `author.history[].source` in HISTORY.md | all | **YELLOW** (absent → no PR will open) |
| attribution | `attribution_lint.py <target>` | claude-users+ | **YELLOW** (HISTORY.md incomplete or LICENSE absent) |
| MCP dependencies | `mcp_deps.py <target>` | claude-users+ | **YELLOW** (undeclared MCP server) |
| shared sync | *(dormant — not run in readiness or full ship flow; sync contract retired 2026-06-20)* | — | — |

---

## Verdict rules

- **RED** — at least one gate classifies as BLOCKER or ERROR. Ship will not complete without fixing the blockers.
- **YELLOW** — no blockers; at least one gate classifies as WARNING. Ship will proceed (warnings become USER-PAUSE or degraded-mode events during the full run).
- **GREEN** — all gates pass or are informational notes. Ship is expected to complete at the declared tier.

---

## Classification detail

**RED gates (blocking):**
- `quick_validate.py` exit 1 — YAML doesn't parse, or a hard rule violated (missing `name`/`description`, `name` not kebab-case, `description` over 1024 chars or contains angle brackets, unknown top-level keys). These block every tier and must be fixed before ship proceeds.
- `portability_lint.py` exit 1 with target tier in `would_fail_at_tiers` — a tier-conditional violation blocks ship at this tier. Common cases: hardcoded user paths at claude-users, Claude extensions (`mcp__*` in `allowed-tools` or body, `Agent` tool calls) at model-agnostic.
- `link_check.py` exit 1 **with a broken link** (`broken_links` non-empty in `--json`) — a cited `references/*.md` / `scripts/*.py` / `assets/*` path that does not resolve on disk. The executor would try to load a missing file. Citations attributed to a sibling skill (paragraph names another `skill-<name>`) are auto-excluded, so a finding is genuinely this skill's orphaned link. (Dead scripts alone, with no broken link, are YELLOW — see below.)
- Any gate returning exit 2 (usage/path error) — the gate itself couldn't run; treated as a blocker to surface the fault.

**YELLOW gates (warnings):**
- `spdx_check.py` exit 1 — license field absent or not a recognized SPDX/OSI identifier. The step-4 advisory check passes, but the `--require` PR gate will block when the PR is opened (Step 9). Fix the `license:` frontmatter field before publishing.
- HISTORY.md absent — Step 1 will enter degraded mode (user prompted once for attribution category). Ship can proceed but is not attribution-complete.
- No upstream URL — ship will complete locally but no PR will be opened. Mention in readiness output so the user knows in advance.
- `attribution_lint.py` exit 1 — attribution check incomplete (usually: `author.history[]` present but LICENSE file missing, or HISTORY.md frontmatter missing required fields). Step 4 will surface this as a TIER cluster.
- `mcp_deps.py` exit 1 — skill calls `mcp__server__tool` but the README install section and/or `metadata.mcp-server` don't mention that server. Ship proceeds; installer won't know to connect the MCP — broken-on-arrival. Fix the README.
- `link_check.py` exit 1 with **only dead scripts** (`dead_scripts` non-empty, `broken_links` empty) — a `scripts/*.py` that nothing references or imports. Dead code shipped to users; advisory. Remove the script or wire it into the workflow.

**NOTE (informational, no color change):**
- `portability_lint.py` findings at tiers OTHER than the target tier — the skill has informational violations at stricter tiers. Not blocking for the current target tier. Shown as a pass with an informational note.
- `triggering_eval.py` description **confidence low or medium** — the SKILL.md description lacks a negative-trigger boundary and/or a clear WHEN signal (or is over-length). Surfaced as a note, **never changing the verdict color**: this is a coarse regex heuristic (a good description may legitimately carry no literal 'Do NOT use' boundary), so the cold audit (Step 3) and the opt-in measured eval (`--run-eval`) are the real enforcement — readiness only flags it. The measured accuracy is NOT run in readiness (it needs `claude -p` latency). The top-level `description_confidence` field in `--json` output carries the gradient for programmatic consumers.

---

## What readiness mode does NOT do

- Does **not** run the CCVW Word/Spirit cold audit (Step 3) — that's an Agent dispatch.
- Does **not** run Cowork-compatibility check (`references/cowork-compatibility.md`) — that requires behavioral reading of the skill.
- Does **not** run the security scan (`security_scan.py`) — resource-intensive, runs at Step 4 in full mode.
- Does **not** write any ledger rows, in-flight markers, or version bumps.
- Does **not** read HISTORY.md in depth — only checks for presence and scans for `source:` URL.
- Does **not** run the measured triggering eval (`triggering_eval.py --run-eval`) — that spawns `claude -p` queries. Readiness runs only the cheap description-confidence heuristic; the measured eval is the opt-in Step-3 add-on.

---

## Invocation

```bash
# Human-readable (default — used by --readiness mode executor instruction):
python3 ~/.claude/skills/skill-publisher/scripts/readiness_report.py <target>

# JSON output (programmatic / debugging):
python3 ~/.claude/skills/skill-publisher/scripts/readiness_report.py <target> --json

# Tier override (when frontmatter tier is ambiguous):
python3 ~/.claude/skills/skill-publisher/scripts/readiness_report.py <target> --tier claude-users
```

Exit 0 = green or yellow (ship will proceed); exit 1 = red (blockers); exit 2 = usage/path error.
