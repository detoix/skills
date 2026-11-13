# Hardware Decision Records

## Locate or initialize the private record

Resolve the skill directory through symlinks. Read its `.env` as data, not
shell code. `HARDWARE_DECISION_LOG` must contain one literal absolute path to
a Markdown file, optionally surrounded by matching quotes:

```dotenv
HARDWARE_DECISION_LOG=/absolute/path/to/hardware-decisions.md
```

If `.env`, the setting, or the record is missing, ask the user to choose or
confirm the location and authorize initialization. If the target is ambiguous,
unexpected, or unwritable, resolve that before recording decisions; do not
silently select a different file. For an authorized first setup, create the
record and `.env`, ensure an ignore rule covers `.env`, and keep `.env`
untracked with owner-only permissions. Configure the private path locally,
never in the public skill text.

## Apply the workflow

Follow [do.md](do.md) for intent and authorization. Before changing the machine,
read relevant decisions, including superseded or rejected approaches, and
verify the current state. Explain the concrete purpose before a privileged
authentication prompt.

Record meaningful choices about the machine's intended behavior, settings,
fixes, and compatibility that future work should preserve, explaining the
reason and consequences. Deliberate desktop settings and app-specific system
integration fixes can qualify. Routine installs, obvious setup, inventories,
diagnostic activity, and unrelated work on skills, repositories, or agent
tools do not qualify merely because they happened on this machine.

## Maintain the record

Use the existing file and numbering scheme, preserving ADR identifiers if
already used. Continue its sequence without creating per-session logs or
parallel decision documents. A new record can start with this structure:

```markdown
# Hardware decision record

## HDR-001 — Decision title
Date: YYYY-MM-DD. Status: proposed | accepted | rejected | deferred | superseded.
Problem: The need or expected behavior.
Decision: What was chosen and why.
Consequences: Tradeoffs, relevant configuration locations, and reversal when useful.
Verification: Implementation state, what was checked, and remaining uncertainty.
```

Keep entries proportional to the decision. Update the relevant entry for
tuning, corrections, implementation, and verification rather than recording
each action. A materially different choice gets a new entry referencing the
superseded decision. Preserve important rejected alternatives without a
command-by-command history, and do not describe an unauthorized action as a
user decision.

Distinguish acceptance from completed implementation, assumptions from verified
results, and vendor defaults from local choices. Record the actual outcome and
remaining limits before finishing consequential work.

The record and `.env` are private. Keep them out of public repository content;
do not publish them without explicit authorization. Never include credentials
or unnecessary personal identifiers in the record.
