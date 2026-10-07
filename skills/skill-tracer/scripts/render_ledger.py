#!/usr/bin/env python3
"""Render a skill-tracer audit ledger as one-page HTML.

STANDALONE, config-driven: this renderer is NOT a consumer of ledger_common.py
(see that module's docstring) — it keeps its own column-name-based parser, its
own DEFAULT_VALID_ACTIONS / DEFAULT_PHASE_COLORS, and its own regression-tag
regex, all overridable via --config. That independence is what lets one script
shape serve both skill-tracer's "Round" ledger and skill-publisher's "Run"
ledger — skill-publisher vendors its own copy of this file
(scripts/render_ledger.py there) and passes its own --config
{POLISH,AUDIT,TIER,PACKAGE,PR} phase map + run-* actions at call time. The
former shared-script sync contract between the two copies was RETIRED
(2026-06-20, HISTORY.md 2.4.1): they are free to diverge and are no longer
kept byte-for-byte identical.

Pure-stdlib (argparse, collections, html, json, os, pathlib, re, subprocess, sys — no third-party dependencies). Reads
the ledger path given as its positional argument and writes HTML to a file
(default: the ledger path with its suffix replaced by .html, e.g. foo.md -> foo.html; or to
--output path). Prints "Wrote HTML to
<path>" to stdout on success.

The rendered page shows:
- Round-on-round cluster count (visual line chart, ASCII-art style for portability;
  the chart counts one row per cluster, not raw flags; HTML heading: "Round-on-round cluster count")
- Cluster fan-out (one row per cluster with flag IDs visualized as chips)
- Regression trace (clusters whose Address names a regression as `regression of round <N> <C-id>`,
  highlighted in red with a [regression] text badge)
- Phase swimlane (phase set depends on the ledger — TRACE/REVIEW/CODE-REVIEW/PREPASS
  plus the CASCADE tier tags Prepass/Code Review for skill-tracer, and for legacy compatibility the
  removed 3.0 tier's tag (Minor Bugs) so old ledgers still render;
  POLISH/AUDIT/TIER/PACKAGE/PR for skill-publisher via --config) — Phase column
  visualized as colored band on each row

Usage:
    python3 render_ledger.py <ledger-path> [--output <html-path>] [--open]

If --open is passed, opens the resulting HTML in the default browser
(macOS `open`, Linux `xdg-open`, Windows `start`).
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


# --- Per-skill config (defaults = skill-tracer; override via --config <json>) ---
# This renderer's SHAPE is shared with skill-publisher's independent copy. The only
# real differences are the phase-color map, the regression-tag patterns, the closed
# set of valid in-flight action keywords, and the round/run column word — all of
# which are configurable below. Everything else (table parse, chart, HTML) is the
# same, so each skill keeps its OWN independent copy of this renderer (skill-tracer +
# skill-publisher, free to diverge — no sync) and overrides only the DEFAULT_*
# values at call time via --config (see skill-publisher's ledger-render
# config). Auto-detection of the "Round" vs "Run" column word means most callers
# don't even need --config for the column.

# skill-tracer's phase vocabulary (mirrors ledger_common.KNOWN_PHASES): the legacy
# direct phases plus the CASCADE tier tags. Each gets its own swimlane color.
DEFAULT_PHASE_COLORS = {
    "TRACE": "#e6f3ff",
    "REVIEW": "#e6ffe9",
    "CODE-REVIEW": "#fff0e6",
    "PREPASS": "#f3e6ff",
    "Prepass": "#f3e6ff",
    # Legacy compatibility: the removed 3.0 tier's rows in old ledgers.
    "Minor Bugs": "#fff9e6",
    "Code Review": "#fff0e6",
}
# Regression markers, checked against the Address column ONLY. The Root cause cell is script-generated
# and never carries a marker; per references/how-to-fix.md "Regression vs cascade" the fixer names a
# regression in its FIX address with the exact phrase `regression of round <N> <C-id>` (the prior
# cluster it regresses), so the pattern requires that phrase and an incidental "regression" does not match.
DEFAULT_REGRESSION_PATTERNS = [r"\bregression of round \d+ C\d+\b"]
REGRESSION_COLUMN = "Address"
# Closed set of valid in-flight action keywords for marker validation: ledger_common.VALID_ACTIONS plus
# the legacy `addressing-MinorBugs` action, which this renderer still accepts on old ledgers (this file
# keeps its own copy by design, see above).
DEFAULT_VALID_ACTIONS = [
    "dispatch", "reviewing", "addressing", "handoff",
    "converged",  # terminal `in-flight:: <timestamp> converged round-<N>` (3 fields, written by close-round --converged)
    "addressing-Prepass", "addressing-CodeReview",
    "addressing-MinorBugs",  # legacy compatibility: a 3.0-and-earlier marker action
]

# Active config — replaced by --config at runtime (see main()).
PHASE_COLORS = dict(DEFAULT_PHASE_COLORS)
REGRESSION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in DEFAULT_REGRESSION_PATTERNS]
VALID_ACTIONS = set(DEFAULT_VALID_ACTIONS)


def parse_ledger(text):
    """Parse a ledger markdown file. Returns:
    {
      "title": str,
      "in_flight": str or None,
      "rows": [{"Runtime": str, "Round": str, "Phase": str, "Cluster": str, "Root cause": str, "Address": str, "Flags": str}, ...],
      "round_summaries": [{round, total_text}, ...],
    }
    """
    lines = text.split("\n")
    result = {
        "title": "",
        "in_flight": None,
        "rows": [],
        "round_summaries": [],
    }

    in_table = False
    header_seen = False
    column_names = []

    for line in lines:
        # Title (first H1)
        if not result["title"] and line.startswith("# "):
            result["title"] = line[2:].strip()
            continue

        # In-flight marker — parse and validate action keyword against the closed list.
        # Tolerates both the legacy 3-field grammar (<runtime> <action> round-N) and the
        # newer 4-field grammar (<runtime> <phase> <state> round-N) — this display-only
        # renderer does not enforce the 4-field state vocabulary, it only flags an
        # unrecognized *action* token when the line parses as the legacy 3-field shape.
        m = re.match(r"^in-flight::\s*(.*)$", line)
        if m:
            raw = m.group(1).strip()
            result["in_flight"] = raw
            parts = raw.split()
            if len(parts) == 3 and parts[1] not in VALID_ACTIONS:
                result["in_flight"] = f"{raw}  ⚠ INVALID ACTION '{parts[1]}' (valid: {sorted(VALID_ACTIONS)})"
            continue

        # Round/Run-summary comment (<!-- Round N total: ... --> or <!-- Run N total: ... -->, optional (PHASE))
        m = re.match(r"^<!--\s*(?:Round|Run)\s+(\d+)(?:\s+\([^)]+\))?\s+total:\s*(.*?)\s*-->", line)
        if m:
            result["round_summaries"].append({
                "round": int(m.group(1)),
                "total_text": m.group(2),
            })
            continue

        # Table header (pipe-delimited). Auto-detect the round-column word ("Round"
        # for tracer, "Run" for publisher); both share the | Runtime | <word> | ... shape.
        if line.startswith("| Runtime | Round") or line.startswith("| Runtime | Run"):
            column_names = [c.strip() for c in line.strip("|").split("|")]
            header_seen = True
            in_table = True
            continue

        # Separator under header
        if header_seen and re.match(r"^\|[\s\-|]+\|$", line):
            continue

        # Data row
        if in_table and line.startswith("|") and line.endswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) != len(column_names):
                # Tolerate a pre-Phase 6-col row under a 7-col (Phase-bearing) header:
                # insert the default Phase at the Phase position so old rows still render
                # (matches append_ledger's ROW_RE, whose Phase group is optional, so a
                # back-compat row append_ledger writes is not dropped here). Any other
                # length mismatch is a genuinely malformed row (e.g. content with an
                # embedded |) and is skipped.
                if "Phase" in column_names and len(cells) == len(column_names) - 1:
                    cells.insert(column_names.index("Phase"), "TRACE")
                else:
                    continue
            row = dict(zip(column_names, cells))
            # Normalize the round/run column into a canonical "_round" key so the
            # rest of the renderer is column-word-agnostic (tracer "Round" / publisher "Run").
            row["_round"] = row.get("Round", row.get("Run", ""))
            # Normalize: add Phase if column absent (pre-migration ledgers). Default to TRACE.
            if "Phase" not in row:
                row["Phase"] = "TRACE"
            # Detect regression
            row["_is_regression"] = any(
                p.search(row.get(REGRESSION_COLUMN, ""))
                for p in REGRESSION_PATTERNS
            )
            result["rows"].append(row)
            continue

        # Empty line or other content — if we hit non-table content, exit table mode
        if in_table and not line.strip():
            in_table = False
            continue

    return result


def ascii_line_chart(per_round_counts):
    """Render an ASCII-art line chart showing cluster count per round (one increment per ledger row)."""
    if not per_round_counts:
        return "(no data)"

    rounds = sorted(per_round_counts.keys())
    counts = [per_round_counts[r] for r in rounds]
    max_count = max(counts) if counts else 1
    if max_count == 0:
        max_count = 1

    lines = []
    height = 8  # rows of ASCII chart
    # Every round takes one column of `width` characters (its widest label plus a space) in the
    # bar rows and the label row alike, and both start after the same 7-character prefix, so each
    # label sits under its own bar.
    width = max(len(f"R{r}") for r in rounds) + 1
    for h in range(height, 0, -1):
        threshold = max_count * h / height
        row = ""
        for c in counts:
            row += ("█" if c >= threshold else " ").ljust(width)
        lines.append(f"{int(threshold):4d} | {row}")
    lines.append("     +" + "-" * (len(counts) * width + 1))
    lines.append("       " + "".join(f"R{r}".ljust(width) for r in rounds))
    return "\n".join(lines)


def render_html(ledger, ledger_path, round_label="Round"):
    """Produce a single HTML page from the parsed ledger.

    round_label is the column word ("Round" for tracer, "Run" for publisher) —
    auto-detected from the header by main() and threaded through for display only.
    """
    title = html.escape(ledger.get("title", "Audit ledger"))
    in_flight = html.escape(ledger.get("in_flight") or "(none — no trace in flight)")

    # Per-round counts
    per_round = defaultdict(int)
    for row in ledger["rows"]:
        # Skip a blank/non-numeric Round cell rather than bucketing it: `int("" or 0)`
        # would silently fold blank-Round rows into a phantom round 0 (rendered "R0"),
        # while a value like "1a" would hit ValueError and vanish — two different wrong
        # states. A row with no real round number simply isn't charted.
        rr = (row.get("_round") or "").strip()
        if not rr.isdigit():
            continue
        per_round[int(rr)] += 1

    chart = html.escape(ascii_line_chart(per_round))

    # Round/Run summaries
    summaries_html = ""
    for s in sorted(ledger["round_summaries"], key=lambda x: x["round"]):
        summaries_html += f'<li><b>{round_label} {s["round"]}:</b> {html.escape(s["total_text"])}</li>'
    if not summaries_html:
        summaries_html = "<li>(no round summaries recorded)</li>"

    # Ledger rows table
    rows_html = ""
    for row in ledger["rows"]:
        phase = row.get("Phase", "TRACE")
        color = PHASE_COLORS.get(phase, "#f0f0f0")
        regression_class = " regression" if row.get("_is_regression") else ""
        regression_badge = ' <span class="regression-badge">[regression]</span>' if row.get("_is_regression") else ""
        cluster_id = html.escape(row.get("Cluster", ""))
        runtime = html.escape(row.get("Runtime", ""))
        round_num = html.escape(row.get("_round", ""))
        root_cause = html.escape(row.get("Root cause", ""))
        address = html.escape(row.get("Address", ""))
        flags = html.escape(row.get("Flags", ""))
        # Render flag IDs as chips
        flag_chips = " ".join(
            f'<span class="chip">{html.escape(f.strip())}</span>'
            for f in flags.split(",") if f.strip()
        )
        phase_css = re.sub(r"[^a-z0-9]+", "-", phase.lower()).strip("-")

        rows_html += f"""
        <tr class="phase-{phase_css}{regression_class}">
            <td>{runtime}</td>
            <td>{round_num}</td>
            <td class="phase-cell" style="background:{color}">{html.escape(phase)}</td>
            <td><b>{cluster_id}</b>{regression_badge}</td>
            <td>{root_cause}</td>
            <td>{address}</td>
            <td>{flag_chips}</td>
        </tr>"""

    # Regression callouts
    regression_rows = [r for r in ledger["rows"] if r.get("_is_regression")]
    regression_count = len(regression_rows)
    regression_section = ""
    if regression_count:
        regression_section = f"""
        <div class="alert">
            <h3>⚠ {regression_count} regression cluster(s) detected</h3>
            <ul>
            {''.join(f'<li><b>{html.escape(r.get("Cluster", ""))}</b> ({round_label} {html.escape(r.get("_round", ""))}): {html.escape(r.get("Root cause", "")[:200])}</li>' for r in regression_rows)}
            </ul>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 1400px; margin: 2em auto; padding: 0 1em; color: #222; }}
h1 {{ border-bottom: 2px solid #333; padding-bottom: 0.3em; }}
h2 {{ margin-top: 2em; border-bottom: 1px solid #ccc; padding-bottom: 0.2em; }}
.meta {{ background: #f7f7f7; padding: 1em; border-radius: 6px; margin-bottom: 1em; }}
.meta dt {{ font-weight: bold; margin-top: 0.5em; }}
.chart {{ font-family: monospace; white-space: pre; background: #fafafa; padding: 1em; border: 1px solid #ddd; border-radius: 4px; overflow-x: auto; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 1em; font-size: 0.9em; }}
th, td {{ border: 1px solid #ccc; padding: 0.5em; text-align: left; vertical-align: top; }}
th {{ background: #eee; position: sticky; top: 0; }}
.phase-cell {{ font-weight: bold; text-align: center; font-size: 0.85em; }}
.regression {{ background-color: #ffe0e0 !important; }}
.regression td {{ background-color: #ffe0e0; }}
.regression-badge {{ font-size: 0.75em; color: #a00; font-weight: normal; margin-left: 0.4em; }}
.chip {{ display: inline-block; padding: 0.1em 0.5em; background: #e0e8f0; border-radius: 10px; font-size: 0.8em; font-family: monospace; margin: 0.1em; }}
.alert {{ background: #fff3cd; border: 1px solid #ffd970; padding: 1em; border-radius: 6px; margin-top: 1em; }}
.legend {{ display: flex; gap: 1em; margin: 1em 0; font-size: 0.9em; flex-wrap: wrap; }}
.legend-item {{ display: flex; align-items: center; gap: 0.5em; }}
.legend-color {{ width: 1.5em; height: 1em; border: 1px solid #999; }}
</style>
</head>
<body>
<h1>{title}</h1>

<div class="meta">
<dl>
<dt>Source ledger</dt><dd>{html.escape(str(ledger_path))}</dd>
<dt>In-flight marker</dt><dd><code>{in_flight}</code></dd>
<dt>Total clusters recorded</dt><dd>{len(ledger["rows"])}</dd>
<dt>{round_label}s present</dt><dd>{', '.join(f'R{r}' for r in sorted(per_round.keys()))}</dd>
</dl>
</div>

<h2>{round_label}-on-{round_label.lower()} cluster count</h2>
<div class="chart">{chart}</div>

<h2>{round_label} summaries</h2>
<ul>{summaries_html}</ul>

{regression_section}

<h2>Phase legend</h2>
<div class="legend">
{''.join(f'<div class="legend-item"><div class="legend-color" style="background:{color}"></div>{html.escape(phase)}</div>' for phase, color in PHASE_COLORS.items())}
<div class="legend-item"><div class="legend-color" style="background:#ffe0e0"></div>Regression row</div>
</div>

<h2>Cluster ledger ({len(ledger["rows"])} rows)</h2>
<table>
<thead>
<tr><th>Runtime</th><th>{round_label}</th><th>Phase</th><th>Cluster</th><th>Root cause</th><th>Address</th><th>Flags</th></tr>
</thead>
<tbody>{rows_html}</tbody>
</table>

</body>
</html>
"""


def open_in_browser(path):
    """Best-effort cross-platform browser open.

    Returns True on success (subprocess exit 0 or os.startfile returned).
    Returns False AND prints diagnostic to stderr on any failure mode:
    - Exception during subprocess construction (binary not found, etc.)
    - subprocess.run returned non-zero exit (binary ran but the open failed)
    """
    try:
        if sys.platform == "darwin":
            result = subprocess.run(["open", str(path)], check=False, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"(could not open in browser: 'open' exited {result.returncode}: {result.stderr.strip()})\nTo view the HTML, open the file manually: navigate to the path printed to stdout.", file=sys.stderr)
                return False
        elif sys.platform.startswith("linux"):
            result = subprocess.run(["xdg-open", str(path)], check=False, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"(could not open in browser: 'xdg-open' exited {result.returncode}: {result.stderr.strip()})\nTo view the HTML, open the file manually: navigate to the path printed to stdout.", file=sys.stderr)
                return False
        elif sys.platform == "win32":
            os.startfile(str(path))
        return True
    except Exception as e:
        # Include the exception TYPE name, not just str(e) — a bare str(e) can be empty
        # or uninformative for some exception classes (e.g. a bare FileNotFoundError()
        # str()s to ""), which makes this diagnostic silently useless without the type name.
        print(f"(could not open in browser: {type(e).__name__}: {e})\nTo view the HTML, open the file manually: navigate to the path printed to stdout.", file=sys.stderr)
        return False


def main():
    global PHASE_COLORS, REGRESSION_PATTERNS, VALID_ACTIONS
    parser = argparse.ArgumentParser(description="Render a skill-tracer/skill-publisher audit ledger as HTML")
    parser.add_argument("ledger_path", help="Path to the markdown ledger file")
    parser.add_argument("--output", default=None, help="Output HTML path (default: the ledger path with its suffix replaced by .html)")
    parser.add_argument("--open", action="store_true", help="Open the resulting HTML in default browser")
    parser.add_argument("--config", default=None,
                        help="JSON (inline or @path) overriding {phase_colors, regression_patterns, "
                             "valid_actions, round_label}. Defaults = skill-tracer; skill-publisher passes "
                             "its POLISH/AUDIT/TIER/PACKAGE/PR map + run-* actions.")
    parser.add_argument("--label", default=None, help="Round-column word override ('Round'/'Run'); else auto-detected")
    args = parser.parse_args()

    round_label = args.label
    if args.config:
        raw = args.config
        if raw.startswith("@"):
            cfgp = Path(raw[1:]).expanduser()
            if not cfgp.is_file():
                print(f"Error: --config file not found: {cfgp}", file=sys.stderr)
                sys.exit(2)
            raw = cfgp.read_text(encoding="utf-8")
        try:
            cfg = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"Error: --config is not valid JSON: {e}", file=sys.stderr)
            sys.exit(2)
        if "phase_colors" in cfg:
            PHASE_COLORS = dict(cfg["phase_colors"])
        if "regression_patterns" in cfg:
            REGRESSION_PATTERNS = [re.compile(p, re.IGNORECASE) for p in cfg["regression_patterns"]]
        if "valid_actions" in cfg:
            VALID_ACTIONS = set(cfg["valid_actions"])
        if round_label is None and cfg.get("round_label"):
            round_label = cfg["round_label"]

    ledger_path = Path(args.ledger_path).expanduser()
    if not ledger_path.is_file():
        print(f"Error: ledger not found at {ledger_path}\nLedgers are written to ${XDG_DATA_HOME:-$HOME/.local/share}/skill-tracer-audit-ledger/<skill-name>.md (tracer) or the equivalent skill-publisher-ledger path (publisher) by a run.\nCheck the skill name and ensure at least one round has completed.", file=sys.stderr)
        sys.exit(1)

    try:
        text = ledger_path.read_text(encoding="utf-8")
    except OSError as e:
        print(f"Error: failed to read ledger at {ledger_path}: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(2)

    # Auto-detect the round-column word from the header if not given.
    if round_label is None:
        round_label = "Run" if re.search(r"^\| Runtime \| Run\b", text, re.MULTILINE) else "Round"

    try:
        ledger = parse_ledger(text)
        html_output = render_html(ledger, ledger_path, round_label=round_label)
    except Exception as e:
        # As in open_in_browser above: a broad except must name the exception class,
        # not just its (possibly empty) str(), for the diagnostic to actually be
        # diagnostic.
        print(f"Error: failed to parse/render ledger {ledger_path}: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(3)

    output_path = Path(args.output).expanduser() if args.output else ledger_path.with_suffix(".html")
    try:
        output_path.write_text(html_output, encoding="utf-8")
    except OSError as e:
        print(f"Error: failed to write HTML to {output_path}: {type(e).__name__}: {e}\nCheck output directory permissions and disk space.", file=sys.stderr)
        sys.exit(4)
    print(f"Wrote HTML to {output_path}")

    if args.open:
        open_in_browser(output_path)


if __name__ == "__main__":
    main()
