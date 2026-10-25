#!/usr/bin/env python3
"""Scripted graders for this skill's own eval rounds.

Usage: python3 evals/graders.py --check-set NAME --skill-dir DIR [--run-dir DIR] [--persona STR ...] [--intent-word STR ...] [--fixtures DIR]
Writes <run-dir>/grading.json (summary + expectations[{text, passed, evidence}]) and prints it.
Check sets are named in evals/evals.json. Every check is mechanical: same files in, same verdict out.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PY = sys.executable


def run(cmd, cwd=None, timeout=60):
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def read(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def all_text(d):
    out = []
    for f in Path(d).rglob("*"):
        if f.is_file() and ".git" not in f.relative_to(d).parts and f.suffix not in {".pyc", ".png", ".jpg", ".pdf"}:
            out.append((f, read(f)))
    return out


# ---- checks: each returns (passed, evidence) ----
def c_quick_validate(d, **k):
    rc, o, e = run([PY, str(ROOT / "scripts/quick_validate.py"), str(d)])
    return rc == 0, (o + e).strip()[:200]


def c_mandatory_files(d, **k):
    rc, o, e = run([PY, str(ROOT / "scripts/portability_lint.py"), str(d)])
    try:
        data = json.loads(o)
    except ValueError:
        return False, f"lint output not JSON: {(o + e)[:150]}"
    if not isinstance(data, dict) or "error" in data or "ccvw_mandatory_missing" not in data:
        return False, f"lint gave no result: {str(data)[:150]}"
    miss = data["ccvw_mandatory_missing"]
    return not miss, f"missing: {miss}" if miss else "README, HISTORY, glossary, dirs and frontmatter present"


def c_attribution(d, **k):
    rc, o, e = run([PY, str(ROOT / "scripts/attribution_lint.py"), str(d)])
    try:
        data = json.loads(o)
    except ValueError:
        return False, f"not JSON: {(o + e)[:150]}"
    if not isinstance(data, dict) or "error" in data or "violations" not in data:
        return False, f"lint gave no result: {str(data)[:150]}"
    # author-identity-mismatch compares with the grader machine's gh login; the eval personas are fictional, so it is ignored here
    blocking = [v for v in data.get("violations", []) if v.get("severity") == "blocking" and v.get("type") != "author-identity-mismatch"]
    return not blocking, f"declared {data.get('declared_category')}, blocking: {[v.get('type') for v in blocking]} (ignored: author-identity-mismatch (fictional persona))"


def c_script_exists(d, **k):
    scripts = [f for f in (Path(d) / "scripts").glob("*") if f.suffix in {".py", ".sh"} and f.name != "__init__.py" and len(read(f).splitlines()) >= 10]
    return bool(scripts), f"scripts: {[s.name for s in scripts]}"


def c_script_contract(d, **k):
    ok = []
    for f in (Path(d) / "scripts").glob("*.py"):
        t = read(f)
        head = t[:1500].lower()
        if "input" in head and "output" in head:
            ok.append(f.name)
    return bool(ok), f"scripts stating input and output: {ok}"


def c_evals_json(d, **k):
    try:
        data = json.loads(read(Path(d) / "evals/evals.json"))
    except ValueError:
        return False, "evals/evals.json missing or not JSON"
    ev = data.get("evals", [])
    ids_ok = all(isinstance(e.get("id"), int) and not isinstance(e.get("id"), bool) for e in ev)
    ok = len(ev) >= 2 and ids_ok and all(e.get("expectations") for e in ev)
    return ok, f"{len(ev)} evals, integer ids: {ids_ok}"


def c_tier_claude_users(d, **k):
    m = re.search(r"(?m)^\s+tier:\s*(\S+)", read(Path(d) / "SKILL.md"))
    return bool(m) and m.group(1) == "claude-users", f"tier: {m.group(1) if m else None}"


def c_skill_under_500(d, **k):
    n = len(read(Path(d) / "SKILL.md").splitlines())
    return 0 < n <= 500, f"{n} lines"


def c_no_persona(d, persona=(), **k):
    hits = []
    for f, t in all_text(d):
        for s in persona:
            if s.lower() in t.lower():
                hits.append(f"{f.relative_to(d)}: {s}")
    return not hits, "; ".join(hits[:5]) or "no persona strings found"


def c_readme_intent(d, intent_words=(), **k):
    t = read(Path(d) / "README.md")
    m = re.search(r"(?ms)^## Intent\s*\n(.*?)(?=^## |\Z)", t)
    if not m:
        return False, "no ## Intent section"
    body = m.group(1).lower()
    missing = [w for w in intent_words if w.lower() not in body]
    return not missing, f"missing intent words: {missing}" if missing else "intent states the trade-off"


def c_checked_marketplace(d, **k):
    ok = "checked-marketplace:" in read(Path(d) / "HISTORY.md")
    return ok, "HISTORY.md has the line" if ok else "no checked-marketplace line"


def c_standard_sections(d, **k):
    t = read(Path(d) / "SKILL.md")
    need = ["known limitations", "examples", "troubleshooting"]
    miss = [n for n in need if not re.search(rf"(?mi)^##+\s+{n}\b", t)]
    return not miss, f"missing sections: {miss}" if miss else "Known limitations, Examples, Troubleshooting present"


def c_description_triggers(d, **k):
    t = read(Path(d) / "SKILL.md")
    m = re.search(r'(?m)^description:\s*"?(.*)$', t)
    desc = m.group(1) if m else ""
    ok = len(desc) >= 120 and re.search(r"(?i)\buse (when|whenever)\b|triggers? on|when the user", desc)
    return bool(ok), f"description {len(desc)} chars"


# ---- round 2: adapt path ----
def _words(s):
    return re.findall(r"[a-z0-9']+", s.lower())


def _shingles(s, n=8):
    w = _words(s)
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def _body(p):
    t = read(Path(p) / "SKILL.md")
    return t.split("---", 2)[-1]


def _out_shingles(d, n=8):
    out = set()
    for f, t in all_text(d):
        out |= _shingles(t, n)
    return out


def c_adapt_history_source(d, fixtures=None, **k):
    h = read(Path(d) / "HISTORY.md")
    ok = "citation-formatter" in h and "apache" in h.lower() and "example.com/skills/citation-formatter" in h
    return ok, "HISTORY names citation-formatter, Apache-2.0 and its source URL" if ok else "HISTORY lacks source name, licence or URL for the Apache candidate"


def c_adapt_category(d, **k):
    m = re.search(r"(?m)^category:\s*([A-D])", read(Path(d) / "HISTORY.md"))
    return bool(m) and m.group(1) in "ABC", f"category {m.group(1) if m else None}"


def c_adapt_no_copy_unknown_licence(d, fixtures=None, **k):
    common = _out_shingles(d) & _shingles(_body(Path(fixtures) / "note-tidier"))
    return not common, f"{len(common)} 8-word runs copied from the unlicensed candidate"


def c_adapt_no_copy_redflag(d, fixtures=None, **k):
    common = _out_shingles(d) & _shingles(_body(Path(fixtures) / "quick-summariser"))
    url = any("collector.example.net" in t for _, t in all_text(d))
    return not common and not url, f"{len(common)} copied runs; collector URL present: {url}"


def c_adapt_apache_attributed_if_copied(d, fixtures=None, **k):
    common = _out_shingles(d) & _shingles(_body(Path(fixtures) / "citation-formatter"))
    h = read(Path(d) / "HISTORY.md").lower()
    if not common:
        return True, "no text copied from the Apache candidate"
    ok = "citation-formatter" in h and "apache" in h
    return ok, f"{len(common)} copied runs; attribution present: {ok}"


def c_adapt_question_logged(d, run_dir=None, **k):
    q = read(Path(run_dir) / "outputs/questions.md") if run_dir else ""
    ok = "note-tidier" in q.lower() and "licen" in q.lower()
    return ok, "questions.md asks about note-tidier's licence" if ok else "no question about the unknown licence in outputs/questions.md"


def c_adapt_not_credited_redflag(d, **k):
    h = read(Path(d) / "HISTORY.md")
    # The block runs to the next top-level key, a '---' line or the end, so dashes at column 0 stay inside it.
    m = re.search(r"(?ms)^inspirations:[^\n]*\n(.*?)(?=^[A-Za-z0-9_][\w-]*[ \t]*:|^---|\Z)", h)
    block = (m.group(1) if m else "") + "".join(re.findall(r"(?mi)^.*\bsee also\b.*$", h))
    ok = "quick-summariser" not in block.lower()
    return ok, "red-flagged candidate is not recorded as a source" if ok else "red-flagged candidate credited as a source"


def c_adapt_lineage_what_taken(d, **k):
    h = read(Path(d) / "HISTORY.md").lower()
    # The lineage prose sits under the '## Lineage notes' heading, below the frontmatter
    # entry that names the candidate; the whole file is read only when that heading is absent.
    m = re.search(r"(?m)^#+[ \t]*lineage notes.*$", h)
    sec = h[m.end():] if m else h
    ok = "citation-formatter" in sec and bool(re.search(r"\b(?:sort|sorts|sorted|sorting|ordering)\b", sec))
    return ok, "lineage says what was taken from the Apache candidate" if ok else "HISTORY does not say which idea came from the Apache candidate"

def c_fork_category_a(d, **k):
    m = re.search(r"(?m)^category:\s*([A-D])", read(Path(d) / "HISTORY.md"))
    return bool(m) and m.group(1) == "A", f"category {m.group(1) if m else None}"


def c_fork_license_kept(d, **k):
    lic = [f for f in Path(d).glob("LICENSE*")]
    ok = any("apache license" in read(f).lower() for f in lic)
    return ok, f"licence files: {[f.name for f in lic]}"


def c_fork_chain(d, **k):
    h = read(Path(d) / "HISTORY.md")
    ok = "citation-formatter" in h and "example.com/skills/citation-formatter" in h and "apache" in h.lower() and re.search(r"(?m)^\s*-?\s*role:", h) is not None
    return bool(ok), "history chain names the original, its source and licence" if ok else "history chain incomplete"


def c_fork_changes_stated(d, **k):
    h = read(Path(d) / "HISTORY.md").lower()
    ok = bool(re.search(r"changes?-summary|changed|modified", h)) and "citation-formatter" in h
    return ok, "changes to the original are stated" if ok else "no statement of what changed"


# ---- round 3: personal data, profile, scripting ----
HOME_PATH = re.compile(r"(?:/Users/[A-Za-z][\w.-]*|/home/[A-Za-z][\w.-]*|[A-Z]:\\Users\\)")


def c_no_home_paths(d, **k):
    placeholder = re.compile(r"/(?:Users|home)/(?:you|user|name|me|example|yourname|username|<[^>]+>)\b", re.I)
    hits = [f"{f.relative_to(d)}: {m.group(0)}" for f, t in all_text(d) if not f.name.startswith("test_")
            for m in HOME_PATH.finditer(t) if not placeholder.match(t[m.start():m.start() + 40])]
    return not hits, "; ".join(hits[:4]) or "no absolute home path in the skill"


def c_configurable_input(d, **k):
    t = "".join(read(f) for f in (Path(d) / "scripts").glob("*")).lower()
    ok = bool(re.search(r"add_argument\(|sys\.argv|os\.environ|getenv\(|configparser|\$\{?[a-z_]*(?:dir|folder|input)[a-z_]*\}?|\$1\b", t))
    return ok, "keyword proxy: a script reads its folder from an argument, config or environment" if ok else "keyword proxy: no script reads an argument, config or environment"


def c_logging_off_switch(d, **k):
    t = "".join(read(f) for f in (Path(d) / "scripts").glob("*")).lower()
    configurable = bool(re.search(r"add_argument\(\s*['\"]--log|environ[^\n]*log|getenv\([^)\n]*log", t))
    off = bool(re.search(r"--no-log|no[_-]log|['\"](?:off|none|disabled?)['\"]", t))
    return configurable and off, f"keyword proxy over scripts: log path configurable (argument or environment): {configurable}; explicit off value: {off}"


def c_no_fixed_tmp(d, **k):
    hits = [str(f.relative_to(d)) for f, t in all_text(d) if re.search(r"(?<![\w.])/tmp/", t)]
    return not hits, f"fixed /tmp path in: {hits[:4]}" if hits else "no fixed /tmp path"


def c_tests_pass(d, **k):
    cands = [f for f in list(Path(d).rglob("test_*.py")) + list(Path(d).rglob("*_test.py"))]
    if not cands:
        return False, "no test file"
    rc, o, e = run([PY, "-m", "unittest", "discover", "-s", str(cands[0].parent), "-t", str(Path(d))], cwd=str(d))
    if rc != 0:
        rc, o, e = run([PY, "-m", "unittest", str(cands[0])], cwd=str(d))
    return rc == 0, f"{cands[0].name}: {'pass' if rc == 0 else (o + e)[-150:]}"


def c_no_opus(d, **k):
    hits = [str(f.relative_to(d)) for f, t in all_text(d) if re.search(r"(?i)\bopus\b", t)]
    return not hits, f"Opus named in: {hits[:3]}" if hits else "no Opus anywhere (helpers stay on Sonnet)"


def c_deviations_logged(d, run_dir=None, **k):
    t = read(Path(run_dir) / "outputs/deviations.md").lower() if run_dir else ""
    ok = "path" in t and "opus" in t
    return ok, "deviations.md explains the path and model requests" if ok else "deviations.md missing or silent on the path and Opus requests"

# ---- round 4: loop-until-dry on a seeded skill ----
def c_cited_refs_exist(d, **k):
    t = read(Path(d) / "SKILL.md")
    missing = [r for r in sorted(set(re.findall(r"references/[A-Za-z0-9._-]+\.md", t))) if not (Path(d) / r).is_file()]
    return not missing, f"cited but missing: {missing}" if missing else "every cited reference exists"


def c_readme_has_intent(d, **k):
    ok = re.search(r"(?m)^## Intent\s*$", read(Path(d) / "README.md")) is not None
    return ok, "README has ## Intent" if ok else "README has no ## Intent"


def _count(d, text):
    f = Path(d) / "scripts/count_words.py"
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tmp:
        tmp.write(text)
    rc, o, e = run([PY, str(f), tmp.name])
    Path(tmp.name).unlink()
    return o.strip() if rc == 0 else f"error: {e[-80:]}"


def c_count_correct(d, **k):
    got = _count(d, "one two three\nfour five\n\nsix  seven\n")
    return got == "7", f"counted {got}, expected 7"


def c_count_empty(d, **k):
    got = _count(d, "")
    return got == "0", f"empty file counted {got}, expected 0"


def c_no_placeholders(d, **k):
    hits = [str(f.relative_to(d)) for f, t in all_text(d) if re.search(r"\b(TODO|TBD|FIXME|lorem ipsum|placeholder)\b", t, re.I)]
    return not hits, f"placeholder text in: {hits[:4]}" if hits else "no placeholder text"


def c_ledger_valid(d, run_dir=None, **k):
    sys.path.insert(0, str(ROOT / "scripts"))
    import loop_ledger
    try:
        led = json.loads(read(Path(run_dir) / "outputs/ledger.json"))
        rounds = led["rounds"]
        dec = loop_ledger.decide(led)
    except Exception as exc:
        return False, f"no valid ledger at outputs/ledger.json ({exc})"
    ok = 2 <= len(rounds) <= 3 and dec["stop"]
    return ok, f"{len(rounds)} rounds, stop={dec['stop']} reason={dec['reason']}"


def c_final_stop_reason(d, run_dir=None, **k):
    t = read(Path(run_dir) / "outputs/final.md").lower() if run_dir else ""
    ok = re.search(r"\b(clean_pass|clean pass|cap|no_progress|no progress)\b", t) is not None
    return ok, "final.md states why the loop stopped" if ok else "final.md missing or silent on the stop reason"

# ---- round 5: large build ----
def _markers():
    return [f"Class marker {chr(65 + i % 26)}{i}." for i in range(48)]


def _skill_corpus(d):
    return [(f, t) for f, t in all_text(d) if f.suffix in {".md", ".txt", ".py"} and "evals" not in f.relative_to(d).parts]


def c_rules_complete(d, **k):
    corpus = "\n".join(t for _, t in _skill_corpus(d))
    missing = [m for m in _markers() if m not in corpus]
    return not missing, f"{48 - len(missing)}/48 rules present" + (f"; missing e.g. {missing[:3]}" if missing else "")


def c_rules_once(d, **k):
    corpus = "\n".join(t for _, t in _skill_corpus(d))
    dup = [m for m in _markers() if corpus.count(m) > 1]
    return not dup, f"{len(dup)} rules written more than once" + (f", e.g. {dup[:3]}" if dup else "")


def c_rules_verbatim(d, **k):
    corpus = "\n".join(t for _, t in _skill_corpus(d))
    bad = [i for i in range(48) if f"(case {i})." not in corpus]
    return not bad, f"{48 - len(bad)}/48 rationales kept verbatim"


def c_no_long_lines(d, **k):
    long_ = [i + 1 for i, l in enumerate(read(Path(d) / "SKILL.md").splitlines()) if len(l) > 1000]
    return not long_, f"lines over 1000 chars: {long_[:5]}" if long_ else "no SKILL.md line over 1000 characters"


def c_four_ready(d, run_dir=None, **k):
    base = Path(run_dir) / "outputs/eval-ws" if run_dir else None
    metas = list(base.glob("iteration-*/eval-*/eval_metadata.json")) if base and base.is_dir() else []
    ids = []
    by_iter = {}
    for m in metas:
        try:
            eid = json.loads(m.read_text()).get("eval_id")
        except ValueError:
            continue
        ids.append(eid)
        by_iter.setdefault(m.parent.parent.name, []).append(eid)
    # Proxy only: a finished workspace cannot show whether eval 0 was built before the others
    # (the metadata files carry no creation order), so this verifies that inside each iteration
    # the built ids are 0 alone or a prefix 0, 1, ... with none skipped; the pilot itself is
    # evidenced only by c_pilot_explained. Ids repeat across iterations, so each iteration is checked on its own.
    per_iter = [sorted(i for i in v if isinstance(i, int)) for v in by_iter.values()]
    ok = bool(per_iter) and all(g and g == list(range(len(g))) for g in per_iter)
    return ok, f"eval ids set up with integer ids: {sorted(i for i in ids if i is not None)} (proxy: a gap-free id prefix starting at 0; build order is not recoverable from a finished workspace)"


def c_pilot_explained(d, run_dir=None, **k):
    t = read(Path(run_dir) / "outputs/notes.md").lower() if run_dir else ""
    ok = "pilot" in t
    return ok, "notes.md mentions the pilot (word check only)" if ok else "notes.md missing or does not mention the pilot"

REGISTRY = {name[2:]: fn for name, fn in globals().items() if name.startswith("c_")}

CHECK_SETS = {
    "r5-large": [
        ("SKILL.md frontmatter passes quick_validate", "quick_validate", {}),
        ("Structure complete (portability lint: no mandatory gaps)", "mandatory_files", {}),
        ("HISTORY attribution lint has no blocking violation (author-identity-mismatch ignored: fictional persona)", "attribution", {}),
        ("SKILL.md is 500 lines or fewer despite 529 lines of rules", "skill_under_500", {}),
        ("All 48 rules are present somewhere in the skill", "rules_complete", {}),
        ("Each rule is written exactly once across the skill", "rules_once", {}),
        ("Every rule's rationale is kept verbatim", "rules_verbatim", {}),
        ("Every cited reference file exists", "cited_refs_exist", {}),
        ("No SKILL.md line is over 1000 characters", "no_long_lines", {}),
        ("SKILL.md has Known limitations, Examples and Troubleshooting sections", "standard_sections", {}),
        ("The eval workspace holds integer ids from 0 with none skipped (proxy: build order is not recoverable)", "four_ready", {}),
        ("notes.md mentions running eval 0 first as a pilot (word check only)", "pilot_explained", {}),
        ("A deterministic step ships as a script with a stated input-to-output contract", "script_contract", {}),
    ],
    "r4-loop": [
        ("SKILL.md frontmatter passes quick_validate (seeded: stray version key)", "quick_validate", {}),
        ("Structure complete (portability lint: no mandatory gaps)", "mandatory_files", {}),
        ("HISTORY attribution lint has no blocking violation (author-identity-mismatch ignored: fictional persona)", "attribution", {}),
        ("Description names trigger contexts (seeded: vague description)", "description_triggers", {}),
        ("Every cited reference file exists (seeded: style-rules.md missing)", "cited_refs_exist", {}),
        ("No absolute home path remains (seeded: /Users/jo/...)", "no_home_paths", {}),
        ("README has an Intent section (seeded: absent)", "readme_has_intent", {}),
        ("count_words.py counts the sample file correctly (seeded: double-space bug)", "count_correct", {}),
        ("count_words.py returns 0 for an empty file (hidden second bug)", "count_empty", {}),
        ("No TODO/TBD/placeholder text was introduced by the fixes", "no_placeholders", {}),
        ("SKILL.md has Known limitations, Examples and Troubleshooting sections", "standard_sections", {}),
        ("outputs/ledger.json is a valid ledger with 2 to 3 rounds that stops", "ledger_valid", {}),
        ("outputs/final.md states why the loop stopped", "final_stop_reason", {}),
    ],
    "r3-personal": [
        ("SKILL.md frontmatter passes quick_validate", "quick_validate", {}),
        ("Structure complete (portability lint: no mandatory gaps)", "mandatory_files", {}),
        ("HISTORY attribution lint has no blocking violation (author-identity-mismatch ignored: fictional persona)", "attribution", {}),
        ("The persona's name and folders appear nowhere in the skill", "no_persona", {}),
        ("No absolute home-directory path appears in the skill (tests excepted)", "no_home_paths", {}),
        ("The input folder comes from an argument, config or environment", "configurable_input", {}),
        ("The run log path is configurable and the log has an off switch", "logging_off_switch", {}),
        ("No fixed /tmp path", "no_fixed_tmp", {}),
        ("A test file exists and passes", "tests_pass", {}),
        ("Opus is not named anywhere; helpers stay on Sonnet", "no_opus", {}),
        ("deviations.md explains declining the hard-coded path and the Opus request", "deviations_logged", {}),
        ("Tier is claude-users", "tier_claude_users", {}),
    ],
    "r2-fork": [
        ("SKILL.md frontmatter passes quick_validate", "quick_validate", {}),
        ("Structure complete (portability lint: no mandatory gaps)", "mandatory_files", {}),
        ("HISTORY attribution lint has no blocking violation (author-identity-mismatch ignored: fictional persona)", "attribution", {}),
        ("Attribution category is A (direct fork)", "fork_category_a", {}),
        ("The original Apache-2.0 LICENSE is preserved in the fork", "fork_license_kept", {}),
        ("The history chain names the original, its source URL and licence", "fork_chain", {}),
        ("The changes made to the original are stated", "fork_changes_stated", {}),
    ],
    "r2-adapt": [
        ("SKILL.md frontmatter passes quick_validate", "quick_validate", {}),
        ("Structure complete (portability lint: no mandatory gaps)", "mandatory_files", {}),
        ("HISTORY attribution lint has no blocking violation (author-identity-mismatch ignored: fictional persona)", "attribution", {}),
        ("Attribution category is B, C or A (not D) because parts were taken", "adapt_category", {}),
        ("HISTORY records the Apache-2.0 candidate: name, licence and source URL", "adapt_history_source", {}),
        ("Any text taken from the Apache-2.0 candidate carries attribution in HISTORY", "adapt_apache_attributed_if_copied", {}),
        ("HISTORY lineage says which idea was taken from the Apache-2.0 candidate", "adapt_lineage_what_taken", {}),
        ("No 8-word run copied from the candidate with an unknown licence", "adapt_no_copy_unknown_licence", {}),
        ("The unknown licence is raised as a question in outputs/questions.md", "adapt_question_logged", {}),
        ("Nothing from the red-flagged candidate: no copied text, no collector URL", "adapt_no_copy_redflag", {}),
        ("The red-flagged candidate is not recorded as a source", "adapt_not_credited_redflag", {}),
    ],
    "r1-build": [
        ("SKILL.md frontmatter passes quick_validate", "quick_validate", {}),
        ("README, HISTORY, glossary and required dirs exist (portability lint: no mandatory gaps)", "mandatory_files", {}),
        ("HISTORY attribution lint has no blocking violation (author-identity-mismatch ignored: fictional persona)", "attribution", {}),
        ("A deterministic step ships as a script under scripts/", "script_exists", {}),
        ("The script states an input-to-output contract", "script_contract", {}),
        ("evals/evals.json has at least 2 evals with integer ids and expectations", "evals_json", {}),
        ("Tier is claude-users (the default)", "tier_claude_users", {}),
        ("SKILL.md is 500 lines or fewer", "skill_under_500", {}),
        ("No persona string appears anywhere in the skill", "no_persona", {}),
        ("README ## Intent states the optimise/trade-off answer", "readme_intent", {}),
        ("HISTORY.md records the marketplace check", "checked_marketplace", {}),
        ("SKILL.md has Known limitations, Examples and Troubleshooting sections", "standard_sections", {}),
        ("Description names trigger contexts", "description_triggers", {}),
    ],
}


def grade(check_set, skill_dir, persona=(), intent_words=(), fixtures=None, run_dir=None):
    exps = []
    for text, key, extra in CHECK_SETS[check_set]:
        try:
            ok, ev = REGISTRY[key](skill_dir, persona=persona, intent_words=intent_words, fixtures=fixtures, run_dir=run_dir, **extra)
        except Exception as exc:  # a crashing check is a failing check, with the reason
            ok, ev = False, f"check crashed: {exc}"
        exps.append({"text": text, "passed": bool(ok), "evidence": ev})
    p = sum(e["passed"] for e in exps)
    return {"summary": {"passed": p, "failed": len(exps) - p, "total": len(exps), "pass_rate": round(p / len(exps), 3)},
            "expectations": exps}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-set", required=True)
    ap.add_argument("--skill-dir", required=True)
    ap.add_argument("--run-dir")
    ap.add_argument("--persona", action="append", default=[])
    ap.add_argument("--intent-word", action="append", default=[])
    ap.add_argument("--fixtures")
    a = ap.parse_args(argv)
    if not Path(a.skill_dir).is_dir():
        exps = [{"text": x[0], "passed": False, "evidence": f"no skill directory at {a.skill_dir}"} for x in CHECK_SETS[a.check_set]]
        res = {"summary": {"passed": 0, "failed": len(exps), "total": len(exps), "pass_rate": 0.0}, "expectations": exps}
    else:
        res = grade(a.check_set, a.skill_dir, a.persona, a.intent_word, a.fixtures, a.run_dir)
    if a.run_dir:
        (Path(a.run_dir) / "grading.json").write_text(json.dumps(res, indent=2) + "\n")
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
