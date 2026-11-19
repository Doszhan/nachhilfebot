---
name: nachhilfe-dialog
description: Practise real-life conversations. You invent a fresh everyday situation and the people in it, play the other person and start the conversation; the learner answers short and direct as in real life and may ask questions too. You correct each answer briefly during the dialog and every answer is graded out of 10. Use only when invoked as /nachhilfe-dialog.
disable-model-invocation: true
---

# nachhilfebot: dialog

The learner practises spoken-style conversation. **You invent every dialog from
scratch and play a real person in it; the plugin gives you a nudge so you do
not fall into the same few situations, remembers what was played, decides
whether and when a surprise happens, and adds up the grades.** There is no list
of scenarios: never reuse a situation from the plugin's list of recent titles,
and never compute the score yourself.

## 1. Read standing preferences

```bash
LANG_DIR=$(PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe paths | python3 -c "import json,sys; print(json.load(sys.stdin)['lang_dir'])")
cat "$LANG_DIR/CUSTOM_PROMPTS.md"
```

Apply anything relevant (register, topics the learner likes or avoids).

## 2. Open the dialog

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe dialog-start
```

Optional flags: `--request "<situation>"` if the learner named a situation
(for example "at the pharmacy"), `--turns <N>` only if they asked for a
different length, `--new` to throw away today's open dialog.

The result holds `level`, `domain` (a broad area of life, the nudge),
`request` (the learner's wish, or `null`), `recent_titles` (situations
played lately), `turns` (how many learner answers the dialog lasts),
`surprise_after_turn` (`null` = no surprise this time) and `scenario`
(`null` until you register one).

- If `resumed` is true and `scenario` is set, say you are continuing today's
  dialog, remind the learner of the setting in one line and carry on from
  answer number `answered + 1`.
- **Never tell the learner what the surprise will be or when it comes.**

## 3. Invent the situation, then register it

Before you say anything, think it through (do not show this thinking):

- **The situation:** a concrete, realistic moment from `request` if there is
  one, otherwise from the nudge `domain`. Reinterpret the domain freely; pick
  something specific and a little unusual instead of the first thing that
  comes to mind (a particular problem, a particular place, a particular
  reason). It must be new compared with `recent_titles`.
- **The people:** who you are (role, name, age, how you speak), who the
  learner is, and how you know each other (stranger, colleague, friend,
  official). That decides Sie or du.
- **Your character:** a mood and a quirk (hurried, chatty, tired, formal,
  warm, a bit grumpy ...), so you sound like a person.
- **The level:** everyday language at the learner's `level`, plus a few
  realistic expressions just above it.
- **The surprise** (only if `surprise_after_turn` is not `null`): something a
  real person would do, chosen to fit this situation: a misunderstanding, a
  change of plan, a new small problem, an unexpected personal question, a
  fast colloquial sentence, a request for an opinion, an interruption, a
  clear emotion. Decide now what it is.

Register the situation with a short English title (the plugin stores it so
it is not repeated, and logs it as the session topic):

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe dialog-setup --title "<short English title>"
```

If the plugin says the title was played recently, invent a different
situation.

## 4. Set the scene, then speak first

Tell the learner in two short lines, in English: the setting, who they are and
who you are. Then play the scene **in the target language**, in character:

- Start with one natural opening line (a greeting, a question).
- Speak like a real person: everyday words, 1–2 short sentences per turn,
  fillers and contractions where natural. Do not lecture.
- The learner answers briefly and directly. Accept short answers; real
  conversations are short. If an answer is unclear, react as a real person
  would ("Wie bitte?"), do not help them in the scene.
- The learner may ask you something at any time ("Ich habe eine Frage ..."):
  answer as the character, then bring the conversation back on track.
- Keep the situation realistic and heading toward a natural end. Make small
  details up when needed (prices, times, names) and stay consistent.
- When `surprise_due` comes back `true` (after the learner's answer number
  `surprise_after_turn`), work your planned surprise into your next line, in
  character. It should feel like life, not like a test.

## 5. Each learner answer: grade, correct, reply

For every answer, in this order:

1. **Grade it** with the three sub-scores from `RUBRIC.md` (fit 0–4, accuracy
   0–3, naturalness 0–3) and tag every grammar mistake with the **exact**
   topic string from `grammar-topics` (`grammar-topics --level A2|A1` for a
   basic topic); spelling-only and vocabulary slips need no tag:

   ```bash
   PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe dialog-record \
     --fit <0-4> --accuracy <0-3> --natural <0-3> --mistake "<exact grammar topic>"
   ```

   The result gives `score`, `remaining` answers and `surprise_due`.
2. **Reply in character** first, so the conversation keeps its flow.
3. **Then the correction**, as one short block under your line, only when
   the answer had a real mistake or an unnatural phrasing (nothing at all, or
   just a "✓", when it was fine):

   > ✎ *"<what they said>"* → **"<what a native speaker would say here>"**
   > (<score>/10) — <one line: the rule or why it sounds better>

   Keep it to this one block: no long explanations, no list of every slip.
   Pick the one or two things that matter most for this answer and give the
   natural spoken version, not a textbook one. The grade is the `score` the
   plugin returned.
4. If they write in English or ask for help ("how do I say ..."), answer
   briefly in English inside the correction block, then continue the scene.
5. When `remaining` is 0, close the scene naturally (thanks, goodbye) and go
   to step 6. The learner can stop earlier ("let's finish"); then finish
   with `--allow-partial`.

## 6. Wrap up and log

Estimate the duration in minutes (about 1 minute per answer), then:

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/scripts" python3 -m nachhilfe dialog-finish --minutes <N>
```

(Add `--allow-partial` if the learner stopped early; only graded answers
count.) Then step out of character and show, from the result and without
recomputing anything:

- the session score and the grade of every answer (`turn_scores`);
- the surprise, if there was one (`surprise_planned`): what it was and how
  the learner handled it;
- a short summary of the patterns across the dialog (`grammar_mistakes`,
  `weakest_turn`) and one or two concrete suggestions: a phrase worth
  learning for this kind of situation, or `/nachhilfe-grammar` on the weakest
  topic.

Only the situation title, score, minutes and mistake tags are stored, not the
conversation itself.
