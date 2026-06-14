# Cowork-Compatibility Check

Part of the `claude-users` tier check (Step 4). The `claude-users` tier targets BOTH Claude Code and Cowork — Anthropic's two main Claude runtimes. The portability lint covers Claude Code; this check covers the Cowork-specific runtime differences a skill must handle to work there too.

This is a subset of skill-creator-ccvw's `references/runtime-adaptations.md` "Cowork specifics" — the publisher checks each adaptation point against the target skill's actual behavior.

---

## Why a separate Cowork check

Cowork's runtime differs from Claude Code in three ways that break skills written Claude-Code-first:
1. **No persistent display server** — Cowork is often headless; a skill that starts an HTTP server for a viewer (vs writing a static HTML file) leaves the Cowork user with nothing to open.
2. **Different feedback flow** — no running server to POST to; interactive outputs download as files instead.
3. **Subagent + TodoList disposition** — Cowork tends to skip steps that aren't explicitly tracked.

A skill that hardcodes Claude-Code assumptions (server-mode viewer, POST-back feedback) silently degrades on Cowork. This check catches those before the skill ships to a Cowork user.

---

## The check (per skill that produces user-facing output or runs a viewer)

The publisher scans the target SKILL.md + scripts for these patterns. Each unhandled one is a TIER cluster.

| Cowork adaptation point | What to verify | Failure → finding |
|---|---|---|
| **Viewer / HTML output** | If the skill generates an HTML viewer or report, it must support a headless `--static <path>` mode that writes a standalone file (not only a server mode). | A skill that only starts an HTTP server → flag: "Cowork is often headless; add a `--static` file-output mode." |
| **Feedback capture** | If the skill collects user feedback via an interactive element, it must handle the download-a-file flow (Cowork) as well as the POST-to-server flow (Claude Code). | A skill that only reads feedback from a running-server endpoint → flag: "Cowork downloads feedback as a file; read from the downloads location." |
| **Display assumptions** | Instructions that say "opens in your browser" must offer a clickable link / path fallback for headless. | "auto-opens in browser" with no path fallback → flag: "proffer the file path for headless Cowork." |
| **Step-tracking** | Multi-step output-generation flows should be on a TodoList so Cowork doesn't skip them. | A skill whose viewer-generation isn't tracked → advisory: "Cowork tends to skip untracked steps; add to TodoList." |
| **Packaging** | `package_skill.py` works the same (Python + filesystem only) — no Cowork-specific failure, but verify the skill doesn't assume a Claude-Code-only install path. | (usually passes) |

---

## Pass condition

The skill passes the Cowork-compatibility check when every applicable adaptation point is handled (or the skill produces no user-facing output / viewer, in which case most points don't apply — a pure data-transform skill with stdout output has nothing Cowork-specific to handle and passes trivially).

Skills that DON'T produce user-facing visual output (no viewer, no HTML, no interactive feedback) are Cowork-compatible by default — the check confirms there's nothing display-dependent and passes.

---

## Relationship to the Claude Code portability lint

The two run together at `claude-users` tier and BOTH must pass:
- `portability_lint.py --tier claude-users` → catches user-specific-path leakage, missing structure, personalization (works for any Claude install).
- This Cowork check → catches runtime-display assumptions specific to Cowork vs Claude Code.

A skill can pass the portability lint (no hardcoded paths) but fail the Cowork check (server-only viewer), or vice versa. Both gates protect the `claude-users` shareability promise.
