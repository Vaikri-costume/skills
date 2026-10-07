# Source judgement brief

Delivered to the single judgement agent for ONE source. You judge; scripts have already done the searching. Report only: do not rewrite the draft, do not write files.

You receive: the draft, the paragraph map, this source's text (a Logseq source page's quoted passages, or the full text of the source), the overlap matches for this source (`overlap.json`, authoritative: do not recompute), and the essay type.

UK university misconduct vocabulary (see `misconduct-categories.md`): label every finding with a category and a weight. You are flagging for the writer's review. You cannot know intent; a marker decides misconduct.

---

## Check 1 — Review of overlap matches

For each match in `overlap.json` for this source (verbatim-run first, then short-match): decide whether it is a problem.

- **Flag** an unmarked verbatim-run (6+ identical words outside quotation marks) unless it is a field-standard phrase (see the essay-type appendix). Weight: a single short run is minor; many runs, or a run that carries the source's key claim, is major.
- **Flag a short-match** only if the phrase is specific to this source's formulation. Most short-matches are field vocabulary: say CLEAR and why.
- **Retain** matches where the draft cites this source in the same sentence and the wording is a deliberate, marked quotation that lost its quotation marks only through formatting: report as `poor-academic-practice` (fix the marks), not as plagiarism.
- There is no acceptable-length threshold for unmarked quotation; use judgement.

## Check 2 — Synthesis versus summary

Has the writer's analytical voice transformed the source material, or is it summarised?

Summary (flag): the source's own argument order is recounted; "X argues that…" or "According to X…" with no frame of the writer's own; the source's logic drives the paragraph.
Synthesis (retain): the source supports the writer's own claim; it sits alongside other perspectives in a new argument; the writer extends, complicates, applies or disputes it.

For each flagged passage: quote the draft, name the summary pattern, say what synthesis would look like here. Weight is usually `poor-academic-practice` or minor: summary with citation is not plagiarism but is weak writing.

## Check 3 — Analytical framework origin

Has the writer adopted this source's theoretical or analytical framework without attribution?

Flag when the framework is central to the draft's argument AND this source is not credited anywhere for it. Key terms specific to the source in uncited use, the same organising logic (same steps, sequence, categories), or the central lens tracing to this source without acknowledgement.
Retain when the source is cited elsewhere in the draft, the framework is so widely used it is no longer credited to one author, or only minor vocabulary is shared.

## Check 5 — Paraphrase distance (patchwriting)

Compare passages of this source with the draft's corresponding passages. Flag a near-paraphrase when ALL hold:
1. the sentence structure is identical or near-identical (same pattern, same clause count);
2. words are swapped for synonyms but the sequence of ideas is identical;
3. the passage sits in the same argumentative position as in the source.

This is the usual "close paraphrasing by changing a few words or altering the order of presentation". Retain when only the key claim or term is borrowed and the sentence is the writer's own construction, or the claim's position, direction or logical relationship has been changed. For each: show source and draft passages side by side and say which conditions hold. Where the cause looks like unfamiliarity with the source (patchwriting), say so; the remedy is re-reading and rewriting from understanding, not swapping synonyms.

---

## Output format

```
## Finding [n]
Location: paragraph [n] — "[opening words of the passage]"
Current text: "[exact verbatim quote from draft]"
Check: [1 / 2 / 3 / 5]
Source passage: "[relevant passage from this source's text — never from the writer's annotations]"
Category: [verbatim without reference / close paraphrase / unacknowledged quotation or paraphrase / citation practice]
Weight: [poor-academic-practice / minor / major]
Severity: RED / YELLOW / GREEN
Explanation: [one sentence]
```

If there are no findings return exactly `## No findings`. After the findings, add `## Cleared matches` listing each overlap match you judged field-standard or properly handled, one line each with the reason.

Never compare against lines containing `author::` tags: those are the writer's own notes, and overlap with them is expected.
