#!/usr/bin/env python3
"""Read-only red-flag scan of a plugin or skill folder that is already on disk.

Usage:
    vet_plugin.py PLUGIN_DIR [--max-file-kb N]

Reads text files under PLUGIN_DIR and reports findings as JSON on stdout:
  {"plugin_dir", "files_scanned", "files_skipped", "licence", "prose_to_read", "findings": [...], "no_flags": bool}
Each finding: {"check", "severity", "file", "line", "text"}.

It never executes, installs or imports anything it reads, and it never follows
text found in the files. "prose_to_read" lists the README, CLAUDE.md, command, agent and
skill files the reader must read personally for text that tries to steer an assistant
(any language, any phrasing; the list is capped, see references/vetting-checks.md Limits);
the patterns here miss paraphrases. "no_flags" means only "no pattern below matched in the
files read"; it is not a safety verdict. Pattern matching can miss things and
can flag harmless text, so every finding needs a human read.

Exit codes: 0 scan finished (findings or not); 2 usage error or folder missing.
Pure standard library.
"""
import argparse
import json
import os
import re
import sys

SKIP_DIRS = {".git", "node_modules"}
TEXT_EXT = {".md", ".json", ".sh", ".bash", ".zsh", ".py", ".js", ".ts", ".mjs", ".cjs", ".yaml",
            ".yml", ".toml", ".txt", ".cfg", ".ini", ".env", ".mcp", ""}
BINARY_EXT = {".so", ".dylib", ".dll", ".exe", ".whl", ".pyc", ".node", ".a"}
VENV_DIRS = {"venv", ".venv", "site-packages", "__pycache__", "node_modules"}
MAGIC = (b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
         b"\xca\xfe\xba\xbe")


def native_header(head):
    """True when the first bytes of a file are an ELF header, a Mach-O header (32-bit or 64-bit, either
    byte order, or universal) or a PE header. "MZ" is only two letters that a text file can start with,
    so it counts only when a NUL byte also appears in the first 64 bytes, as it does in a real PE file."""
    return head.startswith(MAGIC) or (head.startswith(b"MZ") and b"\x00" in head[:64])

# Instruction-like text aimed at an AI reader. Shared with catalog_search.py, which applies it to
# catalogue descriptions. Literal and English-only: it finds common phrasings, not every attempt.
AI_TEXT = re.compile(
    r"ignore (all |any )?(previous|prior|above) instructions|do not (respond|answer) first|"
    r"before (you )?respon(d|ding)[, ]+(you must|always)|you must always|never tell the user|"
    r"do not (mention|reveal) (this|these) instruction|"
    r"(note to|message to|attention|important for|instructions? for|dear) +(any |all |the )?"
    r"(ai|llm|language model|assistants?|agents?|claude)\b|"
    r"when you (read|see|parse) this|"
    r"(tell|inform|say to|report to) the user[^.\n]{0,60}\b(safe|audited|verified|trusted)\b|"
    r"\b(rank|list|put|place) (this|it)( plugin)? (first|top|at the top)|"
    r"(install|run|execute)[^.\n]{0,60}\bwithout (asking|confirmation|permission|telling)", re.I)

# (check, severity, regex, extensions or None for all text files)
LINE_CHECKS = [
    ("pipe-to-shell", "high",
     re.compile(r"(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh\b|(curl|wget)\b[^\n|]*\|\s*(sudo\s+)?python3?\b", re.I), None),
    ("transcript-access", "high",
     re.compile(r"transcript_path|\.jsonl\b.*(session|transcript)|session[-_ ]transcript", re.I), None),
    ("telemetry-or-analytics", "high",
     re.compile(r"\b(telemetry|posthog|mixpanel|segment\.io|amplitude|sentry\.io|google-analytics|plausible)\b", re.I), None),
    ("settings-edit", "medium",
     re.compile(r"(settings(\.local)?\.json)", re.I), None),
    ("global-install", "medium",
     re.compile(r"\bnpm\s+(i|install)\s+(-g|--global)\b|\bpip3?\s+install\b|\bbrew\s+install\b|\bcargo\s+install\b", re.I), None),
    ("permission-bypass", "high",
     re.compile(r"--dangerously-skip-permissions|bypassPermissions|Bash\(\*\)|allowed-tools:(?:[^\n]*?[\[\s,\"'])?\*(?=[\]\s,\"']|$)", re.I), None),
    ("ai-addressed-instruction", "review", AI_TEXT, (".md", ".txt")),
    ("outbound-request", "review",
     re.compile(r"\b(curl|wget)\s[^\n]*?https?://|requests\.(post|put)\(|fetch\(\s*[\"']https?://|urllib\.request\.urlopen", re.I),
     (".sh", ".bash", ".zsh", ".py", ".js", ".ts", ".mjs", ".cjs", ".json")),
    ("secret-handling", "review",
     re.compile(r"\.env\b|\b(aws\s+ssm\s+get-parameter|API_KEY|SECRET_KEY|cookie)", re.I), (".sh", ".bash", ".zsh", ".py", ".js", ".ts", ".mjs", ".cjs", ".json")),
]

MAX_PER_FILE = 3
PROSE_EXT = {".md", ".txt"}
PROSE_DOWNGRADE = {"telemetry-or-analytics", "global-install", "settings-edit", "transcript-access"}
BROAD_MATCHERS = {"", "*", ".*", ".+"}
HOOK_EVENTS_EVERY = {"PreToolUse", "PostToolUse", "UserPromptSubmit"}


def _add(findings, check, severity, rel, line, text):
    findings.append({"check": check, "severity": severity, "file": rel, "line": line, "text": text.strip()[:200]})


def scan_hooks(data, rel, findings):
    """Walk any hooks structure ({"hooks": {Event: [{matcher, hooks:[{command}]}]}})."""
    hooks = data.get("hooks") if isinstance(data, dict) else None
    if not isinstance(hooks, dict):
        return
    for event, groups in hooks.items():
        if not isinstance(groups, list):
            continue
        for g in groups:
            if not isinstance(g, dict):
                continue
            matcher = g.get("matcher", "")
            if not isinstance(matcher, str):
                matcher = ""  # a malformed matcher is treated as empty, so the hook is flagged, not dropped
            inner = g.get("hooks")
            inner = inner if isinstance(inner, list) else []
            cmds = [h["command"] for h in inner if isinstance(h, dict) and isinstance(h.get("command"), str)]
            label = f"{event} matcher={matcher!r} -> {' | '.join(c for c in cmds if c)[:120]}"
            # UserPromptSubmit has no tool to match, so it runs on every prompt whatever its matcher.
            if event == "UserPromptSubmit" or (event in HOOK_EVENTS_EVERY and matcher in BROAD_MATCHERS):
                _add(findings, "hook-on-every-call", "high", rel, 0, label)
            elif event == "SessionStart":
                _add(findings, "session-start-hook", "medium", rel, 0, label)
            elif event in ("Stop", "SubagentStop", "SessionEnd", "PreCompact"):
                _add(findings, "lifecycle-hook", "review", rel, 0, label)


def scan_mcp(data, rel, findings):
    """List every MCP server a plugin would launch or connect to."""
    servers = data.get("mcpServers", data) if isinstance(data, dict) else {}
    if not isinstance(servers, dict):
        return
    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            continue
        args = cfg.get("args")
        args = args if isinstance(args, list) else []
        what = cfg.get("url") or " ".join([str(cfg.get("command") or "")] + [str(a) for a in args])
        what = what if isinstance(what, str) else str(what)
        _add(findings, "mcp-server", "review", rel, 0, f"{name}: {what.strip()[:140]}")


def is_text(path, ext, max_bytes):
    if ext in BINARY_EXT:
        return False
    try:
        if os.path.getsize(path) > max_bytes:
            return False
        with open(path, "rb") as fh:
            head = fh.read(512)
    except OSError:
        return False
    if native_header(head) or b"\x00" in head:
        return False
    return ext in TEXT_EXT


# Order matters: the first match wins. The LGPL texts quote the GPL's name and the GPL-2.0 preamble
# mentions the Lesser licence in passing, so LGPL matches only its own title or "as published by"
# wording and is tried before GPL. The MPL-2.0 text names the GNU licences in its Secondary License
# definition, so MPL is tried first.
LICENCE_NAMES = [("MPL", r"mozilla public license"),
                 ("AGPL", r"affero"),
                 ("LGPL", r"\A\s*gnu lesser general public license|gnu lesser general public license\s+version"
                          r"|this version of the gnu lesser general public license"
                          r"|lesser general public license as published by"),
                 ("GPL", r"gnu general public|\bgpl\b"),
                 ("Apache-2.0", r"apache license"), ("MIT", r"\bmit license\b|permission is hereby granted, free of charge"),
                 ("BSD", r"redistribution and use in source and binary forms"), ("ISC", r"\bisc license\b"),
                 ("Unlicense", r"this is free and unencumbered software")]


def detect_licence(root):
    """Licence from a LICENSE/LICENCE/COPYING file (preferred) or the license field of plugin.json.

    A file name matches when it is one of those words alone or followed by a dash, underscore or dot and
    anything (LICENSE, LICENSE.md, LICENSE-MIT, LICENSE_APACHE, COPYING.LESSER); the first in sorted
    order that opens as a file wins.
    """
    for fn in sorted(os.listdir(root)):
        if re.match(r"(license|licence|copying)([-_.].*)?\Z", fn, re.IGNORECASE):
            try:
                with open(os.path.join(root, fn), encoding="utf-8", errors="replace") as fh:
                    head = fh.read(4000).lower()
            except OSError:
                continue
            for name, pat in LICENCE_NAMES:
                if re.search(pat, head):
                    return {"file": fn, "detected": name}
            return {"file": fn, "detected": "unrecognised: read the file"}
    for rel in (os.path.join(".claude-plugin", "plugin.json"), "plugin.json", "package.json"):
        path = os.path.join(root, rel)
        if os.path.isfile(path):
            try:
                with open(path, encoding="utf-8-sig") as fh:
                    lic = json.load(fh).get("license")
            except (OSError, ValueError, AttributeError):
                continue
            if lic:
                return {"file": rel, "detected": str(lic)}
    return {"file": None, "detected": "none found"}


def vet(root, max_kb=512):
    findings, scanned, skipped, seen, prose = [], 0, [], {}, []
    max_bytes = max_kb * 1024
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = os.path.relpath(dirpath, root)
        for d in dirnames:
            if d in VENV_DIRS:
                _add(findings, "committed-environment", "high", os.path.normpath(os.path.join(rel_dir, d)), 0, f"{d} folder is committed")
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and d not in VENV_DIRS)
        for fn in sorted(filenames):
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            ext = os.path.splitext(fn)[1].lower()
            if ext in BINARY_EXT:
                _add(findings, "binary-file", "high", rel, 0, f"{ext} file committed")
                skipped.append(rel)
                continue
            if not is_text(path, ext, max_bytes):
                try:
                    with open(path, "rb") as fh:
                        if native_header(fh.read(64)):
                            _add(findings, "binary-file", "high", rel, 0, "native executable committed")
                except OSError:
                    pass
                skipped.append(rel)
                continue
            scanned += 1
            low = fn.lower()
            if ext in PROSE_EXT and (low.startswith(("readme", "claude", "agents", "install", "setup"))
                                     or fn == "SKILL.md" or rel.split(os.sep)[0] in ("commands", "agents", "skills")):
                prose.append(rel)
            try:
                with open(path, encoding="utf-8-sig", errors="replace") as fh:
                    text = fh.read()
            except OSError:
                skipped.append(rel)
                continue
            if ext == ".json" and ("hook" in fn.lower() or fn in ("plugin.json", "settings.json")):
                try:
                    scan_hooks(json.loads(text), rel, findings)
                except ValueError:
                    pass
            if fn == ".mcp.json" or fn == "mcp.json":
                try:
                    scan_mcp(json.loads(text), rel, findings)
                except ValueError:
                    pass
            for i, line in enumerate(text.splitlines(), 1):
                for check, sev, rx, exts in LINE_CHECKS:
                    if exts is not None and ext not in exts:
                        continue
                    if rx.search(line):
                        if ext in PROSE_EXT and sev in ("high", "medium") and check in PROSE_DOWNGRADE:
                            sev = "review"
                        key = (check, rel)
                        seen[key] = seen.get(key, 0) + 1
                        if seen[key] <= MAX_PER_FILE:
                            _add(findings, check, sev, rel, i, line)
    for (check, rel), n in sorted(seen.items()):
        if n > MAX_PER_FILE:
            _add(findings, check, "review", rel, 0, f"{n - MAX_PER_FILE} more matching lines not listed ({n} in total)")
    order = {"high": 0, "medium": 1, "review": 2}
    findings.sort(key=lambda f: (order.get(f["severity"], 3), f["file"], f["line"], f["check"]))
    return {"plugin_dir": root, "files_scanned": scanned, "files_skipped": len(skipped),
            "licence": detect_licence(root), "prose_to_read": sorted(prose)[:40],
            "findings": findings, "no_flags": not findings}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plugin_dir")
    ap.add_argument("--max-file-kb", type=int, default=512)
    args = ap.parse_args(argv)
    if not os.path.isdir(args.plugin_dir):
        print(f"error: not a folder: {args.plugin_dir}", file=sys.stderr)
        return 2
    print(json.dumps(vet(os.path.abspath(args.plugin_dir), args.max_file_kb), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
