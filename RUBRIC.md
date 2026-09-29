# Scoring rubric

Used identically by `/nachhilfe-writing` and `/nachhilfe-grammar` (free-text
answers), so a "7/10" means the same thing in September as it does a year
later regardless of how much history has accumulated. The learner's CEFR
level changes what's *expected* in the task and the text, not this rubric.

## Writing / grammar free-text answers — score out of 10

| Criterion | Points | What to check |
|---|---|---|
| Task fulfillment | 0–3 | Addresses what was asked, appropriate length, appropriate register (formal/informal) for the task |
| Grammatical accuracy | 0–3 | Correct use of level-appropriate structures; count real errors, not stylistic preference |
| Vocabulary range & appropriateness | 0–2 | Varied, level-appropriate word choice; not just repeating the prompt's words |
| Coherence & cohesion | 0–2 | Logical structure, appropriate connectors, easy to follow |

Sum the four sub-scores for the final score out of 10. Always show the
sub-scores, not just the total, so the learner sees *why*.

## Reading comprehension — score as % correct

Grade each question right/wrong (partial credit only for genuinely
multi-part questions, in which case count sub-parts). Compute the
percentage as `correct / total * 100` — do this arithmetic with a one-line
`python3 -c` command rather than mentally, so it's never off by a rounding
error.

## Mistake tagging

Every grammatical mistake found in a writing/grammar session must be tagged
with the *exact* topic string from that level's list in
`grammar.json` → `topics` (fetch via `nachhilfe grammar-topics`), so mistake
counts aggregate correctly across sessions instead of fragmenting into
near-duplicate tags. If a mistake doesn't cleanly match any existing topic,
pick the closest one rather than inventing a new tag inline.
