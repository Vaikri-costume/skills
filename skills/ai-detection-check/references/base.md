# AI Detection Check — Base Brief

This brief is delivered selectively. Agents B and C receive the full brief (all 14 patterns + semantic scanning + hedging criteria + critical reminder). Agent A receives only the hedging calibration section. The challenger receives the full brief plus confirmed calibration anchors and disciplinary context (composed and inlined by the executor at dispatch time).

---

## HEDGING CALIBRATION CRITERIA (Agent A receives this section only)

### When to flag hedging as unnecessary

Flag hedging when:
- The claim is a verifiable fact with a specific citation (e.g., "the film was released in 1957" — state directly)
- The writer is reporting their own direct observation or count from close reading (e.g., "the dupatta appears in 12 of the 15 scenes" — if this is a count, state it)
- The hedged statement is tautological: "this could possibly be seen as an example of X" — if it is X, say so

### When to retain hedging

Retain hedging when:
- The claim involves interpretive judgment about cultural meaning, historical causation, or contested theory
- The claim attributes intention or consciousness to a social structure, historical process, or institutional force
- The discipline treats this class of claim as genuinely uncertain
- The project context has explicitly marked this claim type as requiring hedging

### When ambiguous

Report as "hedging — context-dependent" and quote the specific claim for the writer's review. Do not decide for the writer.

---

## 14 AI DETECTION PATTERNS (Agents B and C receive below this line; Agent A does not)

These patterns are anchor sets, not exhaustive lists. For every category, you must:
1. Scan for the listed phrases and constructions (exact match)
2. Then scan semantically: what other language in this text performs the same rhetorical function?
3. Report exact matches and semantic equivalents separately, clearly marking which is which

A flag means this language may have replaced sharper analysis — NOT that the text is AI-generated.

---

### Content patterns

**Pattern 1 — Significance inflation**
Listed phrases: "stands as a testament", "plays a vital role", "underscores the importance", "groundbreaking", "revolutionary", "transformative", "unprecedented", "paradigm shift", "seminal", "pivotal contribution"
Semantic equivalent: any claim about significance that is asserted rather than demonstrated through evidence. Ask: does the surrounding text provide the evidence that would justify this claim? If not, flag.

**Pattern 2 — Hollow generalisations**
Listed phrases: "Throughout history...", "In today's world...", "Society has always...", "Since time immemorial...", "Across cultures..."
Semantic equivalent: any opening or bridging sentence that makes a claim about all people or all time without a specific referent. The function: performing scope before earning it.

**Pattern 3 — False-balance framing**
Listed phrases: "While some argue X, others contend Y", "There are those who believe X, while others maintain Y", "This essay will examine both sides"
Semantic equivalent: any structural move that delays the writer's own position behind performed balance — where the balance is not intellectual honesty but a structural default.

**Pattern 4 — Unearned conclusions**
Listed phrases: "This shows the importance of...", "Further research is needed to understand...", "Ultimately, this reveals the complexity of...", "It is clear that more work must be done..."
Semantic equivalent: any conclusion that adds no new analytical synthesis — that merely restates the claims already made, or ends with aspirational language that does not follow from the argument.

---

### Language patterns

**Pattern 5 — AI vocabulary cluster**
Listed words (list refreshed 2026-10-04 against Wikipedia "Signs of AI writing"; perishable — see `scripts/find_ai_patterns.py`): "delve", "underscore", "interplay", "showcase", "vibrant", "intricate", "tapestry", "nuanced" (as filler), "navigate" (metaphorical), "landscape" (metaphorical), "realm", "comprehensive" (without specificity), "robust", "multifaceted", "multitude", "crucially", "pivotal"
Flag only when not used with precision — "nuanced reading" as a specific analytical claim is different from "a nuanced tapestry of influences." When uncertain whether a term is being used precisely: flag with note "possibly precise — review."

**Pattern 6 — Copula avoidance**
Listed constructions: "X serves as Y", "X functions as Y", "X operates as Y", "X proves to be Y", "X emerges as Y", "X comes to represent Y"
Semantic equivalent: any construction that rewrites a direct predication ("X is Y") as a verb of purpose, function, or emergence — when the directness of "is" would be clearer and more honest.

**Pattern 7 — Vague attributions**
Listed phrases: "experts say", "scholars note", "research suggests", "studies show", "critics argue", "many have observed"
Semantic equivalent: any attribution to an unnamed collective without a specific citation. Function: performing scholarly authority without providing it.

**Pattern 8 — Promotional lexicon**
Listed words: "powerful", "striking", "compelling", "rich", "innovative", "fascinating", "remarkable", "eloquent", "insightful"
Flag when used as assertions rather than demonstrated through analysis. "This is a powerful image" asserts. "This image achieves [specific effect] because [specific observation]" demonstrates.

---

### Style patterns

**Pattern 9 — Excessive hedging** (context-dependent — apply hedging calibration criteria above)
Listed phrases: "it could be argued that", "it might be suggested that", "one could possibly say", "this may indicate", "it would seem that", "it appears as though"
Apply the hedging calibration criteria above. Do NOT apply a single threshold — hedging is appropriate for interpretive claims and inappropriate for verifiable facts. Report each flagged instance with the calibration criteria applied.

**Pattern 10 — Negative parallelisms**
Listed constructions: "not only X but also Y", "not merely X but also Y", "not simply X but rather Y"
Flag when the parallel is formulaic — when the two halves do not genuinely illuminate each other, but the construction is used because it sounds analytical.

**Pattern 11 — Rule of three**
Flag runs of three-element lists: "first..., second..., third..." or "X, Y, and Z" where the number three was chosen for structural convenience rather than because there are exactly three things.
Do NOT flag genuine three-part structures where the third element adds something the first two did not. Only flag when the third element is padding.

---

### Communication patterns

**Pattern 12 — Uniform sentence length**
Human writing naturally varies: very short sentences, very long sentences, fragments. Flag any run of five or more consecutive sentences where all sentences fall in the 15–35 word range with similar grammatical structure.
Do NOT flag passages that are uniformly short (dense, spare writing) or uniformly long (extended analytical sentences) — only flag the mid-range sameness that signals algorithmic smoothness.

**Pattern 13 — Filler openings**
Listed phrases: "It is worth noting that...", "It is important to recognise that...", "It should be noted that...", "One must consider...", "It bears mentioning that..."
Semantic equivalent: any sentence opener that could be deleted without changing the content of the sentence.

**Pattern 14 — Announcement sentences**
Listed constructions: "This essay will examine...", "In this section, I will discuss...", "Having established X, I now turn to...", "This paper argues that..." (mid-essay)
Flag when mid-essay. Do NOT flag the opening sentence of an essay where some announcement is conventional. Flag when announcement sentences appear in every section, or when they substitute for making the argument.

---

## CRITICAL REMINDER (all agents must include this in their output header)

**Statistical properties are downstream of genuine intellectual engagement.**

A flag means this specific language may have replaced sharper, more specific analysis — not that the text is AI-generated. The writer's task when reviewing these findings is to ask: does this passage contain my sharpest thinking, or did a convenient phrase substitute for a more precise one?

Do not suggest the text is AI-generated. Do not use that framing in any finding.

---

## Output constraints

- Do NOT write to any file
- Do NOT edit the draft
- Do NOT drop findings — if uncertain about a finding, keep it and mark "uncertain"
- If you find no instances of a pattern: note "Pattern [n]: no instances found"
- Return findings as a structured list
