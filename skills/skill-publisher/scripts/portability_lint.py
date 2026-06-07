#!/usr/bin/env python3
"""CCVW portability lint — static scan of a skill against the portability-spec.

VENDORED COPY — sync contract. Canonical source:
  ~/.claude/skills/skill-creator-ccvw/scripts/portability_lint.py
A deliberate copy so skill-publisher runs standalone (without skill-creator-ccvw
installed). MUST stay behaviorally in sync with the canonical source — this lint
ENFORCES skill-creator-ccvw's portability-spec, so a drifted copy would have the
publisher enforce a different portability standard than the builder authored.
Check drift:
  diff ~/.claude/skills/skill-creator-ccvw/scripts/portability_lint.py \\
       ~/.claude/skills/skill-publisher/scripts/portability_lint.py
Re-copy from canonical when it changes. (Vendored 2026-05-30.)

Pure-stdlib (json + re only — uses bespoke minimal YAML frontmatter parser so
it runs on machines without PyYAML installed).

Reads <skill>/SKILL.md, checks:
1. CCVW-mandatory frontmatter fields (license, compatibility, metadata, allowed-tools)
2. CCVW-mandatory directories (scripts/, references/, assets/)
3. Tier-specific violations (Claude extensions blocked at model-agnostic;
   personal paths blocked at claude-users+)

Emits structured JSON to stdout.

Usage:
    python3 portability_lint.py <skill-path> [--tier personal|claude-users|model-agnostic]

If --tier is omitted, reads from SKILL.md's metadata.tier field; defaults to
"personal" if absent.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# --- Claude-extension blocklist ---
# These are Claude Code features that will NOT work on non-Claude runtimes.
# The model-agnostic tier disallows all of them; claude-users tier warns; personal allows.
# Full per-tier rules and rationale: see references/portability-spec.md in this skill.

CLAUDE_FRONTMATTER_FIELDS = {
    "disable-model-invocation",
    "user-invocable",
    "context",
    "agent",
    "paths",
}

# Body-level Claude-only patterns (regex, line-based)
CLAUDE_BODY_PATTERNS = [
    (r"!\s*`[^`]+`", "claude-extension", "Dynamic shell injection !`command` is Claude-specific"),
    (r"\$ARGUMENTS\[\d+\]", "claude-extension", "$ARGUMENTS[N] substitution is Claude-specific"),
    (r"\$0(?![A-Za-z0-9_])", "claude-extension", "$0 positional substitution is Claude-specific"),
    (r"\$\{CLAUDE_SESSION_ID\}", "claude-extension", "${CLAUDE_SESSION_ID} is Claude-specific"),
    (r"\bAgent\s+tool\b", "claude-extension", "Agent tool dispatch is Claude-specific"),
    (r"\bWebFetch\b", "claude-extension", "WebFetch is Claude-specific"),
    (r"\bmcp__[a-zA-Z_]+__[a-zA-Z_]+\b", "claude-extension", "mcp__*__* tool names are Claude-specific"),
]

# Path patterns categorized by which tier each blocks.
#
# USER_DATA_PATHS: user-specific data paths every Claude Code install has at
# different content (your ledger vs my ledger). Block at claude-users+ because
# other users don't have YOUR audit history at YOUR exact path.
USER_DATA_PATHS = [
    (r"~/\.claude/skill-tracer-audit-ledger/", "Use $XDG_DATA_HOME/skill-tracer-audit-ledger/ or runtime storage API"),
    (r"~/\.claude/skill-creator-evals-ledger/", "Use $XDG_DATA_HOME/skill-creator-evals-ledger/ or runtime storage API"),
    (r"~/\.claude/CLAUDE\.md", "Use $XDG_CONFIG_HOME/claude/CLAUDE.md or runtime user-memory API"),
    (r"~/\.claude/memory/", "Use $XDG_DATA_HOME/claude/memory/ or runtime memory API"),
]

# CLAUDE_CODE_SYSTEM_PATHS: Claude-Code-system paths every Claude Code install
# has at the same content (the marketplace catalog, session JSONLs, skill
# discovery root). Block at model-agnostic only — other Claude Code users have
# these paths, but Gemini CLI / Cursor / OpenCode don't.
CLAUDE_CODE_SYSTEM_PATHS = [
    (r"~/\.claude/plugins/marketplaces/", "Marketplace access is Claude-Code-specific; document feature as not-supported on non-Claude runtimes"),
    (r"~/\.claude/projects/", "Session JSONLs are Claude-Code-specific; use runtime-provided session API on other runtimes"),
    (r"~/\.claude/skills/[a-zA-Z0-9_-]+/", "Cross-skill dependency path is Claude-Code-specific; use skill-discovery API on other runtimes"),
]

CCVW_MANDATORY_FRONTMATTER = ["license", "compatibility", "metadata", "allowed-tools"]
CCVW_MANDATORY_DIRS = ["scripts", "references", "assets"]
CCVW_METADATA_REQUIRED_KEYS = ["tier", "created", "created-by", "parent-version", "intended-audience"]

# --- Personalization checks (absorbed from skill-tracer accessibility cats 15-16) ---
#
# Cat 15: author-identity / personalization leakage. A skill that embeds the
# author's identity in shippable content confuses a new installer who isn't that
# person. Block at claude-users+ (the new installer needs to not need to know who
# built it). The author's specific name/username is passed in via --author so the
# lint can flag it precisely; absent that, fall back to generic personalization
# phrasings.
PERSONALIZATION_GENERIC_PATTERNS = [
    (r"\bI built this (?:for|because)\b", "Rewrite impersonally — describe what the skill does, not who built it or why personally"),
    (r"\bmy personal\b", "Rewrite without first-person possessive — generic skills don't reference the author's personal context"),
    (r"\bfor my own use\b", "Drop the personal framing; a shipped skill is for any user"),
]

# Cat 16: plan-document / decision-code references. Internal planning notation that
# doesn't ship with the skill — a reader with only the installed skill (no plan
# file, no decision log) sees these as unresolvable. Flag at ALL tiers including
# personal (even your own future self loses the plan-doc context).
PLAN_CODE_PATTERNS = [
    (r"\(per D\d+\)", "Rewrite as standalone prose — `(per D5)` references a plan-doc decision code the installed skill doesn't carry"),
    (r"\bper the plan\b", "Rewrite as standalone prose — `per the plan` references a plan file that doesn't ship with the skill"),
    (r"\bper the (?:original )?feedback\b", "Rewrite as standalone prose — references feedback the installer doesn't have"),
    (r"\bper the decision in section\b", "Rewrite as standalone prose — references a plan-doc section the installer doesn't have"),
    (r"\bsee the plan(?:-doc(?:ument)?)?\b", "Rewrite as standalone prose — points at a plan file that doesn't ship"),
]


def parse_frontmatter(text):
    """Bespoke minimal YAML frontmatter parser — handles flat key:value and one
    level of nested key:value (sufficient for SKILL.md frontmatter).

    Returns (frontmatter_dict, body_text, frontmatter_line_count).
    """
    if not text.startswith("---\n"):
        return {}, text, 0

    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text, 0

    raw = text[4:end]
    body = text[end + 5:]
    fm_lines = raw.count("\n") + 2  # opening ---, closing ---

    fm = {}
    current_key = None
    nested = None
    for line in raw.split("\n"):
        if not line.strip():
            continue
        # Top-level key: value
        m = re.match(r"^([a-zA-Z][a-zA-Z0-9_-]*)\s*:\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            if val == "":
                # Could be nested object on next lines, or empty value
                current_key = key
                nested = {}
                fm[key] = nested
            else:
                # Strip surrounding quotes
                if val.startswith('"') and val.endswith('"'):
                    val = val[1:-1]
                # Try parse as inline object/array
                if val.startswith("{") and val.endswith("}"):
                    try:
                        fm[key] = json.loads(val)
                    except json.JSONDecodeError:
                        fm[key] = val
                elif val.startswith("[") and val.endswith("]"):
                    try:
                        fm[key] = json.loads(val)
                    except json.JSONDecodeError:
                        fm[key] = val
                else:
                    fm[key] = val
                current_key = None
                nested = None
        elif line.startswith("  ") and nested is not None:
            # Nested key
            m2 = re.match(r"^\s+([a-zA-Z][a-zA-Z0-9_-]*)\s*:\s*(.*)$", line)
            if m2:
                nested[m2.group(1)] = m2.group(2).strip()
    return fm, body, fm_lines


def lint_frontmatter(fm):
    """Return list of CCVW-mandatory frontmatter violations."""
    missing = []
    for field in CCVW_MANDATORY_FRONTMATTER:
        if field not in fm:
            missing.append(field)

    metadata_missing_keys = []
    md = fm.get("metadata", {})
    if isinstance(md, dict):
        for k in CCVW_METADATA_REQUIRED_KEYS:
            if k not in md:
                metadata_missing_keys.append(f"metadata.{k}")
    elif "metadata" in fm:
        # metadata is present but not a parseable dict
        metadata_missing_keys = [f"metadata.<unparseable>"]

    return missing + metadata_missing_keys


def lint_directories(skill_path):
    """Return list of CCVW-mandatory missing directories + files."""
    missing = []
    for d in CCVW_MANDATORY_DIRS:
        if not (Path(skill_path) / d).is_dir():
            missing.append(f"{d}/")
    # references/glossary.md is CCVW-mandatory: every CCVW skill ships a per-skill
    # glossary so skill-tracer can read it instead of re-deriving cold.
    if not (Path(skill_path) / "references" / "glossary.md").is_file():
        missing.append("references/glossary.md")
    # README.md (human intent + skill-tracer's considered-fix input) and HISTORY.md
    # (provenance + changelog) are CCVW-mandatory root files as of the three-skill
    # ecosystem refactor. See references/skill-structure-spec.md.
    if not (Path(skill_path) / "README.md").is_file():
        missing.append("README.md")
    if not (Path(skill_path) / "HISTORY.md").is_file():
        missing.append("HISTORY.md")
    return missing


def lint_structure(fm, skill_path):
    """Return list of scaffold-time structural violations (name/folder/reserved/spelling).

    These are registration-correctness checks that apply at EVERY tier (a malformed
    name or a misnamed SKILL.md breaks skill discovery on every runtime). Each
    violation blocks all tiers. Severity is structural, not tier-conditional.
    """
    violations = []
    # Resolve to an absolute path first so the folder basename is correct even when
    # invoked with "." or a trailing-slash path (Path(".").name is "" — a relative
    # path must not be mistaken for an empty folder name).
    sp = Path(skill_path).resolve()
    folder = sp.name

    # SKILL.md exact-spelling diagnostic. The loader requires the file to be named
    # exactly `SKILL.md` (case-sensitive). On a case-insensitive filesystem (default
    # macOS), `(sp / "SKILL.md").is_file()` returns true even when the real entry is
    # `Skill.md`/`skill.md`, so we must compare against the actual directory entries'
    # byte-exact names — not a path existence check.
    try:
        entries = {p.name for p in sp.iterdir() if p.is_file()}
    except (FileNotFoundError, NotADirectoryError):
        entries = set()
    if "SKILL.md" not in entries:
        variants = sorted(n for n in entries if n.lower() in ("skill.md", "skill.markdown"))
        if variants:
            violations.append({
                "line": 0,
                "type": "skill-md-misnamed",
                "message": f"Found {', '.join(variants)} but not SKILL.md — the file must be named exactly `SKILL.md` (case-sensitive; note macOS hides this because its filesystem is case-insensitive)",
                "suggested_fix": f"Rename {variants[0]} to SKILL.md (use a two-step rename on macOS: mv {variants[0]} _tmp && mv _tmp SKILL.md)",
                "blocks_tier": "all (SKILL.md must be exactly that name on every runtime)",
            })

    name = fm.get("name")
    if isinstance(name, str) and name.strip():
        name = name.strip()
        # Reserved-name guard: 'claude'/'anthropic' prefixes are reserved.
        if re.match(r"^(claude|anthropic)([-_]|$)", name, re.IGNORECASE):
            violations.append({
                "line": 1,
                "type": "reserved-name",
                "message": f"Skill name `{name}` uses a reserved prefix (claude/anthropic)",
                "suggested_fix": "Rename without the claude/anthropic prefix — those are reserved",
                "blocks_tier": "all (reserved names are rejected on upload)",
            })
        # name kebab-case
        if not re.match(r"^[a-z0-9-]+$", name) or name.startswith("-") or name.endswith("-") or "--" in name:
            violations.append({
                "line": 1,
                "type": "name-format",
                "message": f"Skill name `{name}` is not kebab-case (lowercase alphanumeric + single hyphens, no leading/trailing/double hyphen)",
                "suggested_fix": "Rewrite the name in kebab-case, e.g. my-skill-name",
                "blocks_tier": "all (name format is validated on upload)",
            })
        # name must match the folder name
        if name != folder:
            violations.append({
                "line": 1,
                "type": "name-folder-mismatch",
                "message": f"Frontmatter name `{name}` does not match the skill folder `{folder}`",
                "suggested_fix": f"Make them identical — rename the folder to `{name}` or set name: {folder}",
                "blocks_tier": "all (name must equal the folder basename)",
            })

    return violations


def lint_frontmatter_content(fm):
    """Return list of frontmatter-content violations independent of tier.

    Widens the angle-bracket security check beyond the description to the WHOLE
    frontmatter block, and bounds compatibility length. These hold at every tier.
    """
    violations = []

    # XML-tag-shaped content anywhere in frontmatter is a prompt-injection surface
    # (frontmatter is injected into the system prompt; a literal `<tag>` could carry
    # injected instructions). Match tag-SHAPED patterns (`<word...>` / `</word>`),
    # NOT bare comparison operators — `claude-code@>=2.0` and `<3.0` version
    # constraints are legitimate and must not false-positive.
    TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
    def scan(val, path):
        if isinstance(val, str):
            if TAG_RE.search(val):
                violations.append({
                    "line": 1,
                    "type": "frontmatter-angle-bracket",
                    "message": f"XML-tag-shaped content (`<...>`) in frontmatter field `{path}` — frontmatter is injected into the system prompt, so tag-shaped content is a prompt-injection surface (version operators like >=2.0 are fine)",
                    "suggested_fix": "Remove the tag-shaped `<...>` — use [placeholder] brackets for placeholders, or rephrase",
                    "blocks_tier": "all (security restriction on frontmatter content)",
                })
        elif isinstance(val, dict):
            for k, v in val.items():
                scan(v, f"{path}.{k}")
        elif isinstance(val, list):
            for i, v in enumerate(val):
                scan(v, f"{path}[{i}]")

    for k, v in fm.items():
        scan(v, k)

    # description length bound (1024) — mirrors quick_validate; surfaced here so the
    # scaffold-time portability lint catches it too.
    desc = fm.get("description")
    if isinstance(desc, str) and len(desc) > 1024:
        violations.append({
            "line": 1,
            "type": "description-too-long",
            "message": f"Description is {len(desc)} characters; the maximum is 1024",
            "suggested_fix": "Trim the description to <=1024 characters (keep WHAT + WHEN + key triggers)",
            "blocks_tier": "all (1024-char description limit)",
        })

    # compatibility length bound (1..500)
    compat = fm.get("compatibility")
    if isinstance(compat, str) and not (1 <= len(compat) <= 500):
        violations.append({
            "line": 1,
            "type": "compatibility-length",
            "message": f"compatibility is {len(compat)} characters; it must be 1–500",
            "suggested_fix": "Set a compatibility string between 1 and 500 characters",
            "blocks_tier": "all (compatibility length bound)",
        })

    return violations


def lint_tier_violations(fm, body, body_start_line, tier):
    """Return list of tier-specific violations."""
    violations = []

    # Frontmatter-level Claude extensions (model-agnostic blocks all; claude-users/personal allow)
    if tier == "model-agnostic":
        for field in CLAUDE_FRONTMATTER_FIELDS:
            if field in fm:
                violations.append({
                    "line": 1,
                    "type": "claude-extension",
                    "message": f"Frontmatter field `{field}` is Claude-specific",
                    "suggested_fix": "Strip and restructure intent into description prose",
                    "blocks_tier": "model-agnostic",
                })

    # Body-level Claude patterns (model-agnostic blocks; claude-users warns; personal allows)
    if tier in ("model-agnostic", "claude-users"):
        body_lines = body.split("\n")
        for i, line in enumerate(body_lines):
            for pattern, vtype, msg in CLAUDE_BODY_PATTERNS:
                if re.search(pattern, line):
                    violations.append({
                        "line": body_start_line + i,
                        "type": vtype,
                        "message": msg,
                        "suggested_fix": "See the Claude-extension blocklist in references/portability-spec.md for the per-feature rewrite",
                        "blocks_tier": "model-agnostic" if tier == "model-agnostic" else "claude-users (warning)",
                    })

    # User-data paths (block at claude-users+ — other users don't have your specific data)
    if tier in ("claude-users", "model-agnostic"):
        body_lines = body.split("\n")
        for i, line in enumerate(body_lines):
            for path_pattern, suggested in USER_DATA_PATHS:
                if re.search(path_pattern, line):
                    violations.append({
                        "line": body_start_line + i,
                        "type": "user-data-path",
                        "message": f"User-data path pattern `{path_pattern}` in skill body",
                        "suggested_fix": suggested,
                        "blocks_tier": "claude-users",
                    })

    # Claude-Code-system paths (block at model-agnostic only — other Claude Code
    # users have them, non-Claude runtimes don't)
    if tier == "model-agnostic":
        body_lines = body.split("\n")
        for i, line in enumerate(body_lines):
            for path_pattern, suggested in CLAUDE_CODE_SYSTEM_PATHS:
                if re.search(path_pattern, line):
                    violations.append({
                        "line": body_start_line + i,
                        "type": "claude-code-system-path",
                        "message": f"Claude-Code-system path pattern `{path_pattern}` in skill body",
                        "suggested_fix": suggested,
                        "blocks_tier": "model-agnostic",
                    })

    # model-agnostic requires compatibility: agentskills.io@X
    if tier == "model-agnostic":
        compat = str(fm.get("compatibility", ""))
        if not compat.startswith("agentskills.io@"):
            violations.append({
                "line": 1,
                "type": "compatibility-attribution",
                "message": "model-agnostic tier requires `compatibility: agentskills.io@<version>`",
                "suggested_fix": "Set frontmatter `compatibility: agentskills.io@1.0`",
                "blocks_tier": "model-agnostic",
            })

    return violations


def lint_personalization(body, body_start_line, tier, author=None):
    """Return personalization (cat 15) + plan-code (cat 16) violations.

    Cat 15 (personalization): blocks at claude-users+ (a shared skill shouldn't
    embed the author's identity). If `author` is given, flag exact occurrences of
    that name/username in the body; always also flag generic personalization
    phrasings.

    Cat 16 (plan-code): flags at ALL tiers (plan-doc references don't ship with
    the skill, so even the author's future self loses the context).
    """
    violations = []
    body_lines = body.split("\n")

    # Cat 16 — plan-code references (all tiers)
    for i, line in enumerate(body_lines):
        for pattern, suggested in PLAN_CODE_PATTERNS:
            if re.search(pattern, line, re.IGNORECASE):
                violations.append({
                    "line": body_start_line + i,
                    "type": "plan-code-leakage",
                    "message": f"Plan-document reference matching `{pattern}` in skill body (cat 16)",
                    "suggested_fix": suggested,
                    "blocks_tier": "all (plan-doc refs don't ship with the skill)",
                })

    # Cat 15 — personalization leakage (claude-users+ only)
    if tier in ("claude-users", "model-agnostic"):
        for i, line in enumerate(body_lines):
            for pattern, suggested in PERSONALIZATION_GENERIC_PATTERNS:
                if re.search(pattern, line, re.IGNORECASE):
                    violations.append({
                        "line": body_start_line + i,
                        "type": "personalization-leakage",
                        "message": f"Personalization phrasing matching `{pattern}` in skill body (cat 15)",
                        "suggested_fix": suggested,
                        "blocks_tier": "claude-users",
                    })
            if author:
                # Flag exact author-name occurrences (case-insensitive whole-word)
                if re.search(rf"\b{re.escape(author)}\b", line, re.IGNORECASE):
                    violations.append({
                        "line": body_start_line + i,
                        "type": "personalization-leakage",
                        "message": f"Author identity `{author}` appears in shippable skill body (cat 15)",
                        "suggested_fix": "Replace with 'the user' / 'you' or drop the personal reference — a new installer shouldn't need to know who built it",
                        "blocks_tier": "claude-users",
                    })

    return violations


def compute_would_fail_at(violations, ccvw_missing):
    """Compute which tiers this skill would fail at given current violations."""
    would_fail = set()
    if ccvw_missing:
        # CCVW-mandatory violations fail every tier
        would_fail.update({"personal", "claude-users", "model-agnostic"})
    for v in violations:
        bt = v.get("blocks_tier", "")
        if bt.startswith("all"):
            would_fail.update({"personal", "claude-users", "model-agnostic"})
        if "model-agnostic" in bt:
            would_fail.add("model-agnostic")
        if "claude-users" in bt:
            would_fail.add("claude-users")
    return sorted(would_fail)


def main():
    parser = argparse.ArgumentParser(description="CCVW portability lint")
    parser.add_argument("skill_path", help="Path to skill directory")
    parser.add_argument("--tier", default=None, choices=["personal", "claude-users", "model-agnostic"],
                        help="Override declared tier")
    parser.add_argument("--author", default=None,
                        help="Author name/username to flag if it appears in shippable skill body (cat 15 personalization). "
                             "If omitted, reads author.primary from the skill's HISTORY.md frontmatter when present.")
    args = parser.parse_args()

    skill_path = Path(args.skill_path).expanduser()
    skill_md = skill_path / "SKILL.md"
    if not skill_md.is_file():
        print(json.dumps({"error": f"SKILL.md not found at {skill_md}"}, indent=2))
        sys.exit(1)

    text = skill_md.read_text()
    fm, body, fm_lines = parse_frontmatter(text)
    body_start_line = fm_lines + 1

    declared_tier = args.tier or fm.get("metadata", {}).get("tier", "personal")
    ccvw_missing = lint_frontmatter(fm) + lint_directories(skill_path)
    # Structural + frontmatter-content checks apply at every tier (registration
    # correctness + the frontmatter prompt-injection surface), so they run before
    # the tier-conditional checks and are merged into the same violations list.
    violations = lint_structure(fm, skill_path)
    violations += lint_frontmatter_content(fm)
    violations += lint_tier_violations(fm, body, body_start_line, declared_tier)

    # Author for personalization (cat 15): explicit --author wins; else read
    # author.primary from HISTORY.md (the three-skill refactor moved author out of
    # SKILL.md's metadata into HISTORY.md top-level frontmatter).
    author = args.author
    if author is None:
        history_md = skill_path / "HISTORY.md"
        if history_md.is_file():
            hfm, _, _ = parse_frontmatter(history_md.read_text())
            a = hfm.get("author")
            if isinstance(a, dict):
                author = a.get("primary")
            elif isinstance(a, str):
                author = a
    violations += lint_personalization(body, body_start_line, declared_tier, author)
    would_fail = compute_would_fail_at(violations, ccvw_missing)

    result = {
        "skill_path": str(skill_path),
        "declared_tier": declared_tier,
        "ccvw_mandatory_missing": ccvw_missing,
        "tier_violations": violations,
        "would_fail_at_tiers": would_fail,
    }

    print(json.dumps(result, indent=2))
    # Exit 1 if any CCVW-mandatory missing or any violations at declared tier
    if ccvw_missing or violations:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
