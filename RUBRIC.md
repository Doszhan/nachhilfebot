# Scoring rubric

Used identically by `/nachhilfe-writing`, `/nachhilfe-grammar`,
`/nachhilfe-translate` and `/nachhilfe-dialog`, so a "7/10" means the same thing in September as it does a year
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

## Grammar exercises (`/nachhilfe-grammar`) — each exercise out of 10

Every exercise gets its own grade in half-point steps; the plugin averages
them (`session-log --item-score`), the model never does the arithmetic.

| Grade | Meaning |
|---|---|
| 10 | Fully correct |
| 9 | Correct apart from a spelling or umlaut slip |
| 7–8 | The target structure is right, with one small error elsewhere |
| 5–6 | The structure is attempted but contains an error |
| 3–4 | The structure is wrong, the sentence is still understandable |
| 0–2 | Not the requested structure, or not understandable |

## Translation (`/nachhilfe-translate`) — every sentence out of 10

Every answer gets its own grade from 0 to 10 in half-point steps; the
session score is their average (computed by the plugin). Judge meaning and
grammar, not word-for-word agreement with the reference.

| Grade | Meaning |
|---|---|
| 10 | Fully correct (an alternative wording is fine) |
| 9 | Only a spelling or umlaut slip |
| 7–8 | Meaning and structure right, one or two small errors (an ending, an article) |
| 5–6 | Understandable, but several errors or a target word missing |
| 3–4 | Only part of the meaning conveyed, or serious errors |
| 1–2 | Fragments |
| 0 | Nothing usable |

The plugin caps the grade by what it measured itself: at most **7** while a
target word is missing from the answer, at most **9** while one is
misspelled or the answer carries grammar mistake tags. Accepting an equally
valid expression for a target word (`--accept`) lifts the cap for that word.
Grammar mistakes use the same tagging rules as below.

## Dialog (`/nachhilfe-dialog`) — every answer out of 10, from three sub-scores

Grade each answer of the learner in the conversation (and correct it on the
spot), then let the plugin add the sub-scores up. Answers in real life are
short, so length is never penalised.

| Sub-score | Points | What to check |
|---|---|---|
| Fit | 0–4 | Answers what was asked, moves the situation forward, handles a surprise sensibly |
| Accuracy | 0–3 | Correct grammar and word choice at the learner's level (count real errors) |
| Naturalness | 0–3 | Sounds like real speech, right register (Sie/du), idiomatic where it matters |

The session score is the average of all graded answers.

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
