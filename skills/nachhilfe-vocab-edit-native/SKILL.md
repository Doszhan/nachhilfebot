---
name: nachhilfe-vocab-edit-native
description: Change the native-language word of a vocab card, for example when the translation on the card is wrong, too vague or has a better wording. The learner picks one of the latest cards and gives the new native word; the target word and the review schedule stay as they are. Use only when invoked as /nachhilfe-vocab-edit-native.
disable-model-invocation: true
---

# nachhilfebot: edit a card's native word

The learner wants to fix the native-language side of a card (the word they
are asked to translate). This is not a study session: nothing is logged and
no schedule changes.

## 1. Show the latest cards

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe vocab-recent
```

The result lists the most recently reviewed or added cards (`id`,
`native_word`, `target_word`, `level`), newest first; default 10, use
`--limit <N>` if the learner wants to see more. Show them as a numbered list,
**native word → target word**, so the learner can recognise the card. (This
is an edit, not a quiz, so showing the target word is fine.)

If the learner already named the card and the new wording in the same
message, skip the question and go to step 2.

Otherwise ask which card (a number or the word) and what the new native word
should be.

## 2. Make the change

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe vocab-edit-native --card-id "<id>" --native-word "<new native word>"
```

Write the new native word exactly as the learner gave it, in the same
language as the other cards (the cue language, usually English), without
translating or "correcting" it. Report the result in one line: old native
word → new native word, target word unchanged.

If the plugin refuses (the same word, an empty word, or another card
already uses that native word), tell the learner why in plain words. For a
duplicate, name the card it clashes with and offer to pick a different
wording or to hide the other card with
`vocab-suppress --card-id "<id>"`, but only do that if they say so.

## 3. Examples and next steps

If the new meaning differs from the old one, the saved example translations
of that card may no longer fit. Check with:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe vocab-reveal --card-id "<id>"
```

and only if `examples` is not empty and no longer matches, offer to rewrite
the three examples (same rules as in `/nachhilfe-vocab`, saved with
`vocab-examples --replace`).

Then ask whether they want to change another card, and repeat from step 1 if
so (the list is already on screen, just ask which one).
