# Recommendations.md Template

Template for the per-iteration `recommendations.md` payload that the orchestrator authors before invoking the eval viewer. The viewer renders this as a sidebar alongside the raw eval data.

Required structure — three sections, in order:

```markdown
## What this iteration did well
- <observation 1>
- <observation 2>
- <observation 3 if applicable>
- <... more as you observe them>

## What this iteration failed at
- <observation 1 — tie to a specific failed assertion or feedback comment>
- <observation 2 — tie to a specific failed assertion or feedback comment>
- <observation 3 — tie to a specific failed assertion or feedback comment>
- <... more as you observe them>

## Recommended next iteration
- <concrete edit 1>
- <concrete edit 2>
- <concrete edit 3>
- <concrete edit 4 if applicable>
- <... more as you have them>
```

## Bullet-count rules

Bullet counts are **minimums, not maximums**:

- At least 2 observations in "did well"
- At least 2 observations in "failed at"
- At least 3 concrete recommendations in "Recommended next iteration"

**More is better.** Every additional observation or recommendation here saves an iteration cycle later. If you noticed something, write it down even if it feels minor — the user can dismiss it in seconds, but a missing observation means a future iteration spent re-discovering it. The viewer scales to fit.

## Why this exists

This payload is what differentiates a CCVW review from a raw eval dump. The user gets one click to see the orchestrator's full analysis — what worked, what didn't, and concrete next steps — rather than having to derive it themselves from the test outputs.
