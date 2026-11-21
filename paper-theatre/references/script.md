# Script (`script.md`)

## Shape

- Scenes as `## N. Scene title` — the titles become chapters. Count them from the target length (about a minute per scene for long-form).
- Each scene: lines of 1–3 sentences, one line = one take. Under the lines, a `> Picture:` paragraph says what is on stage and which cut-outs it needs.
- Each line starts with an English delivery instruction in parentheses, then the text in the narration language.
- The first scene opens on a concrete moment (a year, a place, a person doing something), turns it into the question the film answers, and ends on the title card. The last scene returns to the opening image with the answer.
- A long film asks the viewer once to like and subscribe: one line of its own at the close of the chapter about two thirds in, in the wording agreed for the channel and tied to this film's subject, with a picture beat of its own (the channel's name on a card, a figure from the film reacting to the ask). Not in the opening, not twice, not as a closing tag after the answer.

## Writing

- Written to be spoken in the narration language as a native speaker would say it: short sentences, active voice, concrete nouns, one idea per sentence; no translated-English phrasing.
- Every scene moves the viewer loop forward; cut what does not.
- Prefer one vivid, sourced object or person to an inventory of facts.
- When a well-known story is wrong, say what was claimed and what is true.
- A dry turn or joke every scene or two, fitting the agreed tone.
- Avoid: "in today's episode", "let's dive in", textbook transitions, triple-balanced lists, a rhetorical question in every scene, an ask to the viewer worded the same in every film.

## Numbers and names

- Write numbers as digits where captions should show digits. `tools/script.py` refuses an unmapped digit: add its spoken form to `film.json` → `spoken`, keyed by the exact on-screen phrase, using `{display|spoken}` spans.
- Add a phonetic spoken form for foreign names and words the voice may read with another language's rules, using the same display/spoken mechanism.
- A line that opens with a name or a number is the most likely to start wrong; keep the first word plain when the sentence allows.

## Fact check (before voice and scene production)

- Keep a claim register linking each material claim to a stable line or scene ID, its exact source location, the supported wording, uncertainty and the corresponding visual assertion. Read the source; a search excerpt or an uninspected citation is not verification.
- Check dates, quantities, units, places, attributions and comparisons against the best available evidence. Distinguish the date of an object's creation from its arrival, deposition, discovery and later interpretation. Identify what a reported total counts and whether a later study revises it.
- Match the specificity of the statement to the evidence. Preserve approximation, disputed identifications and scholarly disagreement in narration and labels. A plausible reconstruction is not an observed fact.
- Check the picture as part of the claim: object inventories, construction, boundaries, routes, portraits, ownership and reenacted actions can imply facts the narration never states. Mark a reconstruction when the viewer could reasonably mistake it for documented evidence.
- Resolve material contradictions before approving the script and producing voice or scenes. Record deliberately retained uncertainties. If later evidence changes a claim, identify every affected line, label, map, caption and derived export before rebuilding.
- Use period-appropriate place names and explain ambiguous identifications. Do not infer certainty merely from a modern name or a familiar account.

## Delivery instructions

English, concrete, 2–4 qualities specifying emotion, pace and emphasis. Vary them along each scene's arc. Let the delivery set the pace of the opening and any reveal.
