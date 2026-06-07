# Security Checks (skill-publisher — tier-transition phase)

> **How this runs (skill-publisher, the tier-transition checks phase):** the security check runs once at ship time on the final shippable state, as an **orchestrator-side checklist the publisher walks** — NOT a cold-parallel dispatched agent. Two phases: (1) the deterministic pre-pass `scripts/security_scan.py` catches the grep-able categories (1 creds, 3 unsafe-deser, 7 crypto, 8 path-traversal, 13 telemetry, 14 deprecated APIs) and emits `SEC-*` candidates; (2) the orchestrator then walks the judgment categories below by adversarial reading. Each confirmed finding becomes a `SEC*` flag in a TIER-phase ledger cluster, addressed per `ship-checklist.md` (FIX/STRENGTHEN/USER-PAUSE). (Lineage: this was skill-tracer's `security.md` cadenced direction; it moved here when the tracer slimmed to correctness-only.)

The security check reads SKILL.md (and every supporting file in scope) hunting for security-relevant defects — the orchestrator inspects each instruction, script, brief, and example for patterns that introduce or amplify risk when the skill executes.

The guiding question: *"If an attacker controlled an input to this skill, or read its outputs, what would they gain?"* Read each instruction with that adversarial intent and record a `SEC*` cluster for anything that creates risk — regardless of which category it most closely fits.

---

## What counts as a security finding

A line, script, brief, or example is a finding when one of the following is true. Each item below is a complete category — these are the most frequent security failures, not the exhaustive set. See "Findings outside the categories above" (below) for the open extension point. The `security_scan.py` pre-pass auto-surfaces the grep-able ones (cats 1, 3, 7, 8, 13, 14) as candidates; the orchestrator confirms those and reads for the judgment categories (2, 4, 5, 6, 9, 10, 11, 12) itself. The two-phase procedure covers categories 1–14; category 15 (frontmatter prompt-injection) is also checked by the frontmatter-validity gate via `portability_lint.py`.

**1. Hardcoded credentials, tokens, keys, or secrets.** Any literal API key, password, token, SSH key, OAuth secret, signing key, or environment-specific identifier present in SKILL.md, a script, a brief, or a reference file. This includes placeholder-looking values that are actually real (`AKIA...` AWS keys, `ghp_...` GitHub tokens, JWTs). Even partial credentials (one half of an OAuth flow) are a leak. Quote the exact occurrence with file path and line number.

**2. Injection vectors.** Any place the skill constructs a shell command, SQL query, prompt, URL, or other interpreter-input by string-concatenating user-supplied or externally-supplied values. Examples: `bash -c f"... {user_input} ..."`, an SQL query built with f-strings, a URL with un-encoded query parameters, a sub-agent prompt that inlines user-supplied text without escaping. Quote the construction site and identify the unsanitized source.

**3. Unsafe deserialization.** Any use of `pickle.loads`, `yaml.load` (vs `yaml.safe_load`), `eval`/`exec` on parsed data, `json.loads` of untrusted data into structured types without validation, or equivalent in scripts. Quote the deserialization call and the data source.

**4. Missing or weak authentication / authorization.** A skill action that reads sensitive data, modifies external state, or invokes a privileged operation without first verifying the caller's identity or permission. Examples: a script that writes to `~/.ssh/`, a skill that calls a paid API, a skill that modifies `/etc/`. Quote the action and the absence of any guard.

**5. Sensitive data in logs, prompts, or outputs.** Any place a script or skill instruction writes a credential, PII, internal-only identifier, or other sensitive value to stdout, stderr, a log file, an agent prompt, or a user-facing message — when the value originated from a context where it was protected. Examples: `print(f"Connecting with {api_key}")`, a brief that inlines the user's email when the brief is logged. Quote both the source and the disclosure site.

**6. Broken access control patterns.** A skill that grants the executor or a dispatched agent broader file/system access than the task requires. Examples: `allowed-tools` includes `Bash` when the skill only needs `Read`; an agent dispatch gives the sub-agent full Bash when its job is read-only. Quote the over-permissive grant and the actual narrower need.

**7. Insecure cryptographic choices.** Use of MD5/SHA1 for security purposes (vs hashing for content addressing), DES/3DES, custom crypto schemes, hardcoded IVs, ECB mode, predictable nonces, or `random` (vs `secrets`) for security tokens. Quote the cryptographic call and the security-purpose use.

**8. Path traversal.** Any place the skill constructs a filesystem path from external input without normalizing or restricting to a base directory. `Path(user_input)` without an `is_relative_to` or `resolve().startswith(base)` check is a flag. Quote the path construction and the input source.

**9. Server-Side Request Forgery (SSRF) / unconstrained outbound requests.** A skill that fetches URLs from external input without an allow-list (e.g., a script that takes a user-supplied URL and fetches it). Quote the request site and the URL source.

**10. Time-of-check / time-of-use (TOCTOU) races.** A skill that checks a resource state, then acts on the resource, without holding a lock or using the atomic check-and-act primitive. Examples: `if not os.path.exists(p): open(p, 'w')` (race), `if file.mtime < threshold: file.unlink()` (race). Quote the check site and the action site.

**11. Information leakage via error messages or timing.** A skill that returns different error messages (or noticeably different latencies) depending on whether a secret value matched. Allows an adversary to enumerate. Quote the branching code and the secret comparison.

**12. Cross-agent / cross-skill trust violations.** A skill that dispatches a sub-agent or invokes another skill while passing along its own credentials, session tokens, or privileged context unnecessarily. The sub-skill receives more privilege than the task warrants. Quote the dispatch construction and the privilege passed.

**13. Default-on telemetry, logging, or external reporting.** A skill that, by default, sends usage data, error reports, or analytics to an external endpoint without explicit user opt-in. Quote the reporting code and the absence of an opt-in check.

**14. Outdated dependency calls or deprecated security APIs.** A script using a library function the library's docs flag as deprecated-for-security. Examples: Python's `cgi.escape` (deprecated for `html.escape`), Node's `crypto.createCipher` (deprecated for `createCipheriv`). Quote the call site.

**15. Frontmatter prompt-injection surface.** XML-tag-shaped content (`<tag>…</tag>`, `<instructions>`, or any `<word…>` pattern) anywhere in the SKILL.md YAML frontmatter. **Why this is security, not style:** the frontmatter is injected verbatim into Claude's system prompt to drive triggering — so a literal tag in a frontmatter value is an instruction-injection vector (a description reading `…use this <system>ignore prior rules</system>` would land in the system prompt). The frontmatter-validity gate (the blocking frontmatter gate that opens the tier-transition checks) flags `frontmatter-angle-bracket` via `portability_lint.py`; this category is the security framing of the same finding and why it blocks. Version operators (`>=2.0`, `<3.0`) are not tags and are fine; reserved-name prefixes (`claude`/`anthropic`) are a separate registration check, not this one. Quote the frontmatter field and the tag-shaped value.

These categories overlap at the edges. When a single failure could be flagged under two categories, choose the one whose description most directly matches and tag accordingly. Do not file twice.

---

## Findings outside the categories above

The categories above describe the most frequent security failures, not the complete set. While reading the skill adversarially, if the orchestrator notices anything else that creates risk — a discrepancy, a missing check, a subtle privilege escalation, an unexpected trust assumption, a structural problem that does not match any category above — record it with the same discipline.

Use a kebab-case sub-tag that names the failure precisely (e.g. `SEC-insufficient-randomness`, `SEC-secrets-in-git-history`, `SEC-unencrypted-storage`, or whatever fits). The bar is unchanged: exact-quote evidence (file + line), no hedging, no qualifying, no grading.

Do not invent findings to fill the ledger. If nothing outside the categories surfaces, the TIER-phase clusters contain only the categorised findings.

---

## Worked example — what a `SEC*` cluster looks like

A confirmed security finding becomes a `SEC*` cluster in the TIER-phase ledger, with exact-quote evidence and an Address (per `ship-checklist.md`). Shape of the finding the orchestrator records:

```
SEC-injection-vector: SKILL.md Step 4 instructs the orchestrator to invoke a shell command containing a user-supplied value without quoting or escaping. A value like `; rm -rf /` would execute as a separate command.
File: <target-skill>/SKILL.md (the dispatch/shell-invocation site — this is an illustrative example; pin to the actual finding location when recording a real cluster)
Evidence: "Run `bash -c \"find ~/.claude/skills/$SKILL_NAME -name SKILL.md\"` to locate the target skill's manifest."
Why it's a risk: $SKILL_NAME is sourced from the user's natural-language invocation with no quoting, no character allowlist, no validation. A name containing shell metacharacters injects into the bash -c command.
→ Address: FIX (<target-skill>/SKILL.md: quote and allowlist-validate $SKILL_NAME before interpolation)
```

The orchestrator writes the cluster to the ledger with `scripts/append_ledger.py` (Phase `TIER`, Cluster `SEC-injection-vector`, Address as above) — it rejects a literal `|` or embedded newline that would corrupt the row.
