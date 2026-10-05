# Authenticity evidence and policy context

Read by the presentation agent for the "Citation and quotation integrity" and "Evidence you can show" sections, and by anyone writing the report header. Review this file when SOAS or Jisc guidance changes; items are dated.

## Why the report is framed as it is

- Independent tests find AI-text detectors unreliable: 14 tools all under 80% accuracy in one 2023 study (Weber-Wulff et al.); 39.5% baseline accuracy falling to 17.4% on text modified to evade (Perkins et al. 2024); easily fooled on 6 million generations (RAID, ACL 2024).
- They misclassify formal, constrained and second-language writing: Liang et al. 2023 (non-native English essays); Karr et al. 2026 (unmodified human abstracts flagged 9–15%, more in non-STEM fields, tracking long-token and Academic Word List density; honest light AI editing flagged 38–80%, while after a humaniser under 4% stayed flagged).
- A text-only detector with useful power must falsely accuse writers whose style overlaps AI output (Garland 2026). Educators also fare badly: 38% correct in one cited study.
- UK HE: Jisc says no detector can prove AI authorship conclusively; its 2025 update says the sector mood has shifted decisively away from automated detection toward assessment redesign. A July 2026 HEPI piece reports universities still lean on detector scores and argues they should not be sole grounds.
- Turnitin's own guidance: document false-positive rate under 1% at 20%+ AI writing, about 4% per sentence, "no right or target score", highlights are "areas of interest".
- SOAS (REG-183-10 v10, effective 1 Sep 2026): §2.1(j) and §2.8 treat AI use to an extent that work may not be the student's own, without approval, as misconduct, and list human-judgement indicators below. §2.9 describes the inquiry: compare with the student's other work, a colleague's second view, an informal non-adversarial meeting where the student brings notes, drafts and readings. The sections read do not name an AI-detection score as evidence. Whether SOAS switches on the Turnitin AI indicator is unconfirmed.


## SOAS §2.8 indicators the skill can check by machine

| Indicator (SOAS wording, paraphrased) | Check |
|---|---|
| quotations that do not exist or are not in the cited source | `quote_verify.py` |
| extensive bibliography not cited in the text | `citation_audit.py` → `uncited_bibliography` |
| significant repetition: authors introduced repeatedly, repeated bibliography entries | `citation_audit.py` → `author_reintroductions`, `duplicate_bibliography` |
| context of quotations and sources cannot be verified | `quote_verify.py` → `no-source-supplied` |
| vagueness on topics covered in class; not answering the question | human judgement; the skill cannot check |

Machine-written references also carry artefacts: `utm_` parameters, invalid ISBN checksums, malformed DOIs, placeholder markers (Wikipedia "Signs of AI writing"). These are reported under `artefacts`.

## Evidence you can show (checklist for the report footer)

Offer, never require: dated drafts or version history; reading notes and annotations; the reading list with what was actually read; notes on why the topic was chosen; a record of any AI use and what for (SOAS: students must not use generative AI to produce assignments; permitted study uses should be disclosed per the module's rules). Keeping these is good practice whatever any tool says.

## Rules for the report

1. Never present a metric, pattern or smoothness flag as evidence of machine authorship.
2. Never advise how to lower a score or avoid detection. If asked, say the check exists to find places where specific thinking may be missing, and that honest AI assistance should be declared, not disguised.
3. State when the writer's profile (formal academic register, second-language writing) raises false-positive risk. Never infer the writer's background.
4. Say what is unknown: whether the institution runs a detector, and what it would report.
