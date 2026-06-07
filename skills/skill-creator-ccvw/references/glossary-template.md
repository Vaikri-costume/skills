# Glossary — <SKILL-NAME>

See also: [`~/.claude/skills/skill-creator-ccvw/references/ccvw-glossary.md`](../../skill-creator-ccvw/references/ccvw-glossary.md) for all CCVW shared terms (cluster, FIX, STRENGTHEN, in-flight marker, Round, Phase, ledger, cold-trace, tier, etc.). Do NOT redefine those terms here — they live in the shared glossary as the single source of truth. This file lists ONLY skill-specific terms.

## How to use this template

1. Replace `<SKILL-NAME>` in the heading with your skill's name.
2. Add one row per skill-specific term — backticked nouns from your SKILL.md, ALL-CAPS state words, tracking-field shorthands, role names, mode names, named protocols, status strings, custom file roles.
3. Keep definitions to ONE line each. Cross-reference the shared glossary for any term that's already CCVW-vocabulary.
4. Alphabetize by term.
5. When skill-tracer runs on this skill, Step 3's [GLOSSARY] derivation reads this file FIRST. Definitions here go into the trace agents' prompts verbatim, so the trace agents understand your skill's vocabulary without re-derivation.

## Skill-specific terms

| Term | Definition |
|---|---|
| `<example-term>` | <one-line definition; no period at end> |

## When to update this glossary

- After every skill-tracer convergence, any new terms the trace agents had to derive cold get written back here after a tracer convergence. Review them after each trace.
- When you add new functionality to the skill that introduces new vocabulary, add the term here BEFORE the next trace runs — otherwise skill-tracer derives it cold and your definition may differ from the orchestrator's.
- When you rename a term in SKILL.md, update the term here in the same edit pass (or the next trace will flag the drift).
