# Severity anchors

Use these to set `Severity:` so that High, Medium and Low mean the same thing across agents and runs. They are descriptive anchors, not numeric grades: LLM reviewers show position, verbosity and phrasing biases, and rubric prompts alone do not make scores reliable. Where unsure between two levels, pick the lower and add "— uncertain".

| Severity | Meaning | Examples |
|---|---|---|
| High | A reader would misread, doubt or reject the argument or the passage because of it | central claim missing or only a topic; a warrant absent at a pivotal move; a key claim with no grounds; a pronoun whose referent changes the meaning |
| Medium | A careful reader notices and the point is weakened, but follows | an implicit warrant that could be one sentence; evidence cited but not shown; a quotation left floating; a long interruption between subject and verb |
| Low | Polish: a better version exists, but nothing is lost | a passive that hides a minor actor; a sentence ending on an afterthought; a compound sentence that could split |

Do not raise severity because a finding is interesting, or lower it to be kind. Strengths are never scored.
