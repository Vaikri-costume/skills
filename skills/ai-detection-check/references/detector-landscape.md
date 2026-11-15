# Detector landscape (dated; for context only, never a source of numbers in a report)

**Last reviewed: 2026-11-12.** Refresh when the writer or the maintainer asks, and at least when an institution's policy or a major detector changes. This file explains why the skill is a descriptive review and not a detector. A report never quotes a vendor figure from here as fact about the writer's draft.

## How the evidence is labelled

*Independent* = authors with no stake in the detector. *Vendor* = produced by the company selling the detector. *Not verified* = seen only in a summary or not reachable. Treat vendor figures as claims.

## What stays true (slow to change)

- **No detector proves authorship.** Every independent study finds non-zero false positives, and every one finds that edited, paraphrased or "humanised" machine text lowers detection. Vendors themselves say a score is not sole evidence.
- **Mechanisms.** Perplexity and burstiness (machine text is more predictable and even); supervised classifiers trained on human versus machine text; watermarking (only text from a cooperating model, broken by paraphrase and translation); process evidence (drafts, version history, source trail), which does not depend on a classifier; human judgement.
- **Plain, formulaic and second-language prose has low perplexity**, which is why it is flagged more often. A 2023 study of seven detectors found high false-positive rates on second-language essays (Liang et al.); no independent 2025 or 2026 replication for second-language student writing was found, which is a gap, not a clean bill of health.
- **Public benchmarks over-report accuracy** (RAID authors), and vendor test sets, thresholds and false-positive targets differ, so vendor figures are not comparable.

## What goes stale fastest (check before relying on it)

- Vendor false-positive and accuracy claims (for example under 1% per document, or one in 10,000), minimum word counts, supported languages, the categories a tool reports (for example "AI-paraphrased"), and which tools are retired or renamed.
- Institutional policy: whether a university runs a detector, and whether a score alone may ground a misconduct process. In the UK sector in 2026, complaint bodies and commentary have pressed that a score cannot be the sole basis; some universities abroad have switched detection off. Confirm the writer's own institution from their rules file, never from here.
- Independent studies on the newest detectors: samples are small (hundreds to a few thousand documents), mostly English, mostly no student scripts.

## Independent sources read for the 2026-11-12 review

Weber-Wulff et al. 2023 (14 tools, "neither accurate nor reliable"); Liang et al. 2023 (second-language bias); Sadasivan et al. 2023 and Dugan et al. (RAID) 2024 (paraphrase and adversarial attacks); Russell, Karpinska and Iyyer 2025 (expert readers versus detectors); Jabarian and Imas 2025 (newer detectors at tuned thresholds); Han et al. 2025 (watermark robustness); Epoch AI 2026 (false negatives). Search the titles above to find each one; figures are left out here on purpose.

## Refresh plan

Re-read vendor pages and the independent studies above; update the dates and the "goes stale fastest" list; record the review date at the top. Do not add a vendor claim unless it is labelled as a claim.
